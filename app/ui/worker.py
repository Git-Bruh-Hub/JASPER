from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.core.config import JASPER_VOICE_ENABLED
from app.ui.cancellation import AsyncRequestController
from app.core.orchestrator import Orchestrator
from app.core.permissions import PermissionManager
from app.main import build_registry, build_vision_manager, build_voice_manager
from app.memory.sqlite_memory import SQLiteMemory
from app.tools.system import get_system_info


class JasperWorker(QObject):
    """Runs JASPER work away from the Qt GUI thread."""

    response_ready = Signal(str, str)  # kind, content
    response_stream = Signal(str)  # incremental assistant text
    vision_ready = Signal(str)
    status_changed = Signal(str)
    system_status_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.log = logging.getLogger("jasper.ui.worker")
        self.vision = build_vision_manager()
        self.jasper = Orchestrator(build_registry(self.vision), PermissionManager(), SQLiteMemory(), vision=self.vision)
        self.voice = build_voice_manager() if JASPER_VOICE_ENABLED else None
        self._request_control = AsyncRequestController()

    def begin_request(self) -> None:
        """Prepare a new request from the GUI thread."""
        self._request_control.begin()

    def cancel_request(self) -> None:
        """Thread-safe cancellation invoked directly from the GUI thread."""
        self._request_control.cancel()
        if self.voice is not None:
            stop = getattr(self.voice, "stop", None)
            if callable(stop):
                stop()

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
    def send_text(self, text: str) -> None:
        self.status_changed.emit("ACTIVE")
        try:
            answer = self._request_control.run(
                self.jasper.respond(
                    text,
                    on_chunk=self._emit_stream_chunk,
                    cancel_callback=self._request_control.is_cancelled,
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
    def send_text_with_image(self, text: str, image_path: str) -> None:
        """Send text alongside an attached image through the vision-to-text bridge."""
        self.status_changed.emit("ACTIVE")
        try:
            answer = self._request_control.run(
                self.jasper.respond(
                    text,
                    on_chunk=self._emit_stream_chunk,
                    image_path=image_path,
                    cancel_callback=self._request_control.is_cancelled,
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
