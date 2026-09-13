import json
import logging
import re
from typing import Any

from app.core.config import MAX_HISTORY_MESSAGES
from app.models.model_router import ModelRouter
from app.core.permissions import PermissionManager
from app.tools.registry import ToolRegistry

SYSTEM_PROMPT = """You are JASPER, a local-first personal AI assistant.
JASPER means Just Another Smart Program Executing Request.

Communication:
- Understand English, Bahasa Malaysia, casual Malay, slang, typos, and BM-English rojak.
- Reply naturally in the user's language/style unless asked otherwise.
- Do not invent facts or claim an action was performed unless the system actually performed it.

Tool use:
- You have access to read-only local tools.
- Use a tool when the user's request requires current information from this computer.
- Do not guess information that a tool can directly verify.
- After receiving tool results, answer using those results.
- Never claim a tool ran unless its result confirms it.

Safety:
- Never invent filesystem contents or system state.
- Do not attempt actions outside the tools provided to you.
- The current tool policy is read-only.
"""

MAX_TOOL_ROUNDS = 5

# Direct system-fact questions are routed through the observation tool before
# the LLM gets a chance to answer. This prevents the model from substituting
# remembered/common hardware values for the user's actual machine.
SYSTEM_FACT_PATTERNS = (
    r"\bwhat (?:cpu|processor) (?:am i|do i) (?:using|have)\b",
    r"\bwhat (?:gpu|graphics card|video card) (?:am i|do i) (?:using|have)\b",
    r"\bhow much (?:ram|memory) .*\bdo i have\b",
    r"\bhow much (?:storage|disk space) .*\bdo i have\b",
    r"\bwhat (?:drives|storage drives) do i have\b",
    r"\bwhat model is currently loaded in ollama\b",
    r"\bhow much vram .*ollama\b",
    r"\bwhat (?:model|models) .*loaded.*ollama\b",
    r"\bmy (?:hardware|pc specs|computer specs|system specs)\b",
)

SYSTEM_FACT_TERMS = {
    "cpu": ("cpu", "processor"),
    "gpu": ("gpu", "graphics card", "video card"),
    "ram": ("ram", "memory"),
    "storage": ("storage", "disk space", "drive", "drives"),
    "ollama": ("ollama",),
}

SYSTEM_LIVE_CONTEXT = (
    "my",
    "i have",
    "am i using",
    "do i have",
    "currently",
    "running",
    "loaded",
    "using",
    "specs",
    "system information",
    "system info",
    "pc information",
    "pc info",
)


def _requires_system_observation(text: str) -> bool:
    """Return True when the user is asking for facts about this live machine."""
    normalized = " ".join(text.lower().split())

    # Keep the original high-confidence patterns for common direct questions.
    if any(re.search(pattern, normalized) for pattern in SYSTEM_FACT_PATTERNS):
        return True

    # Handle natural combined questions such as:
    # "Tell me my CPU, GPU, VRAM, RAM, storage, and currently loaded model."
    # The old detector missed these because none of the single-fact regexes
    # required an exact phrase match. Requiring multiple hardware/runtime
    # categories plus live-system context avoids hijacking conceptual questions.
    matched_categories = 0
    for terms in SYSTEM_FACT_TERMS.values():
        if any(term in normalized for term in terms):
            matched_categories += 1

    has_live_context = any(
        re.search(rf"\b{re.escape(context)}\b", normalized)
        if " " not in context
        else context in normalized
        for context in SYSTEM_LIVE_CONTEXT
    )

    if matched_categories >= 2 and has_live_context:
        return True

    # Common explicit system-spec phrasing.
    return bool(
        re.search(r"\b(what|tell me|show me|give me)\b.*\b(my|this)\b.*\b(pc|computer|system|hardware)\b", normalized)
        or re.search(r"\b(my|this)\b.*\b(pc|computer|system|hardware)\b.*\b(specs|information|info)\b", normalized)
    )


def _system_observation_tool_result(registry: ToolRegistry, permissions: PermissionManager) -> dict:
    tool = registry.get("get_system_info")
    permissions.check(tool)
    return tool.handler()


def _format_system_fact_answer(question: str, info: dict) -> str:
    """Answer direct hardware/runtime questions only from observed values."""
    q = question.lower()
    sections: list[str] = []

    asks_cpu = "cpu" in q or "processor" in q
    asks_gpu = "gpu" in q or "graphics card" in q or "video card" in q
    asks_ram = "ram" in q or "memory" in q
    asks_storage = "storage" in q or "disk space" in q or "drive" in q
    asks_ollama = "ollama" in q and ("model" in q or "vram" in q)

    if asks_cpu:
        cpu = info.get("cpu")
        sections.append(f"CPU: **{cpu}**" if cpu else "CPU: unavailable from the system inspection tool.")

    if asks_gpu:
        gpus = info.get("gpu") or []
        if not gpus:
            sections.append("GPU: I couldn't detect an NVIDIA GPU from the system inspection tool.")
        else:
            gpu_lines = []
            for gpu in gpus:
                name = gpu.get("name") or "Unknown GPU"
                vram = gpu.get("vram_total_gb")
                suffix = f" — **{vram:g} GB** VRAM" if isinstance(vram, (int, float)) else ""
                gpu_lines.append(f"**{name}**{suffix}")
            sections.append("GPU: " + "; ".join(gpu_lines))

    if asks_ram:
        total = info.get("ram_total_gb")
        available = info.get("ram_available_gb")
        used = info.get("ram_used_percent")
        if isinstance(total, (int, float)):
            sections.append(
                f"RAM: **{total:g} GB** total, **{available:g} GB** available ({used:g}% used)."
            )
        else:
            sections.append("RAM: I couldn't determine it from the system inspection tool.")

    if asks_storage:
        drives = info.get("storage") or []
        if not drives:
            sections.append("Storage: I couldn't detect any mounted storage volumes.")
        else:
            storage_lines = [
                f"**{drive['path']}** — **{drive['total_gb']:g} GB** total, "
                f"**{drive['free_gb']:g} GB** free, **{drive['used_gb']:g} GB** used."
                for drive in drives
            ]
            sections.append("Storage:\n" + "\n".join(f"- {line}" for line in storage_lines))

    if asks_ollama:
        models = (info.get("ollama") or {}).get("models") or []
        if not models:
            sections.append("Ollama: no model is currently loaded.")
        else:
            model_lines = []
            for model in models:
                name = model.get("name") or "Unknown model"
                vram = model.get("vram_gb")
                if isinstance(vram, (int, float)):
                    model_lines.append(f"**{name}** — **{vram:g} GB** VRAM")
                else:
                    model_lines.append(f"**{name}** — VRAM usage unavailable")
            sections.append("Ollama:\n" + "\n".join(f"- {line}" for line in model_lines))

    if not sections:
        return "I inspected the system, but I couldn't map that question to a supported system fact."

    return "\n".join(sections)


class Orchestrator:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager, memory):
        self.registry = registry
        self.permissions = permissions
        self.memory = memory
        self.models = ModelRouter()
        self.log = logging.getLogger("jasper.orchestrator")

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self.registry.list() if self.permissions.allowed(tool)]

    async def _execute_tool_call(self, call: dict[str, Any]) -> str:
        function = call.get("function") or {}
        name = function.get("name")
        arguments = function.get("arguments") or {}

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid arguments for tool '{name}': {exc}") from exc

        if not isinstance(arguments, dict):
            raise ValueError(f"Arguments for tool '{name}' must be an object.")

        tool = self.registry.get(name)
        self.permissions.check(tool)
        self.log.info("tool requested name=%s arguments=%s", name, arguments)

        try:
            result = tool.handler(**arguments)
            if hasattr(result, "model_dump"):
                result = result.model_dump()
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            self.log.exception("tool failed name=%s", name)
            return json.dumps({
                "error": type(exc).__name__,
                "message": str(exc),
            }, ensure_ascii=False)

    async def respond(self, user_text: str) -> str:
        self.memory.add("user", user_text)

        if _requires_system_observation(user_text):
            info = _system_observation_tool_result(self.registry, self.permissions)
            self.log.info("forced system observation for direct fact query")
            answer = _format_system_fact_answer(user_text, info)
            self.memory.add("assistant", answer)
            self.log.info("chat completed model=system-observation tool_rounds=1")
            return answer
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(
            {"role": role, "content": content}
            for role, content in self.memory.recent(MAX_HISTORY_MESSAGES)
        )

        provider, model = self.models.provider_for(user_text)
        tools = self._tool_schemas()

        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            response = await provider.chat(messages, model=model, tools=tools)
            message = response.get("message", {})
            tool_calls = message.get("tool_calls") or []

            # Preserve the assistant message, including tool_calls, exactly enough
            # for Ollama to continue the tool-calling conversation.
            messages.append(message)

            if not tool_calls:
                answer = message.get("content", "")
                self.memory.add("assistant", answer)
                self.log.info("chat completed model=%s tool_rounds=%s", model, round_number - 1)
                return answer

            for call in tool_calls:
                try:
                    name = (call.get("function") or {}).get("name", "unknown")
                    result = await self._execute_tool_call(call)
                except Exception as exc:
                    self.log.exception("tool request rejected name=%s", name)
                    result = json.dumps({
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }, ensure_ascii=False)

                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": result,
                })

        raise RuntimeError(f"Tool loop exceeded {MAX_TOOL_ROUNDS} rounds; request stopped for safety.")
