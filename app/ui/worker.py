from __future__ import annotations

import asyncio
import logging

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from app.core.approval import ApprovalRequest
from app.core.config import JASPER_VOICE_ENABLED
from app.ui.cancellation import AsyncRequestController
from app.core.orchestrator import Orchestrator
from app.core.permissions import PermissionManager
from app.main import build_registry, build_vision_manager, build_voice_manager
from app.memory.sqlite_memory import SQLiteMemory
from app.tools.system import get_system_info

if TYPE_CHECKING:
    from app.agents.coordinator import Coordinator


class JasperWorker(QObject):
    """Runs JASPER work away from the Qt GUI thread."""

    response_ready = Signal(str, str)  # kind, content
    response_stream = Signal(str)  # incremental assistant text
    vision_ready = Signal(str)
    status_changed = Signal(str)
    system_status_ready = Signal(dict)
    approval_requested = Signal(ApprovalRequest)
    error = Signal(str)
    finished = Signal()
    cancelled = Signal()

    def __init__(self, coordinator: Coordinator | None = None) -> None:
        super().__init__()
        self.log = logging.getLogger("jasper.ui.worker")
        self.vision = build_vision_manager()
        self.jasper = Orchestrator(build_registry(self.vision), PermissionManager(), SQLiteMemory(), vision=self.vision)
        self.voice = build_voice_manager() if JASPER_VOICE_ENABLED else None
        self._request_control = AsyncRequestController()
        self._coordinator: Coordinator | None = None
        if coordinator is not None:
            self.set_coordinator(coordinator)

    @property
    def coordinator(self) -> Coordinator | None:
        """Return the attached coordinator, or the orchestrator's coordinator if present."""
        if self._coordinator is not None:
            return self._coordinator
        coord = getattr(self.jasper, "multi_agent_coordinator", None)
        if coord is not None and getattr(coord, "_approval_notifier", None) is None:
            coord._approval_notifier = self.approval_requested.emit
        return coord

    def set_coordinator(self, coordinator: Coordinator | None) -> None:
        """Attach a coordinator and wire its approval notifier to approval_requested."""
        self._coordinator = coordinator
        if coordinator is not None and getattr(coordinator, "_approval_notifier", None) is None:
            coordinator._approval_notifier = self.approval_requested.emit
        if hasattr(self, "jasper") and self.jasper is not None:
            from app.agents.multi_agent_coordinator import MultiAgentCoordinator
            if isinstance(coordinator, MultiAgentCoordinator):
                self.jasper.multi_agent_coordinator = coordinator
            elif coordinator is None:
                self.jasper.multi_agent_coordinator = None

    def notify_approval(self, request: ApprovalRequest) -> None:
        """Emit approval_requested Qt Signal for an ApprovalRequest."""
        self.approval_requested.emit(request)

    @Slot(str, bool)
    def resolve_approval(self, gate_id: str, granted: bool) -> bool:
        """Resolve a pending approval gate on the attached coordinator.

        Thread-safe: May be called from the Qt GUI thread or connected to a Qt signal.
        Fails closed: Returns False if no coordinator is configured, if gate_id
        is invalid, or if the coordinator rejects resolution.
        """
        coord = self.coordinator
        if coord is None:
            self.log.warning(
                "resolve_approval rejected: no coordinator configured on worker (gate_id=%s)",
                gate_id,
            )
            return False

        if not isinstance(gate_id, str) or not gate_id.strip():
            self.log.warning("resolve_approval rejected: invalid gate_id=%r", gate_id)
            return False

        return coord.resolve_approval(gate_id.strip(), granted=bool(granted))

    def has_active_request(self) -> bool:
        """Return True if an asyncio request task is currently registered and not done."""
        return self._request_control.has_active_request()

    def begin_request(self) -> None:
        """Prepare a new request from the GUI thread."""
        self._request_control.begin()

    def cancel_request(self) -> None:
        """Thread-safe cancellation invoked directly from the GUI thread."""
        self._request_control.cancel()
        if self.voice is not None:
            stop = getattr(self.voice, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception as exc:
                    self.log.warning("voice.stop failed during cancellation: %s", exc)

    def _handle_error(self, exc: Exception, context: str) -> None:
        self.log.exception(f"{context} failed")

        # Friendly error mapping
        err_str = str(exc).lower()
        if isinstance(exc, asyncio.CancelledError):
            return  # Will be handled gracefully
        elif "connection" in err_str or "connect" in err_str or "11434" in err_str:
            self.error.emit("Ollama is currently unavailable. Please check if it's running.")
        elif "not found" in err_str and "image" in err_str:
            self.error.emit("The specified image could not be found.")
        elif "model" in err_str and "not found" in err_str:
            self.error.emit("The required AI model is not downloaded or available in Ollama.")
        elif isinstance(exc, PermissionError) or "denied" in err_str:
            self.error.emit(f"Operation cancelled: {exc}")
        else:
            self.error.emit("An unexpected internal error occurred. Please check the logs.")

    @Slot()
    def refresh_system_status(self) -> None:
        try:
            self.system_status_ready.emit(get_system_info())
        except Exception as exc:
            self.log.exception("System status refresh failed")
            self.error.emit(f"System status unavailable: {exc}")

    def _emit_stream_chunk(self, chunk: str) -> None:
        if chunk and not self._request_control.is_cancelled():
            self.response_stream.emit(chunk)

    @Slot(str)
    @Slot(str, str)
    def send_text(self, text: str, session_id: str | None = None) -> None:
        self.status_changed.emit("ACTIVE")
        sid = session_id or getattr(self, "active_session_id", None)
        try:
            answer = self._request_control.run(
                self.jasper.respond(
                    text,
                    on_chunk=self._emit_stream_chunk,
                    cancel_callback=self._request_control.is_cancelled,
                    session_id=sid,
                )
            )
            if not self._request_control.is_cancelled():
                self.response_ready.emit("text", answer)
        except asyncio.CancelledError:
            self.log.info("desktop text request cancelled")
            self.status_changed.emit("CANCELLED")
            self.cancelled.emit()
        except Exception as exc:
            self._handle_error(exc, "Desktop text request")
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()

    @Slot(str, str)
    @Slot(str, str, str)
    def send_text_with_image(self, text: str, image_path: str, session_id: str | None = None) -> None:
        """Send text alongside an attached image through the vision-to-text bridge."""
        self.status_changed.emit("ACTIVE")
        sid = session_id or getattr(self, "active_session_id", None)
        try:
            answer = self._request_control.run(
                self.jasper.respond(
                    text,
                    on_chunk=self._emit_stream_chunk,
                    image_path=image_path,
                    cancel_callback=self._request_control.is_cancelled,
                    session_id=sid,
                )
            )
            if not self._request_control.is_cancelled():
                self.response_ready.emit("text", answer)
        except asyncio.CancelledError:
            self.log.info("desktop vision-chat request cancelled")
            self.status_changed.emit("CANCELLED")
            self.cancelled.emit()
        except Exception as exc:
            self._handle_error(exc, "Desktop vision-chat request")
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()

    @Slot(str, str)
    def analyze_vision(self, image_path: str, prompt: str) -> None:
        self.status_changed.emit("ACTIVE")
        try:
            result = self._request_control.run(
                self.vision.analyze(image_path, prompt)
            )
            if not self._request_control.is_cancelled():
                self.vision_ready.emit(result.answer)
        except asyncio.CancelledError:
            self.log.info("standalone vision request cancelled")
            self.status_changed.emit("CANCELLED")
            self.cancelled.emit()
        except Exception as exc:
            self._handle_error(exc, "Desktop vision request")
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()

    @Slot()
    def listen_once(self) -> None:
        if self.voice is None:
            self.error.emit("Voice is disabled. Set JASPER_VOICE_ENABLED=true and restart JASPER.")
            self.finished.emit()
            return

        self.status_changed.emit("LISTENING")
        try:
            spoken_text, answer = self._request_control.run(
                self.voice.run_once(
                    self.jasper.respond,
                    cancel_callback=self._request_control.is_cancelled,
                )
            )
            if self._request_control.is_cancelled():
                self.cancelled.emit()
                return
            if not spoken_text:
                self.response_ready.emit("voice_empty", "I didn't detect any speech.")
            else:
                self.response_ready.emit("voice", f"{spoken_text}\n\n{answer}")
        except asyncio.CancelledError:
            self.log.info("desktop voice request cancelled")
            self.status_changed.emit("CANCELLED")
            self.cancelled.emit()
        except Exception as exc:
            self._handle_error(exc, "Desktop voice request")
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()

    @Slot(str)
    def speak_text(self, text: str) -> None:
        if self.voice is None:
            self.error.emit("Voice is disabled. Set JASPER_VOICE_ENABLED=true and restart JASPER.")
            self.finished.emit()
            return

        self.status_changed.emit("SPEAKING")
        try:
            self.voice.speak(text)
        except Exception as exc:
            self._handle_error(exc, "Desktop TTS request")
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()
