"""Deterministic cognitive routing for JASPER v0.6.

Classifies user requests into SIMPLE, COLLABORATIVE, or DEEP using a
small feature-scoring classifier.  No LLM calls, no network, no
expensive processing — just cheap text features and bounded arithmetic.
"""

from __future__ import annotations

import re
from enum import Enum


class CognitiveMode(Enum):
    SIMPLE = "SIMPLE"
    COLLABORATIVE = "COLLABORATIVE"
    DEEP = "DEEP"


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------

# Verb/intent patterns compiled once at import time.
_TASK_VERBS = re.compile(
    r"\b(?:analyze|analysis|compare|evaluate|assess|debug|design|implement|refactor|"
    r"investigate|diagnose|optimise|optimize|benchmark|trace|profile)\b"
)
_PLANNING_INTENT = re.compile(
    r"\b(?:plan|outline|strategy|roadmap|break\s?down|architect)\b"
)
_MULTI_STEP = re.compile(
    r"\b(?:step[- ]+by[- ]+step|first\s.*then\s|phase\s+\d|multi[- ]?step|"
    r"stages?|sequentially|each\s+step|in\s+order)\b"
)
_DEPTH_REQUEST = re.compile(
    r"\b(?:comprehensive|thorough|in[- ]?depth|exhaustive|deep\s+dive|"
    r"detailed\s+analysis|detailed\s+plan|full\s+analysis|extensively)\b"
)
_COMPARISON = re.compile(
    r"\b(?:compare|contrast|versus|vs\.?|pros?\s+and\s+cons?|"
    r"trade[- ]?offs?|advantages?\s+and\s+disadvantages?)\b"
)
_EVIDENCE_RESEARCH = re.compile(
    r"\b(?:research|evidence|sources?|citations?|investigate|"
    r"find\s+(?:out|information)|gather\s+(?:data|info))\b"
)
_DEFINITION_QUESTION = re.compile(
    r"^(?:what\s+is|what\s+does|define|explain\s+what|what\s+do\s+you\s+mean)\b"
)
_CONJUNCTION_SPLIT = re.compile(
    r"(?:^|\.\s+|\n|;\s*|\band\s+also\b|\bthen\s+also\b|\badditionally\b)"
)


def _word_count(text: str) -> int:
    """Approximate word count."""
    return len(text.split())


def _count_objectives(text: str) -> int:
    """Estimate the number of distinct requested objectives."""
    parts = _CONJUNCTION_SPLIT.split(text)
    return sum(1 for p in parts if p and len(p.strip()) > 8)


# ---------------------------------------------------------------------------
# Scoring classifier
# ---------------------------------------------------------------------------

class CognitiveRouter:
    """Classifies user requests into a cognitive mode.

    Uses a small set of inexpensive text features to compute bounded
    scores for COLLABORATIVE and DEEP.  Normal conversation stays SIMPLE.
    """

    # Thresholds — tuned so that ordinary questions remain SIMPLE.
    _COLLAB_THRESHOLD = 2
    _DEEP_THRESHOLD = 5

    def route(self, user_text: str) -> CognitiveMode:
        """Deterministically route the request to a cognitive mode."""
        text = user_text.lower().strip()
        words = _word_count(text)

        score = 0

        # --- Feature: definition questions ---
        # Definitions negate the presence of single task verbs
        if _DEFINITION_QUESTION.search(text):
            score -= 2

        # --- Feature: word count / length ---
        if words > 60:
            score += 2
        elif words > 30:
            score += 1

        # --- Feature: task verb density ---
        task_verbs = len(_TASK_VERBS.findall(text))
        if task_verbs >= 2:
            score += 3
        elif task_verbs == 1:
            score += 2

        # --- Feature: planning intent ---
        if _PLANNING_INTENT.search(text):
            score += 2

        # --- Feature: multi-step language ---
        if _MULTI_STEP.search(text):
            score += 2

        # --- Feature: explicit depth request ---
        if _DEPTH_REQUEST.search(text):
            score += 3

        # --- Feature: comparison / evaluation ---
        if _COMPARISON.search(text):
            score += 2

        # --- Feature: research / evidence ---
        if _EVIDENCE_RESEARCH.search(text):
            score += 1

        # --- Feature: multiple objectives ---
        objectives = _count_objectives(text)
        if objectives >= 4:
            score += 2
        elif objectives >= 2:
            score += 1

        # --- Classify ---
        if score >= self._DEEP_THRESHOLD:
            return CognitiveMode.DEEP
        if score >= self._COLLAB_THRESHOLD:
            return CognitiveMode.COLLABORATIVE
        return CognitiveMode.SIMPLE
