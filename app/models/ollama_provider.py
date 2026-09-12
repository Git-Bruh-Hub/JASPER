from typing import Any
import httpx
from .base import ModelProvider
from app.core.config import OLLAMA_HOST, JASPER_MODEL, JASPER_KEEP_ALIVE, JASPER_THINK

class OllamaProvider(ModelProvider):
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")

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
            return response.json()
