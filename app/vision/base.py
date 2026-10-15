from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator


@dataclass(frozen=True)
class VisionResult:
    """The provider output plus explicit provenance for downstream reasoning."""

    provider: str
    model: str
    image_path: str
    prompt: str
    answer: str


class VisionProvider(ABC):
    """Provider interface for image understanding."""

    @abstractmethod
    async def analyze(
        self,
        image_path: Path,
        prompt: str,
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> VisionResult:
        raise NotImplementedError

    async def stream_analyze(
        self,
        image_path: Path,
        prompt: str,
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield incremental answer text when the provider supports streaming."""
        raise NotImplementedError
