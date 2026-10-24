from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncIterator

import httpx

from app.core.config import (
    JASPER_VISION_KEEP_ALIVE,
    JASPER_VISION_MAX_IMAGE_MB,
    JASPER_VISION_MAX_OUTPUT_TOKENS,
    JASPER_VISION_MODEL,
    JASPER_VISION_THINK,
    OLLAMA_HOST,
)
from .base import VisionProvider, VisionResult
from .image import load_image


class OllamaVisionProvider(VisionProvider):
    """Ollama-backed multimodal provider using the native /api/chat images field."""

    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")
        self.log = logging.getLogger("jasper.vision.ollama")

    def _payload(
        self,
        image_path: Path,
        prompt: str,
        *,
        model: str | None,
        stream: bool,
        max_output_tokens: int | None,
    ) -> dict:
        max_image_bytes = JASPER_VISION_MAX_IMAGE_MB * 1024 * 1024
        image = load_image(image_path, max_bytes=max_image_bytes)
        options: dict[str, Any] = {}
        target_tokens = max_output_tokens if max_output_tokens is not None else JASPER_VISION_MAX_OUTPUT_TOKENS
        if target_tokens and target_tokens > 0:
            options["num_predict"] = target_tokens

        return {
            "model": model or JASPER_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image.base64_data],
                }
            ],
            "stream": stream,
            "keep_alive": JASPER_VISION_KEEP_ALIVE,
            "options": options,
            "think": JASPER_VISION_THINK,
        }

    async def analyze(
        self,
        image_path: Path,
        prompt: str,
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> VisionResult:
        selected_model = model or JASPER_VISION_MODEL
        payload = self._payload(
            image_path,
            prompt,
            model=selected_model,
            stream=False,
            max_output_tokens=max_output_tokens,
        )
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        msg = data.get("message") or {}
        content = (msg.get("content") or "").strip()
        thinking = (msg.get("thinking") or "").strip()
        answer = content or thinking
        if not answer:
            raise RuntimeError("Vision model returned an empty response.")

        self._log_metrics(data, selected_model)
        return VisionResult(
            provider="ollama",
            model=selected_model,
            image_path=str(image_path),
            prompt=prompt,
            answer=answer,
        )

    async def stream_analyze(
        self,
        image_path: Path,
        prompt: str,
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        selected_model = model or JASPER_VISION_MODEL
        payload = self._payload(
            image_path,
            prompt,
            model=selected_model,
            stream=True,
            max_output_tokens=max_output_tokens,
        )
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = ((chunk.get("message") or {}).get("content") or "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        self._log_metrics(chunk, selected_model)

    def _log_metrics(self, data: dict, model: str) -> None:
        values = (
            data.get("total_duration"),
            data.get("load_duration"),
            data.get("prompt_eval_duration"),
            data.get("eval_duration"),
        )
        if not all(isinstance(value, (int, float)) for value in values):
            return

        def seconds(value: int | float) -> float:
            return value / 1_000_000_000

        self.log.info(
            "vision response model=%s total=%.2fs load=%.2fs prompt=%.2fs eval=%.2fs eval_tokens=%s",
            model,
            seconds(values[0]),
            seconds(values[1]),
            seconds(values[2]),
            seconds(values[3]),
            data.get("eval_count"),
        )
