import json
import logging
import re
from typing import Any, Callable

from app.core.config import MAX_HISTORY_MESSAGES
from app.memory.memory_manager import MemoryManager
from app.models.model_router import ModelRouter
from app.core.permissions import PermissionManager
from app.tools.registry import ToolRegistry

SYSTEM_PROMPT = """You are JASPER, a local-first personal AI assistant.
JASPER means Just Another Smart Program Executing Request.

Communication:
- Be helpful, natural, calm, conversational, and practical.
- Give the answer first, then useful explanation or detail.
- Adapt depth to the request.
- Use Markdown when it improves readability.
- Default response language is English; use Bahasa Malaysia when explicitly requested or clearly established.
- Understand English, Bahasa Malaysia, casual Malay, slang, typos, and BM-English rojak.

Accuracy:
- Do not invent facts, values, capabilities, or actions.
- Distinguish live observations from reference specifications and general knowledge.
- When a local tool can verify a fact, use it instead of guessing.
- For hardware explanations, supplied live observations and exact-model reference specifications are authoritative.
- Do not override supplied hardware values with remembered values.
- AMD Ryzen uses SMT (Simultaneous Multithreading), not Intel's Hyper-Threading branding.
- Distinguish base clock from maximum boost clock.
- Do not present a reference specification as a live measurement.

Tool use:
- You have read-only local tools.
- Use tools when current information from this computer is required.
- Never claim a tool ran unless its result confirms it.

Safety:
- Never invent filesystem contents or system state.
- Do not attempt actions outside the tools provided.
- The current tool policy is read-only.
"""

MAX_TOOL_ROUNDS = 5

# These are intentionally conservative. Direct fact questions are answered by JASPER's
# observation layer, not by the language model.
SYSTEM_FACT_PATTERNS = (
    r"\bwhat (?:is|are) (?:my|this) (?:cpu|processor)\b",
    r"\bwhat (?:cpu|processor) (?:am i|do i) (?:using|have)\b",
    r"\bwhat (?:is|are) (?:my|this) (?:gpu|graphics card|video card)\b",
    r"\bwhat (?:gpu|graphics card|video card) (?:am i|do i) (?:using|have)\b",
    r"\bhow much (?:ram|memory) .*\bdo i have\b",
    r"\bwhat (?:ram|memory) .*\bdo i have\b",
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
    "my", "i have", "am i using", "do i have", "currently", "running", "loaded", "using",
    "specs", "system information", "system info", "pc information", "pc info",
)

SYSTEM_GROUNDING_TERMS = (
    "explain", "describe", "details", "detailed", "specification", "specifications",
    "about my", "tell me about my", "what can my", "how does my",
)


def _requires_system_observation(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if any(re.search(pattern, normalized) for pattern in SYSTEM_FACT_PATTERNS):
        return True

    matched_categories = sum(
        any(term in normalized for term in terms) for terms in SYSTEM_FACT_TERMS.values()
    )
    has_live_context = any(
        re.search(rf"\b{re.escape(context)}\b", normalized) if " " not in context else context in normalized
        for context in SYSTEM_LIVE_CONTEXT
    )
    if matched_categories >= 2 and has_live_context:
        return True
    return bool(
        re.search(r"\b(what|tell me|show me|give me)\b.*\b(my|this)\b.*\b(pc|computer|system|hardware)\b", normalized)
        or re.search(r"\b(my|this)\b.*\b(pc|computer|system|hardware)\b.*\b(specs|information|info)\b", normalized)
    )


def _requires_system_grounding(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    has_hardware = any(any(term in normalized for term in terms) for terms in SYSTEM_FACT_TERMS.values())
    has_live_context = any(
        re.search(rf"\b{re.escape(context)}\b", normalized) if " " not in context else context in normalized
        for context in SYSTEM_LIVE_CONTEXT
    )
    return has_hardware and has_live_context and any(term in normalized for term in SYSTEM_GROUNDING_TERMS)


def _system_observation_tool_result(registry: ToolRegistry, permissions: PermissionManager) -> dict:
    tool = registry.get("get_system_info")
    permissions.check(tool)
    return tool.handler()


def _cpu_reference_facts(info: dict) -> dict:
    name = str(info.get("cpu") or "").lower()
    if "ryzen 5 5600x" not in name:
        return {}
    return {
        "model": "AMD Ryzen 5 5600X",
        "architecture": "Zen 3",
        "cores": 6,
        "threads": 12,
        "threading_technology": "AMD SMT (Simultaneous Multithreading)",
        "socket": "AM4",
        "tdp_w": 65,
        "base_clock_ghz": 3.7,
        "max_boost_clock_ghz": 4.6,
        "l2_cache_mb": 3,
        "l3_cache_mb": 32,
        "total_cache_mb": 35,
    }


def _grounding_context(question: str, info: dict) -> str:
    q = question.lower()
    observed: dict[str, Any] = {}
    if "cpu" in q or "processor" in q:
        observed["live_observations"] = {
            "cpu_name": info.get("cpu"),
            "cpu_details": info.get("cpu_details", {}),
            "physical_cores": info.get("cpu_physical_cores"),
            "logical_processors": info.get("cpu_logical_cores"),
        }
        reference = _cpu_reference_facts(info)
        if reference:
            observed["reference_specifications_for_this_exact_model"] = reference
    if "gpu" in q or "graphics card" in q or "video card" in q:
        observed["gpu"] = info.get("gpu") or []
    if "ram" in q or "memory" in q:
        observed["ram_total_gb"] = info.get("ram_total_gb")
        observed["ram_available_gb"] = info.get("ram_available_gb")
        observed["ram_used_percent"] = info.get("ram_used_percent")
    if "storage" in q or "disk space" in q or "drive" in q:
        observed["storage"] = info.get("storage") or []
    if "ollama" in q:
        observed["ollama"] = info.get("ollama") or {}
    return (
        "AUTHORITATIVE HARDWARE CONTEXT. Use supplied values exactly. Live observations describe this computer now. "
        "Reference specifications describe the exact identified CPU model. Do not substitute remembered values. "
        "Do not call a base clock a boost clock. For AMD Ryzen, call 12-thread capability SMT, not Hyper-Threading. "
        "Current RAM usage is a live state value, not a CPU specification.\n\n"
        + json.dumps(observed, ensure_ascii=False, indent=2, default=str)
    )


def _format_system_fact_answer(question: str, info: dict) -> str:
    """Format deterministic system facts without an LLM."""
    q = question.lower()
    sections: list[str] = []

    asks_cpu = "cpu" in q or "processor" in q
    asks_gpu = "gpu" in q or "graphics card" in q or "video card" in q
    asks_ram = "ram" in q or "memory" in q
    asks_storage = "storage" in q or "disk space" in q or "drive" in q
    asks_ollama = "ollama" in q and ("model" in q or "vram" in q)

    if asks_cpu:
        cpu = info.get("cpu")
        sections.append(f"Your CPU is **{cpu}**." if cpu else "I couldn't determine your CPU from the system inspection tool.")

    if asks_gpu:
        gpus = info.get("gpu") or []
        if not gpus:
            sections.append("I couldn't detect an NVIDIA GPU from the system inspection tool.")
        else:
            for gpu in gpus:
                name = gpu.get("name") or "Unknown GPU"
                vram = gpu.get("vram_total_gb")
                suffix = f" with **{vram:g} GB VRAM**." if isinstance(vram, (int, float)) else "."
                sections.append(f"Your GPU is **{name}**{suffix}")

    if asks_ram:
        total = info.get("ram_total_gb")
        available = info.get("ram_available_gb")
        used = info.get("ram_used_percent")
        if isinstance(total, (int, float)):
            sections.append(f"You have **{total:g} GB RAM** total, with **{available:g} GB** available ({used:g}% used).")
        else:
            sections.append("I couldn't determine your RAM from the system inspection tool.")

    if asks_storage:
        drives = info.get("storage") or []
        if not drives:
            sections.append("I couldn't detect any mounted storage volumes.")
        else:
            sections.append("Storage:\n" + "\n".join(
                f"- **{d['path']}** — **{d['total_gb']:g} GB** total, **{d['free_gb']:g} GB** free, **{d['used_gb']:g} GB** used."
                for d in drives
            ))

    if asks_ollama:
        models = (info.get("ollama") or {}).get("models") or []
        if not models:
            sections.append("Ollama: no model is currently loaded.")
        else:
            lines = []
            for model in models:
                name = model.get("name") or "Unknown model"
                vram = model.get("vram_gb")
                lines.append(f"- **{name}** — **{vram:g} GB** VRAM" if isinstance(vram, (int, float)) else f"- **{name}** — VRAM usage unavailable")
            sections.append("Ollama:\n" + "\n".join(lines))

    return "\n\n".join(sections) if sections else "I inspected the system, but I couldn't map that question to a supported system fact."


def _response_budget(text: str) -> int:
    normalized = " ".join(text.lower().split())
    detailed = any(p in normalized for p in ("in detail", "detailed", "thorough", "deep dive", "comprehensive", "step by step", "explain fully"))
    complex_request = any(p in normalized for p in ("analyze", "compare", "debug", "design", "plan", "why is", "how can i"))
    if detailed or complex_request:
        return 1024
    if len(normalized.split()) <= 12:
        return 384
    return 640


class Orchestrator:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager, memory):
        self.registry = registry
        self.permissions = permissions
        self.memory = memory
        self.memory_manager = MemoryManager(memory)
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
            return json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False)

    async def respond(self, user_text: str, on_chunk: Callable[[str], None] | None = None) -> str:
        self.memory.add("user", user_text)
        memory_command = self.memory_manager.parse_command(user_text)
        if memory_command is not None:
            answer = self.memory_manager.handle_command(memory_command)
            self.memory.add("assistant", answer)
            if on_chunk:
                on_chunk(answer)
            self.log.info("memory command handled action=%s", memory_command.action)
            return answer

        # Deterministic current-system facts never go through the LLM.
        if _requires_system_observation(user_text):
            info = _system_observation_tool_result(self.registry, self.permissions)
            self.log.info("forced system observation for direct fact query")
            answer = _format_system_fact_answer(user_text, info)
            self.memory.add("assistant", answer)
            if on_chunk:
                on_chunk(answer)
            self.log.info("chat completed model=system-observation tool_rounds=1")
            return answer

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        memory_context = self.memory_manager.context_for(user_text)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        messages.extend({"role": role, "content": content} for role, content in self.memory.recent(MAX_HISTORY_MESSAGES))

        if _requires_system_grounding(user_text):
            info = _system_observation_tool_result(self.registry, self.permissions)
            messages.append({"role": "system", "content": _grounding_context(user_text, info)})
            self.log.info("added live system grounding for hardware explanation")

        provider, model = self.models.provider_for(user_text)
        tools = self._tool_schemas()
        max_output_tokens = _response_budget(user_text)
        self.log.info("response budget=%s tokens", max_output_tokens)

        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            if on_chunk is None:
                response = await provider.chat(messages, model=model, tools=tools, max_output_tokens=max_output_tokens)
                message = response.get("message", {})
            else:
                message, response = await self._stream_model_round(
                    provider, messages, model=model, tools=tools,
                    max_output_tokens=max_output_tokens, on_chunk=on_chunk,
                )

            tool_calls = message.get("tool_calls") or []
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
                    result = json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False)
                messages.append({"role": "tool", "tool_name": name, "content": result})

        raise RuntimeError(f"Tool loop exceeded {MAX_TOOL_ROUNDS} rounds; request stopped for safety.")

    async def _stream_model_round(
        self,
        provider,
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[dict[str, Any]],
        max_output_tokens: int,
        on_chunk: Callable[[str], None],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        content_parts: list[str] = []
        final_chunk: dict[str, Any] = {}
        final_tool_calls: list[dict[str, Any]] = []

        async for chunk in provider.stream_chat(
            messages, model=model, tools=tools, max_output_tokens=max_output_tokens
        ):
            final_chunk = chunk
            message = chunk.get("message") or {}
            piece = message.get("content") or ""
            if piece:
                content_parts.append(piece)
                on_chunk(piece)
            if message.get("tool_calls"):
                final_tool_calls = message.get("tool_calls") or []

        final_message = dict(final_chunk.get("message") or {})
        if content_parts:
            final_message["content"] = "".join(content_parts)
        if final_tool_calls:
            final_message["tool_calls"] = final_tool_calls
        return final_message, final_chunk
