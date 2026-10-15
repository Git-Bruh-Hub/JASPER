"""Adapters for translating LLM output into JASPER v0.7 contracts.

These adapters enforce the security boundary by ignoring any authority
claims (risk, scope, approval) forged by the LLM, and reconstructing them
strictly from the authoritative ToolRegistry.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    DisagreementFeedback,
    PermissionScope,
    PlannerResult,
    PlannerTask,
    ProposedAction,
)
from app.agents.router import CognitiveMode
from app.core.response import sanitize_thinking_tags
from app.models.model_router import ModelRouter
from app.tools.registry import Risk, ToolRegistry


def _map_approval(risk: Risk) -> ApprovalRequirement:
    """Map tool risk strictly to system approval policy."""
    if risk == Risk.READ:
        return ApprovalRequirement.NEVER
    return ApprovalRequirement.ALWAYS


def _parse_llm_actions(
    tool_calls: list[dict[str, Any]], registry: ToolRegistry
) -> list[ProposedAction]:
    """Parse raw LLM tool calls into safe ProposedActions."""
    actions = []
    for call in tool_calls:
        # Some models nest inside 'function'
        func = call.get("function", call)
        name = func.get("name", "")
        args = func.get("arguments", {})

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        if not name:
            continue

        try:
            tool = registry.get(name)
        except KeyError:
            # Skip unknown tools; let verification or retry handle it
            continue

        # Derive operation from tool name and resource scope from args if present
        operation = name

        # Normalize arguments according to tool schema (e.g. integer parameters)
        param_props = tool.parameters.get("properties", {}) if isinstance(tool.parameters, dict) else {}
        for param_name, param_schema in param_props.items():
            if param_name in args and param_schema.get("type") == "integer":
                try:
                    args[param_name] = int(args[param_name])
                except (ValueError, TypeError):
                    pass
        
        # Attempt to infer a resource scope from common argument names, default to "global"
        resource_scope = args.get("path") or args.get("url") or args.get("key") or "global"

        scope = PermissionScope(
            risk=tool.risk.value,
            resource_scope=str(resource_scope),
            operation=operation,
            approval_requirement=_map_approval(tool.risk),
        )

        actions.append(
            ProposedAction(
                tool_name=name,
                arguments=args,
                scope=scope,
                rationale="Autonomous LLM proposal",
            )
        )
    return actions


class PlannerAdapter:
    """Adapts the Planner LLM invocation to the v0.7 PlannerTask contract."""

    def __init__(self, models: ModelRouter, registry: ToolRegistry):
        self.models = models
        self.registry = registry

    async def __call__(
        self, task: PlannerTask, cancel_callback: Callable[[], bool] | None = None
    ) -> AgentResult:
        system_prompt = (
            "You are the JASPER Planner agent.\n"
            "Analyze the user request and any observations from previous action results.\n"
            "If more information or actions are needed, propose tool calls for the Executor to run.\n"
            "Guidelines for web tasks:\n"
            "- To search the web: call `browser_search(query)` or `browser_navigate(url)`.\n"
            "- To fill a search bar or form: call `browser_type(index, text)`.\n"
            "- To click a search result or link: call `browser_click(index)`.\n"
            "- To read page content: call `browser_read_text()`.\n"
            "- Once you have enough information to answer the user's request, do NOT call any tools. "
            "Provide your complete, detailed answer directly in your response."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task.user_text},
        ]

        tools = [t.schema() for t in self.registry.list()]

        # Autonomous mode uses DEEP model for planning
        provider, model_name = self.models.provider_for(CognitiveMode.DEEP)

        response = await provider.chat(
            messages=messages,
            model=model_name,
            tools=tools,
            cancel_callback=cancel_callback,
        )

        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        actions = _parse_llm_actions(tool_calls, self.registry)
        clean_content = sanitize_thinking_tags(content)

        return AgentResult(
            agent_id="planner",
            observations=[clean_content] if clean_content else [],
            proposed_actions=actions,
        )


class ExecutorAdapter:
    """Adapts the Executor LLM invocation to the v0.7 PlannerResult contract."""

    def __init__(self, models: ModelRouter, registry: ToolRegistry):
        self.models = models
        self.registry = registry

    async def __call__(
        self,
        plan: PlannerResult,
        disagreement: DisagreementFeedback | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> AgentResult:
        planner_actions = plan.planner_result.proposed_actions
        action_descriptions = [
            f"- `{a.tool_name}` with arguments `{json.dumps(a.arguments)}`"
            for a in planner_actions
        ]

        system_prompt = (
            "You are the JASPER Executor agent.\n"
            "Execute the user's request strictly following the Planner's proposed tools.\n"
            "You must output valid tool calls."
        )

        if action_descriptions:
            system_prompt += (
                f"\n\nThe Planner evaluated the current state and decided on the following planned action(s):\n"
                + "\n".join(action_descriptions)
                + "\n\nYou MUST call the exact tool(s) with the exact arguments specified by the Planner above."
            )

        if disagreement:
            excess_details = [
                f"{a.tool_name} (excess: {a.excess_count})"
                for a in disagreement.excess_actions
            ]
            planner_details = [a.tool_name for a in disagreement.planner_actions]
            system_prompt += (
                f"\n\nWARNING: In your previous attempt, you proposed actions "
                f"({', '.join(excess_details)}) that exceeded the Planner's bounds.\n"
                f"You MUST restrict your actions to: {', '.join(planner_details)}."
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": plan.user_text},
        ]

        # The Executor has context of what the planner output
        planner_content = "\n".join(plan.planner_result.observations)
        if planner_content:
            messages.append({"role": "assistant", "content": f"Planner thoughts: {planner_content}"})

        if action_descriptions:
            messages.append({
                "role": "assistant",
                "content": f"Planned action(s) to execute:\n" + "\n".join(action_descriptions),
            })
            messages.append({
                "role": "user",
                "content": "Proceed and invoke the exact planned tool call(s) now.",
            })

        tools = [t.schema() for t in self.registry.list()]
        
        provider, model_name = self.models.provider_for(CognitiveMode.DEEP)

        response = await provider.chat(
            messages=messages,
            model=model_name,
            tools=tools,
            cancel_callback=cancel_callback,
        )

        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        actions = _parse_llm_actions(tool_calls, self.registry)
        clean_content = sanitize_thinking_tags(content)

        return AgentResult(
            agent_id="executor",
            observations=[clean_content] if clean_content else [],
            proposed_actions=actions,
        )
