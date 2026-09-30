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
            "Analyze the request and propose a plan by calling the required tools.\n"
            "Do NOT execute the plan. Return ONLY the tool calls you want the Executor to use.\n"
            "You must output valid tool calls."
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

        return AgentResult(
            agent_id="planner",
            observations=[content] if content else [],
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
        system_prompt = (
            "You are the JASPER Executor agent.\n"
            "Execute the user's request strictly following the Planner's proposed tools.\n"
            "You must output valid tool calls."
        )

        if disagreement:
            system_prompt += (
                f"\n\nWARNING: In your previous attempt, you used tools "
                f"({', '.join(disagreement.unexpected_tools)}) that were NOT authorized by the Planner.\n"
                f"You MUST restrict your tools to: {', '.join(disagreement.planner_tools)}."
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": plan.user_text},
        ]

        # The Executor has context of what the planner output
        planner_content = "\n".join(plan.planner_result.observations)
        if planner_content:
            messages.append({"role": "assistant", "content": f"Planner thoughts: {planner_content}"})

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

        return AgentResult(
            agent_id="executor",
            observations=[content] if content else [],
            proposed_actions=actions,
        )
