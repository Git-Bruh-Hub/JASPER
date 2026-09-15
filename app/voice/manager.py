from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from app.voice.audio import record_until_silence
from app.voice.base import SpeechToTextProvider, TextToSpeechProvider


class VoiceManager:
    """Coordinates recording, transcription, JASPER responses, and speech."""

    def __init__(
        self,
        stt: SpeechToTextProvider,
        tts: TextToSpeechProvider,
        *,
        temp_dir: str | Path,
        max_seconds: float = 8.0,
        sample_rate: int = 16_000,
        silence_seconds: float = 0.9,
        silence_threshold: float = 0.01,
        min_seconds: float = 0.6,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.temp_dir = Path(temp_dir)
        self.max_seconds = max_seconds
        self.sample_rate = sample_rate
        self.silence_seconds = silence_seconds
        self.silence_threshold = silence_threshold
        self.min_seconds = min_seconds
        self.log = logging.getLogger("jasper.voice")

    def listen_once(self) -> str:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="jasper_", suffix=".wav", dir=self.temp_dir, delete=False
        ) as temp:
            audio_path = Path(temp.name)

        try:
            record_until_silence(
                audio_path,
                max_seconds=self.max_seconds,
                sample_rate=self.sample_rate,
                silence_seconds=self.silence_seconds,
                silence_threshold=self.silence_threshold,
                min_seconds=self.min_seconds,
            )
            text = self.stt.transcribe(audio_path).strip()
            self.log.info("voice input transcribed chars=%s", len(text))
            return text
        finally:
            audio_path.unlink(missing_ok=True)

    def speak(self, text: str) -> None:
        self.tts.speak(text)

    async def run_once(self, responder: Callable[[str], Awaitable[str]]) -> tuple[str, str]:
        user_text = self.listen_once()
        if not user_text:
            return "", ""
        answer = await responder(user_text)
        self.speak(answer)
        return user_text, answer
