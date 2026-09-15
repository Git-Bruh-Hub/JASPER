from .base import ModelProvider
from .ollama_provider import OllamaProvider
from app.core.config import JASPER_MODEL, JASPER_FAST_MODEL


class ModelRouter:
    """Small heuristic router for local models.

    Fast model: normal conversation, explanations, and short/simple requests.
    Main model: tools, coding, planning, research, deep comparison, and other
    requests that genuinely benefit from the larger model.
    """

    def __init__(self):
        self.local = OllamaProvider()

    def provider_for(self, task: str) -> tuple[ModelProvider, str]:
        text = task.lower().strip()
        complex_markers = (
            "analyze", "analysis", "compare", "debug", "code", "program",
            "plan", "planning", "reason", "research", "explain in depth",
            "step by step", "calculate", "why", "how should", "tool",
            "file", "folder", "directory", "windows", "check my",
            "find in", "read",
        )
        is_complex = len(text) > 280 or any(marker in text for marker in complex_markers)
        return self.local, (JASPER_MODEL if is_complex else JASPER_FAST_MODEL)
