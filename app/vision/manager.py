from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncIterator

from app.core.config import JASPER_VISION_EMPTY_RESPONSE_RETRIES
from .base import VisionResult
from .router import VisionRouter

DEFAULT_VISION_PROMPT = (
    "Analyze the image and answer the user's request. Separate direct visual observations "
    "from uncertain identification. Only report details visually supported by the image. "
    "If requested information is not visible or cannot be determined confidently, say that "
    "it is not clearly visible. Never guess or invent details."
)


class VisionManager:
    """Coordinates image validation, provider routing, and visual observations."""

    def __init__(self, router: VisionRouter, empty_response_retries: int = JASPER_VISION_EMPTY_RESPONSE_RETRIES):
        self.router = router
        self.empty_response_retries = max(0, empty_response_retries)
        self.log = logging.getLogger("jasper.vision")

    async def analyze(self, image_path: str | Path, prompt: str = DEFAULT_VISION_PROMPT) -> VisionResult:
        path = Path(image_path).expanduser().resolve()
        self.log.info("vision analysis started path=%s", path)

        last_error: RuntimeError | None = None
        for attempt in range(self.empty_response_retries + 1):
            try:
                result = await self.router.analyze(path, prompt)
                self.log.info("vision analysis completed model=%s chars=%s", result.model, len(result.answer))
                return result
            except RuntimeError as exc:
                if str(exc) != "Vision model returned an empty response.":
                    raise
                last_error = exc
                if attempt >= self.empty_response_retries:
                    break
                self.log.warning(
                    "vision provider returned an empty response; retrying attempt=%s/%s",
                    attempt + 2,
                    self.empty_response_retries + 1,
                )

        raise RuntimeError(
            "Vision model returned an empty response after "
            f"{self.empty_response_retries + 1} attempt(s)."
        ) from last_error

    async def stream(self, image_path: str | Path, prompt: str = DEFAULT_VISION_PROMPT) -> AsyncIterator[str]:
        path = Path(image_path).expanduser().resolve()
        self.log.info("vision streaming started path=%s", path)
        async for chunk in self.router.stream_analyze(path, prompt):
            yield chunk
