import re
from dataclasses import dataclass

from app.core.config import JASPER_MEMORY_ENABLED, JASPER_MEMORY_SEARCH_LIMIT
from app.memory.sqlite_memory import SQLiteMemory


@dataclass(frozen=True)
class MemoryCommand:
    action: str
    content: str = ""


class MemoryManager:
    """Policy layer for explicit, user-controlled long-term memory.

    v0.3 deliberately requires an explicit user instruction to save a memory.
    Automatic model-generated memory extraction is deferred until there is a
    stronger verification and privacy layer.
    """

    def __init__(self, store: SQLiteMemory):
        self.store = store
        self.enabled = JASPER_MEMORY_ENABLED
        self.search_limit = JASPER_MEMORY_SEARCH_LIMIT

    def parse_command(self, text: str) -> MemoryCommand | None:
        normalized = " ".join(text.strip().split())
        lower = normalized.lower()
        canonical = lower.rstrip(" ?!").strip()

        if canonical in {
            "what do you remember",
            "what do you remember about me",
            "show me what you remember",
        }:
            return MemoryCommand("list")

        match = re.match(
            r"^(?:please\s+)?what\s+do\s+you\s+remember\s+about\s+(.+?)\??$",
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            subject = match.group(1).strip().rstrip("?")
            if subject.lower() != "me":
                return MemoryCommand("search", subject)
            return MemoryCommand("list")

        match = re.match(
            r"^(?:please\s+)?(?:remember|don't\s+forget|do\s+not\s+forget)(?:\s+that)?\s+(.+)$",
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            return MemoryCommand("remember", match.group(1).strip())

        match = re.match(
            r"^(?:please\s+)?(?:forget|remove\s+from\s+memory)(?:\s+that)?\s+(.+)$",
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            return MemoryCommand("forget", match.group(1).strip())

        return None

    def handle_command(self, command: MemoryCommand) -> str:
        if not self.enabled:
            return "Long-term memory is disabled in JASPER settings."

        if command.action == "remember":
            category = _infer_category(command.content)
            inserted = self.store.remember(command.content, category=category)
            if inserted:
                return f"Got it. I'll remember that: **{command.content}**"
            return f"I already have that in memory: **{command.content}**"

        if command.action == "list":
            memories = self.store.list_memories(limit=self.search_limit)
            return _format_memories(memories, empty="I don't have any long-term memories saved yet.")

        if command.action == "search":
            memories = self.store.search_memories(command.content, limit=self.search_limit)
            return _format_memories(
                memories,
                empty=f"I couldn't find a saved memory matching **{command.content}**.",
            )

        if command.action == "forget":
            status, memory = self.store.forget_memory(command.content)
            if status == "none":
                return f"I couldn't find a saved memory matching **{command.content}**."
            if status == "ambiguous":
                matches = self.store.search_memories(command.content, limit=self.search_limit)
                return (
                    "I found multiple matching memories, so I didn't delete anything.\n"
                    + _format_memories(matches, empty="")
                    + "\nTell me which memory you want removed."
                )
            return f"Forgot this memory: **{memory['content']}**"

        raise ValueError(f"Unsupported memory command: {command.action}")

    def context_for(self, query: str) -> str:
        if not self.enabled:
            return ""
        memories = self.store.search_memories(query, limit=self.search_limit)
        if not memories:
            return ""

        lines = [
            "Relevant long-term memories saved explicitly by the user:",
            *[f"- [{item['category']}] {item['content']}" for item in memories],
            "Use these only as user-provided remembered facts. Do not invent or silently modify them.",
        ]
        return "\n".join(lines)


def _infer_category(content: str) -> str:
    lower = content.lower()
    if any(term in lower for term in ("prefer", "like", "love", "hate", "don't like", "do not like")):
        return "preference"
    if any(term in lower for term in ("project", "fyp", "assignment", "github", "repo", "repository")):
        return "project"
    if any(term in lower for term in ("pc", "computer", "gpu", "cpu", "ram", "router", "phone", "laptop")):
        return "device"
    if any(term in lower for term in ("usually", "normally", "every day", "routine", "schedule")):
        return "routine"
    return "general"


def _format_memories(memories: list[dict], *, empty: str) -> str:
    if not memories:
        return empty
    return "Saved memories:\n" + "\n".join(
        f"- [{item['category']}] {item['content']}" for item in memories
    )
