"""app/core/response.py -- Response normalization and sanitization utilities.

Normalizes model responses before storage and presentation, stripping
internal reasoning metadata (<think>...</think> and stray closing tags)
while preserving legitimate final answers, code blocks, and prose.
"""

from __future__ import annotations

import re


def sanitize_thinking_tags(text: str) -> str:
    """Strip model chain-of-thought metadata while preserving answer content.

    Handles:
    - Complete reasoning blocks (<think>...</think>)
    - Stray leading/trailing closing tags (e.g. </think> prefix from continued turns)
    - Incomplete thinking blocks at the start of output (unclosed <think>)
    - Code blocks (fenced ``` and inline `) containing <think> tags are preserved
    - Natural language prose discussing <think> or </think> tags is preserved

    Parameters
    ----------
    text:
        Raw model response string.

    Returns
    -------
    str
        Sanitized text without internal chain-of-thought metadata.
    """
    if not text or not isinstance(text, str):
        return ""

    code_blocks: list[str] = []

    def _save_block(m: re.Match[str]) -> str:
        code_blocks.append(m.group(0))
        return f"__JASPER_CODE_BLOCK_{len(code_blocks) - 1}__"

    # 1. Protect markdown code blocks (fenced ```...``` and inline `...`)
    cleaned = re.sub(r"`{3}.*?`{3}", _save_block, text, flags=re.DOTALL)
    cleaned = re.sub(r"`[^`\n]+`", _save_block, cleaned)

    # 2. Strip leading stray closing tags (e.g. </think> from continued turns)
    cleaned = re.sub(r"^\s*</think>\s*", "", cleaned, flags=re.IGNORECASE)

    # 3. Strip all leading complete <think>...</think> blocks
    while True:
        stripped = re.sub(r"^\s*<think>.*?</think>\s*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if stripped == cleaned:
            break
        cleaned = stripped

    # 4. Strip incomplete <think> block starting at the beginning (aborted during thinking)
    cleaned = re.sub(r"^\s*<think>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # 5. Strip trailing stray closing tags
    cleaned = re.sub(r"\s*</think>\s*$", "", cleaned, flags=re.IGNORECASE)

    # 6. Restore preserved code blocks
    for i, block in enumerate(code_blocks):
        cleaned = cleaned.replace(f"__JASPER_CODE_BLOCK_{i}__", block)

    return cleaned.strip()
