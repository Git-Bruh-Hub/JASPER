from .base import ModelProvider
from .ollama_provider import OllamaProvider
from app.core.config import JASPER_MODEL, JASPER_FAST_MODEL


class ModelRouter:
    """Route ordinary chat to the fast local model and reserve the main model for harder work."""

    _COMPLEX_MARKERS = (
        "analyze",
        "analysis",
        "compare",
        "debug",
        "code",
        "program",
        "design",
        "plan",
        "planning",
        "reason through",
        "research",
        "in depth",
        "deep dive",
        "comprehensive",
        "step by step",
    )

    def __init__(self):
        self.local = OllamaProvider()

    def provider_for(self, task: str) -> tuple[ModelProvider, str]:
        text = task.lower().strip()
        is_complex = len(text) > 320 or any(marker in text for marker in self._COMPLEX_MARKERS)
        return self.local, (JASPER_MODEL if is_complex else JASPER_FAST_MODEL)
