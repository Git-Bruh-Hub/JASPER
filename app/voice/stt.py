from __future__ import annotations

import logging
from pathlib import Path

from app.voice.base import SpeechToTextProvider


class FasterWhisperSTT(SpeechToTextProvider):
    """Local speech recognition using faster-whisper with lazy model loading."""

    def __init__(
        self,
        model_name: str = "small",
        *,
        device: str = "auto",
        gpu_compute_type: str = "int8_float16",
        cpu_compute_type: str = "int8",
        language: str = "auto",
    ) -> None:
        self.model_name = model_name
        self.device = device.lower()
        self.gpu_compute_type = gpu_compute_type
        self.cpu_compute_type = cpu_compute_type
        self.language = None if language.lower() == "auto" else language
        self._model = None
        self._device = None
        self.log = logging.getLogger("jasper.voice.stt")

    def _load_model(self) -> None:
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Speech recognition requires faster-whisper. "
                "Install with: pip install -r requirements-voice.txt"
            ) from exc

        if self.device in {"auto", "cuda", "gpu"}:
            try:
                self._model = WhisperModel(
                    self.model_name,
                    device="cuda",
                    compute_type=self.gpu_compute_type,
                )
                self._device = "cuda"
                self.log.info("Loaded STT model=%s device=cuda", self.model_name)
                return
            except Exception as exc:
                if self.device in {"cuda", "gpu"}:
                    raise RuntimeError(
                        f"CUDA speech recognition could not start: {exc}"
                    ) from exc
                self.log.warning("CUDA STT unavailable; falling back to CPU: %s", exc)

        try:
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type=self.cpu_compute_type,
            )
            self._device = "cpu"
            self.log.info("Loaded STT model=%s device=cpu", self.model_name)
        except Exception as exc:
            raise RuntimeError(f"Could not load STT model '{self.model_name}': {exc}") from exc

    def transcribe(self, audio_path: Path) -> str:
        self._load_model()
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)

        segments, _info = self._model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            return ""
        self.log.info("STT transcription completed device=%s chars=%s", self._device, len(text))
        return text
