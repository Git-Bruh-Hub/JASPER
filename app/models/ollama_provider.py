from typing import Any, AsyncIterator
import json
import logging

import httpx

from .base import ModelProvider
from app.core.config import OLLAMA_HOST, JASPER_KEEP_ALIVE, JASPER_MAX_OUTPUT_TOKENS, JASPER_MODEL, JASPER_THINK


class OllamaProvider(ModelProvider):
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")
        self.log = logging.getLogger("jasper.models.ollama")

    def _payload(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None,
        tools: list[dict[str, Any]] | None,
        keep_alive: str | int,
        think: bool | None,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or JASPER_MODEL,
            "messages": messages,
            "stream": stream,
            "keep_alive": keep_alive,
            "options": {"num_predict": JASPER_MAX_OUTPUT_TOKENS},
        }
        if tools:
            payload["tools"] = tools
        if think is not None:
            payload["think"] = think
        return payload

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        keep_alive: str | int = JASPER_KEEP_ALIVE,
        think: bool | None = JASPER_THINK,
    ) -> dict[str, Any]:
        payload = self._payload(
            messages,
            model=model,
            tools=tools,
            keep_alive=keep_alive,
            think=think,
            stream=False,
        )
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        self._log_metrics(data, model or JASPER_MODEL)
        return data

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        keep_alive: str | int = JASPER_KEEP_ALIVE,
        think: bool | None = JASPER_THINK,
    ) -> AsyncIterator[dict[str, Any]]:
        payload = self._payload(
            messages,
            model=model,
            tools=tools,
            keep_alive=keep_alive,
            think=think,
            stream=True,
        )

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    yield chunk
                    if chunk.get("done"):
                        self._log_metrics(chunk, model or JASPER_MODEL)

    def _log_metrics(self, data: dict[str, Any], model: str) -> None:
        total = data.get("total_duration")
        load = data.get("load_duration")
        prompt = data.get("prompt_eval_duration")
        eval_duration = data.get("eval_duration")
        eval_tokens = data.get("eval_count")
        if not all(isinstance(value, (int, float)) for value in (total, load, prompt, eval_duration)):
            return

        def seconds(value: int | float) -> float:
            return value / 1_000_000_000

        self.log.info(
            "ollama response model=%s total=%.2fs load=%.2fs prompt=%.2fs eval=%.2fs eval_tokens=%s",
            model,
            seconds(total),
            seconds(load),
            seconds(prompt),
            seconds(eval_duration),
            eval_tokens,
        )
