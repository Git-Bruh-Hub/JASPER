from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from app.voice.audio import record_until_silence
from app.voice.base import SpeechToTextProvider, TextToSpeechProvider


_DEFAULT_STOP_PHRASES = {
    "stop listening",
    "goodbye jasper",
    "bye jasper",
    "berhenti jasper",
    "berhenti dengar",
    "cukup jasper",
    "itu sahaja",
    "itu saja",
    "dah cukup",
}


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

    @staticmethod
    def should_stop_conversation(text: str) -> bool:
        normalized = text.lower().strip()
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        normalized = " ".join(normalized.split())
        return normalized in _DEFAULT_STOP_PHRASES

    async def run_once(self, responder: Callable[[str], Awaitable[str]]) -> tuple[str, str]:
        user_text = self.listen_once()
        if not user_text:
            return "", ""
        answer = await responder(user_text)
        self.speak(answer)
        return user_text, answer

    async def run_conversation(
        self,
        responder: Callable[[str], Awaitable[str]],
        *,
        max_turns: int = 8,
        empty_limit: int = 2,
        on_listen_start: Callable[[int], None] | None = None,
        on_turn: Callable[[int, str, str], None] | None = None,
    ) -> list[tuple[str, str]]:
        """Run a bounded, hands-free conversation without wake-word listening.

        The loop stops when the user says a local stop phrase, the configured
        turn limit is reached, or repeated empty recordings occur. All actual
        responses still go through the existing JASPER responder/orchestrator.
        """
        turns: list[tuple[str, str]] = []
        empty_count = 0
        max_turns = max(1, int(max_turns))
        empty_limit = max(1, int(empty_limit))

        for turn_number in range(1, max_turns + 1):
            if on_listen_start:
                on_listen_start(turn_number)

            user_text = self.listen_once()
            if not user_text:
                empty_count += 1
                self.log.info("voice conversation empty input count=%s", empty_count)
                if empty_count >= empty_limit:
                    break
                continue

            empty_count = 0
            if self.should_stop_conversation(user_text):
                self.log.info("voice conversation stopped by local phrase")
                break

            answer = await responder(user_text)
            self.speak(answer)
            turns.append((user_text, answer))
            if on_turn:
                on_turn(turn_number, user_text, answer)

        return turns
