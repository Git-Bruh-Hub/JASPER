from abc import ABC, abstractmethod
from typing import Any

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
    ) -> dict[str, Any]:
        raise NotImplementedError
