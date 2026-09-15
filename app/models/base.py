from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class ModelProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        keep_alive: str | int = "5m",
        think: bool | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        keep_alive: str | int = "5m",
        think: bool | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield streaming response chunks from providers that support them."""
        raise NotImplementedError
