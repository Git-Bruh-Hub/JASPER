from __future__ import annotations

from pathlib import Path

from app.core.config import JASPER_VISION_MODEL
from .base import VisionProvider


class VisionRouter:
    """Selects the configured vision provider without coupling JASPER to one backend."""

    def __init__(self, provider: VisionProvider, model: str = JASPER_VISION_MODEL):
        self.provider = provider
        self.model = model

    async def analyze(self, image_path: Path, prompt: str):
        return await self.provider.analyze(image_path, prompt, model=self.model)

    async def stream_analyze(self, image_path: Path, prompt: str):
        async for chunk in self.provider.stream_analyze(image_path, prompt, model=self.model):
            yield chunk
