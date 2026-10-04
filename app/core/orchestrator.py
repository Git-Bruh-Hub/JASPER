import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from app.core.config import MAX_HISTORY_MESSAGES
from app.memory.memory_manager import MemoryManager
from app.models.model_router import ModelRouter
from app.core.permissions import PermissionManager
from app.tools.registry import ToolRegistry
from app.tools.vision import validate_image_path
from app.knowledge.hardware import get_cpu_profile, render_cpu_explanation
from app.vision.manager import VisionManager
from app.agents import CognitiveRouter, CognitiveMode, CognitiveEngine
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.agents.adapters import PlannerAdapter, ExecutorAdapter

SYSTEM_PROMPT = """You are JASPER, a local-first personal AI assistant.
JASPER means Just Another Smart Program Executing Request.

Communication and personality:
- Be helpful, natural, calm, conversational, and easy to understand.
- Be direct and practical. Give the answer first, then useful explanation or detail.
- Adapt depth to the user's request: concise for simple questions, detailed when asked.
- Do not generate unnecessary repetition just to make an answer look detailed.
- Use clear headings, bullets, numbered lists, tables, quotes, code blocks, and other Markdown formatting when they genuinely improve readability.
- Never expose raw Markdown markers such as ###, **, or * as plain text when normal Markdown can represent the formatting.
- Do not overuse emojis, filler, or repeated follow-up offers.
- Keep a consistent, friendly assistant persona without pretending to be human or claiming feelings or experiences you do not have.
- Understand English, Bahasa Malaysia, casual Malay, slang, typos, and BM-English rojak.
- Default response language is English.
- Respond in Bahasa Malaysia when the user explicitly asks for BM/Malay, or clearly establishes BM as the desired response language.
- If the user mixes English and Bahasa Malaysia without requesting a language, default to English.
- If the user explicitly asks for a response language, follow that request for the response.
- Do not confuse the speech-recognition language with the response language: STT may use Malay (`ms`) while JASPER can still respond in English.

Accuracy:
- Do not invent facts, values, capabilities, or actions.
- Distinguish observed facts from reference specifications, assumptions, and general knowledge.
- When a local tool can directly verify a fact, use the tool instead of guessing.
- If information is uncertain or unavailable, say so clearly rather than filling the gap.
- For hardware explanations, the live system observations and exact-model reference specifications supplied in the hardware context are authoritative for this machine.
- Do not override a supplied hardware value with a remembered value.
- Do not use Intel-specific terminology for AMD CPUs. AMD Ryzen processors use SMT (Simultaneous Multithreading), not Intel's Hyper-Threading branding.
- Distinguish base clock from maximum boost clock. Never call the base clock the boost clock.
- Do not present a reference specification as a live measurement. Clearly distinguish static specifications from current usage/state.

Tool use:
- You have access to read-only local tools.
- Use a tool when the user's request requires current information from this computer.
- Do not guess information that a tool can directly verify.
- After receiving tool results, answer using those results.
- Never claim a tool ran unless its result confirms it.

Vision:
- You have a read-only image inspection tool.
- Use it ONLY when the user explicitly mentions an image file path or asks you to look at, describe, or analyze a specific image file on their computer.
- Do not guess image paths. If the user mentions an image but does not provide a path, ask them for the exact file path.
- Do not use vision for text-only questions.
- After receiving visual observations, answer using those observations. Do not add details that are not in the visual observation.

Safety:
- Never invent filesystem contents or system state.
- Do not attempt actions outside the tools provided to you.
- The current tool policy is read-only.
"""

MAX_TOOL_ROUNDS = 5

SYSTEM_FACT_PATTERNS = (
    r"\bwhat (?:cpu|processor) (?:am i|do i) (?:using|have)\b",
    r"\bwhat (?:cpu|processor) is (?:this|my)\b",
    r"\bwhat (?:gpu|graphics card|video card) (?:am i|do i) (?:using|have)\b",
    r"\bwhat (?:gpu|graphics card|video card) is (?:this|my)\b",
    r"\bhow much (?:ram|memory) .*\bdo i have\b",
    r"\bwhat (?:ram|memory) do i have\b",
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

_IMAGE_PATH_RE = re.compile(
    r"""
    (?:                           # path prefix — at least one of:
        (?<![A-Za-z])             #   NOT preceded by a letter (isolates drive)
        [A-Za-z]:[\\\/]           #   Windows drive letter  (C:\, D:/)
      | \\\\                      #   UNC path              (\\server\...)
      | (?:^|(?<=\s)|(?<=["']))   #   must follow whitespace, quote, or SOL
        [~]?\/                    #   Unix-style absolute or home-relative
    )
    \S*                           # rest of path (no spaces — may be quoted)
    \.(?:png|jpe?g|webp)          # image extension
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _requires_system_observation(text: str) -> bool:
    """Return True when the user is asking for direct facts about this live machine."""
    normalized = " ".join(text.lower().split())
    if any(re.search(pattern, normalized) for pattern in SYSTEM_FACT_PATTERNS):
        return True
    matched_categories = sum(any(term in normalized for term in terms) for terms in SYSTEM_FACT_TERMS.values())
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
    """Return True when a hardware explanation should receive live machine facts."""
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


def _grounding_context(question: str, info: dict) -> str:
    """Build a compact, authoritative hardware context for the model."""
    q = question.lower()
    observed: dict[str, Any] = {}
    asks_cpu = "cpu" in q or "processor" in q
    asks_gpu = "gpu" in q or "graphics card" in q or "video card" in q
    asks_ram = "ram" in q or "memory" in q
    asks_storage = "storage" in q or "disk space" in q or "drive" in q
    asks_ollama = "ollama" in q
    if asks_cpu:
        observed["live_observations"] = {
            "cpu_name": info.get("cpu"),
            "cpu_details": info.get("cpu_details", {}),
            "physical_cores": info.get("cpu_physical_cores"),
            "logical_processors": info.get("cpu_logical_cores"),
        }
        reference = get_cpu_profile(info.get("cpu"))
        if reference:
            observed["reference_specifications_for_this_exact_model"] = reference
    if asks_gpu:
        observed["gpu"] = info.get("gpu") or []
    if asks_ram:
        observed["ram_total_gb"] = info.get("ram_total_gb")
        observed["ram_available_gb"] = info.get("ram_available_gb")
        observed["ram_used_percent"] = info.get("ram_used_percent")
    if asks_storage:
        observed["storage"] = info.get("storage") or []
    if asks_ollama:
        observed["ollama"] = info.get("ollama") or {}
    return (
        "AUTHORITATIVE HARDWARE CONTEXT. Use the supplied values exactly. Live observations describe this computer right now. "
        "Reference specifications describe the exact identified CPU model. Do not substitute remembered values. "
        "Do not call a base clock a boost clock. For AMD Ryzen, call the 12-thread capability SMT, not Hyper-Threading. "
        "Current RAM usage is a live state value, not a CPU specification.\n\n"
        + json.dumps(observed, ensure_ascii=False, indent=2, default=str)
    )


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
            sections.append(f"RAM: **{total:g} GB** total, **{available:g} GB** available ({used:g}% used).")
        else:
            sections.append("RAM: I couldn't determine it from the system inspection tool.")
    if asks_storage:
        drives = info.get("storage") or []
        if not drives:
            sections.append("Storage: I couldn't detect any mounted storage volumes.")
        else:
            sections.append("Storage:\n" + "\n".join(
                f"- **{drive['path']}** — **{drive['total_gb']:g} GB** total, **{drive['free_gb']:g} GB** free, **{drive['used_gb']:g} GB** used."
                for drive in drives
            ))
    if asks_ollama:
        models = (info.get("ollama") or {}).get("models") or []
        if not models:
            sections.append("Ollama: no model is currently loaded.")
        else:
            sections.append("Ollama:\n" + "\n".join(
                f"- **{model.get('name', 'Unknown model')}** — **{model.get('vram_gb', 'VRAM usage unavailable')} GB** VRAM"
                for model in models
            ))
    return "\n".join(sections) if sections else "I inspected the system, but I couldn't map that question to a supported system fact."


def _response_budget(text: str) -> int:
    """Choose a generation budget from the user's requested depth and task type."""
    normalized = " ".join(text.lower().split())
    hardware_explanation = any(term in normalized for term in ("cpu", "processor", "gpu", "graphics card", "ram", "memory", "storage")) and any(
        term in normalized for term in ("explain", "describe", "detail", "detailed", "how does", "what does")
    )
    if hardware_explanation and not any(term in normalized for term in ("in detail", "thorough", "comprehensive", "step by step", "deep dive")):
        return 640
    if any(term in normalized for term in ("in detail", "detailed", "thorough", "deep dive", "comprehensive", "step by step", "explain fully")):
        return 1024
    if any(term in normalized for term in ("analyze", "compare", "debug", "design", "plan", "why is", "how can i")):
        return 1024
    if any(term in normalized for term in ("recommend", "recommendation", "best", "good for", "which .* should", "what .* should i buy")):
        return 640
    if len(normalized.split()) <= 12:
        return 512
    return 640


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionManager,
        memory,
        vision: VisionManager | None = None,
        multi_agent_coordinator: MultiAgentCoordinator | None = None,
    ):
        self.registry = registry
        self.permissions = permissions
        self.memory = memory
        self.vision = vision
        self.multi_agent_coordinator = multi_agent_coordinator
        self.memory_manager = MemoryManager(memory)
        self.models = ModelRouter()
        self.cognitive_router = CognitiveRouter()
        self.engine = CognitiveEngine(self._run_model_loop)
        self.log = logging.getLogger("jasper.orchestrator")

    def _tool_schemas(self, user_text: str = "") -> list[dict[str, Any]]:
        """Build tool schemas for the current turn.

        ``inspect_image`` is only offered to the model when the user's message
        contains an explicit local image file path (e.g. ``C:\\photo.png``).
        Generic mentions of "image", "photo", or "screenshot" without a path
        do **not** surface the tool, preventing the model from inventing paths.
        """
        image_relevant = bool(_IMAGE_PATH_RE.search(user_text))
        return [
            tool.schema()
            for tool in self.registry.list()
            if self.permissions.allowed(tool)
            and (tool.name != "inspect_image" or image_relevant)
        ]

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
            if asyncio.iscoroutine(result):
                result = await result
            if hasattr(result, "model_dump"):
                result = result.model_dump()
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            self.log.exception("tool failed name=%s", name)
            return json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False)

    async def _emit_local_response(self, answer: str, on_chunk: Callable[[str], None] | None) -> None:
        if not on_chunk:
            return
        parts = re.split(r"(?<=\n)(?=\n)|(?<=\.) (?=[A-Z#])", answer)
        parts = [part for part in parts if part]
        if len(parts) <= 1:
            on_chunk(answer)
            return
        import asyncio
        for part in parts:
            on_chunk(part)
            await asyncio.sleep(0.035)

    async def respond(
        self,
        user_text: str,
        on_chunk: Callable[[str], None] | None = None,
        image_path: str | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> str:
        self.memory.add("user", user_text)
        memory_command = self.memory_manager.parse_command(user_text)
        if memory_command is not None:
            answer = self.memory_manager.handle_command(memory_command)
            self.memory.add("assistant", answer)
            await self._emit_local_response(answer, on_chunk)
            self.log.info("memory command handled action=%s", memory_command.action)
            return answer
        if _requires_system_observation(user_text):
            info = _system_observation_tool_result(self.registry, self.permissions)
            self.log.info("forced system observation for direct fact query")
            answer = _format_system_fact_answer(user_text, info)
            self.memory.add("assistant", answer)
            await self._emit_local_response(answer, on_chunk)
            self.log.info("chat completed model=system-observation tool_rounds=1")
            return answer

        normalized = " ".join(user_text.lower().split())
        if _requires_system_grounding(user_text) and ("cpu" in normalized or "processor" in normalized):
            info = _system_observation_tool_result(self.registry, self.permissions)
            answer = render_cpu_explanation(user_text, info)
            if answer is not None:
                self.memory.add("assistant", answer)
                await self._emit_local_response(answer, on_chunk)
                self.log.info("chat completed model=local-verified-hardware tool_rounds=1")
                return answer

        # --- Vision-to-text bridge (v0.5.2 / hardened) ----------------------
        # When the user attaches an image, validate and analyze it FIRST.
        # If validation or analysis fails the exception propagates immediately:
        # the normal text-LLM is never called and the Worker's error-signal path
        # displays the failure to the user.  This is intentional — JASPER must
        # not answer an image question when it cannot see the image.
        vision_observation: str | None = None
        if image_path and self.vision:
            validated = validate_image_path(image_path)
            result = await self.vision.analyze(validated)
            vision_observation = result.answer
            self.log.info(
                "vision bridge completed path=%s chars=%s",
                validated.name,
                len(vision_observation),
            )
        # ----------------------------------------------------------------------

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        memory_context = self.memory_manager.context_for(user_text)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        messages.extend({"role": role, "content": content} for role, content in self.memory.recent(MAX_HISTORY_MESSAGES))
        if _requires_system_grounding(user_text):
            info = _system_observation_tool_result(self.registry, self.permissions)
            messages.append({"role": "system", "content": _grounding_context(user_text, info)})
            self.log.info("added live system grounding for hardware explanation")
        if vision_observation:
            filename = Path(image_path).name if image_path else "attached image"
            messages.append({
                "role": "system",
                "content": (
                    f"VISION OBSERVATION for the image the user attached "
                    f"({filename}):\n\n{vision_observation}\n\n"
                    "Use only the above visual observations when answering questions "
                    "about the attached image. Do not add details not present in the "
                    "observation."
                ),
            })
        mode = self.cognitive_router.route(user_text)

        if mode == CognitiveMode.AUTONOMOUS:
            if not self.multi_agent_coordinator:
                # Fail safely without falling back to unrestricted path
                return "Autonomous mode is not enabled."
            
            clean_text = re.sub(r'(?i)^/auto\s*', '', user_text).strip()
            
            planner_adapter = PlannerAdapter(self.models, self.registry)
            executor_adapter = ExecutorAdapter(self.models, self.registry)
            
            answer = await self.multi_agent_coordinator.run_multi_agent(
                planner_callable=planner_adapter,
                executor_callable=executor_adapter,
                user_text=clean_text,
                cancel_callback=cancel_callback,
            )
            self.memory.add("assistant", answer)
            await self._emit_local_response(answer, on_chunk)
            return answer

        answer = await self.engine.run(mode, messages, user_text, on_chunk, cancel_callback=cancel_callback)

        self.memory.add("assistant", answer)
        return answer

    async def _run_model_loop(self, messages: list[dict[str, Any]], system_prompt: str | None, use_tools: bool, mode: CognitiveMode, user_text: str, on_chunk: Callable[[str], None] | None = None, cancel_callback: Callable[[], bool] | None = None) -> str:
        provider, model = self.models.provider_for(mode)

        # Augment system prompt if provided
        loop_messages = list(messages)
        if system_prompt:
            # Append role prompt to core JASPER prompt
            if loop_messages and loop_messages[0]["role"] == "system":
                loop_messages[0] = {
                    "role": "system",
                    "content": f"{loop_messages[0]['content']}\n\n{system_prompt}"
                }
            else:
                loop_messages.insert(0, {"role": "system", "content": system_prompt})

        tools = self._tool_schemas(user_text) if use_tools else []
        max_output_tokens = _response_budget(user_text)
        self.log.info("response budget=%s tokens", max_output_tokens)

        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            if cancel_callback and cancel_callback():
                raise asyncio.CancelledError()

            if on_chunk is None:
                response = await provider.chat(loop_messages, model=model, tools=tools, max_output_tokens=max_output_tokens, cancel_callback=cancel_callback)
                message = response.get("message", {})
            else:
                message, response = await self._stream_model_round(provider, loop_messages, model=model, tools=tools, max_output_tokens=max_output_tokens, on_chunk=on_chunk, cancel_callback=cancel_callback)

            if cancel_callback and cancel_callback():
                raise asyncio.CancelledError()

            tool_calls = message.get("tool_calls") or []
            loop_messages.append(message)
            if not tool_calls:
                answer = message.get("content", "")
                self.log.info("chat completed model=%s tool_rounds=%s", model, round_number - 1)
                return answer
            for call in tool_calls:
                try:
                    name = (call.get("function") or {}).get("name", "unknown")
                    result = await self._execute_tool_call(call)
                except Exception as exc:
                    self.log.exception("tool request rejected name=%s", name)
                    result = json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False)
                loop_messages.append({"role": "tool", "tool_name": name, "content": result})
        raise RuntimeError(f"Tool loop exceeded {MAX_TOOL_ROUNDS} rounds; request stopped for safety.")

    async def _stream_model_round(self, provider, messages: list[dict[str, Any]], *, model: str, tools: list[dict[str, Any]], max_output_tokens: int, on_chunk: Callable[[str], None], cancel_callback: Callable[[], bool] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        content_parts: list[str] = []
        final_chunk: dict[str, Any] = {}
        final_tool_calls: list[dict[str, Any]] = []
        async for chunk in provider.stream_chat(messages, model=model, tools=tools, max_output_tokens=max_output_tokens, cancel_callback=cancel_callback):
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
