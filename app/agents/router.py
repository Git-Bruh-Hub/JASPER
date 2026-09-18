from enum import Enum

class CognitiveMode(Enum):
    SIMPLE = "SIMPLE"
    COLLABORATIVE = "COLLABORATIVE"
    DEEP = "DEEP"

class CognitiveRouter:
    """Classifies user requests into a cognitive mode."""
    
    _DEEP_MARKERS = (
        "comprehensive",
        "deep dive",
        "step by step",
        "thorough",
        "in depth",
        "detailed plan",
    )
    
    _COLLAB_MARKERS = (
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
    )

    def route(self, user_text: str) -> CognitiveMode:
        """Deterministically route the request to a cognitive mode based on heuristics."""
        text = user_text.lower().strip()
        
        # Deep checks
        if any(marker in text for marker in self._DEEP_MARKERS):
            return CognitiveMode.DEEP
        if len(text) > 500:
            return CognitiveMode.DEEP
            
        # Collaborative checks
        if any(marker in text for marker in self._COLLAB_MARKERS):
            return CognitiveMode.COLLABORATIVE
        if len(text) > 300:
            return CognitiveMode.COLLABORATIVE
            
        # Default to simple
        return CognitiveMode.SIMPLE
