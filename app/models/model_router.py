from .base import ModelProvider
from .ollama_provider import OllamaProvider
from app.core.config import JASPER_MODEL, JASPER_FAST_MODEL


from app.agents.router import CognitiveMode

class ModelRouter:
    """Route SIMPLE chat to the fast local model and reserve the main model for harder work."""

    def __init__(self):
        self.local = OllamaProvider()

    def provider_for(self, mode: CognitiveMode = CognitiveMode.SIMPLE) -> tuple[ModelProvider, str]:
        if mode in (CognitiveMode.DEEP, CognitiveMode.COLLABORATIVE):
            return self.local, JASPER_MODEL
        return self.local, JASPER_FAST_MODEL
