"""Voice provider interfaces for JASPER."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SpeechToTextProvider(ABC):
    """Convert recorded audio into text."""

    @abstractmethod
    def transcribe(self, audio_path: Path) -> str:
        raise NotImplementedError


class TextToSpeechProvider(ABC):
    """Convert text into audible speech."""

    @abstractmethod
    def speak(self, text: str) -> None:
        raise NotImplementedError
