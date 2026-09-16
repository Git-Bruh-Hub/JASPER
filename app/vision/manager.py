from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncIterator

from .base import VisionResult
from .router import VisionRouter

DEFAULT_VISION_PROMPT = (
    "Analyze the image and answer the user's request. Separate direct visual observations "
    "from uncertain identification. Do not invent details that cannot be supported by the image."
)


class VisionManager:
    """Coordinates image validation, provider routing, and visual observations."""

    def __init__(self, router: VisionRouter):
        self.router = router
        self.log = logging.getLogger("jasper.vision")

    async def analyze(self, image_path: str | Path, prompt: str = DEFAULT_VISION_PROMPT) -> VisionResult:
        path = Path(image_path).expanduser().resolve()
        self.log.info("vision analysis started path=%s", path)
        result = await self.router.analyze(path, prompt)
        self.log.info("vision analysis completed model=%s chars=%s", result.model, len(result.answer))
        return result

    async def stream(self, image_path: str | Path, prompt: str = DEFAULT_VISION_PROMPT) -> AsyncIterator[str]:
        path = Path(image_path).expanduser().resolve()
        self.log.info("vision streaming started path=%s", path)
        async for chunk in self.router.stream_analyze(path, prompt):
            yield chunk
