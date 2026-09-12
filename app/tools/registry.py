from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

class Risk(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    DESTRUCTIVE = "destructive"
    ADMIN = "admin"

@dataclass
class Tool:
    name: str
    description: str
    risk: Risk
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
    })

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def list(self) -> list[Tool]:
        return list(self._tools.values())
