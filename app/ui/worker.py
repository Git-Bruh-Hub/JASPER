from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.core.config import JASPER_VOICE_ENABLED
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

    def __init__(self) -> None:
        super().__init__()
        self.log = logging.getLogger("jasper.ui.worker")
        self.vision = build_vision_manager()
        self.jasper = Orchestrator(build_registry(self.vision), PermissionManager(), SQLiteMemory())
        self.voice = build_voice_manager() if JASPER_VOICE_ENABLED else None

    @Slot()
    def refresh_system_status(self) -> None:
        try:
            self.system_status_ready.emit(get_system_info())
        except Exception as exc:
            self.log.exception("System status refresh failed")
            self.error.emit(f"System status unavailable: {exc}")

    def _emit_stream_chunk(self, chunk: str) -> None:
        if chunk:
            self.response_stream.emit(chunk)

    @Slot(str)
    def send_text(self, text: str) -> None:
        self.status_changed.emit("ACTIVE")
        try:
            answer = asyncio.run(self.jasper.respond(text, on_chunk=self._emit_stream_chunk))
            self.response_ready.emit("text", answer)
        except Exception as exc:
            self.log.exception("Desktop text request failed")
            self.error.emit(str(exc))
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()

    @Slot(str, str)
    def analyze_vision(self, image_path: str, prompt: str) -> None:
        self.status_changed.emit("ACTIVE")
        try:
            result = asyncio.run(self.vision.analyze(image_path, prompt))
            self.vision_ready.emit(result.answer)
        except Exception as exc:
            self.log.exception("Desktop vision request failed")
            self.error.emit(str(exc))
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
            spoken_text, answer = asyncio.run(self.voice.run_once(self.jasper.respond))
            if not spoken_text:
                self.response_ready.emit("voice_empty", "I didn't detect any speech.")
            else:
                self.response_ready.emit("voice", f"{spoken_text}\n\n{answer}")
        except Exception as exc:
            self.log.exception("Desktop voice request failed")
            self.error.emit(str(exc))
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
            self.log.exception("Desktop TTS request failed")
            self.error.emit(str(exc))
        finally:
            self.status_changed.emit("STANDBY")
            self.finished.emit()
