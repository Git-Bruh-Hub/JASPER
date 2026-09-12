import json
import logging
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
