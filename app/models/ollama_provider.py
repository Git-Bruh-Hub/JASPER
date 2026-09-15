from typing import Any
import logging
import httpx
from .base import ModelProvider
from app.core.config import OLLAMA_HOST, JASPER_MODEL, JASPER_KEEP_ALIVE, JASPER_THINK


class OllamaProvider(ModelProvider):
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")
        self.log = logging.getLogger("jasper.models.ollama")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        keep_alive: str | int = JASPER_KEEP_ALIVE,
        think: bool | None = JASPER_THINK,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or JASPER_MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }
        if tools:
            payload["tools"] = tools
        if think is not None:
            payload["think"] = think

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        def seconds(value: Any) -> float | None:
            return value / 1_000_000_000 if isinstance(value, (int, float)) else None

        self.log.info(
            "ollama response model=%s total=%.2fs load=%s prompt=%s eval=%s eval_tokens=%s",
            data.get("model", model),
            seconds(data.get("total_duration")) or 0.0,
            f"{seconds(data.get('load_duration')):.2f}s" if seconds(data.get("load_duration")) is not None else "n/a",
            f"{seconds(data.get('prompt_eval_duration')):.2f}s" if seconds(data.get("prompt_eval_duration")) is not None else "n/a",
            f"{seconds(data.get('eval_duration')):.2f}s" if seconds(data.get("eval_duration")) is not None else "n/a",
            data.get("eval_count", "n/a"),
        )
        return data
