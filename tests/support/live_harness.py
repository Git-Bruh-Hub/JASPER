"""tests/support/live_harness.py — Isolated Live-Model Test Harness for JASPER.

This harness provides a strictly isolated, opt-in validation environment for
evaluating local Ollama models (such as `qwen3:14b`) through JASPER's multi-agent
coordinator and approval bridge.

Safety & Isolation Invariants:
1. Hermetic Registry: Never calls `build_registry()`; constructs a fresh, minimal
   registry with only allowed tools.
2. Two Mutually Exclusive Configurations:
   - "read_only": Contains ONLY the verified read-only `get_system_info` tool.
   - "approval": Contains ONLY an in-memory `mock_safe_action` requiring explicit approval.
3. Strict Containment: The mock tool has zero filesystem, network, subprocess, or
   credential access. It operates purely in memory and records its invocations.
4. Fail-Closed Boundaries:
   - Unknown tools proposed by LLMs are dropped by `_parse_llm_actions` and denied by `ScopedPermissionManager`.
   - Denied approvals halt tool execution immediately with zero handler invocations.
   - Bounded execution timeouts and coordinator budgets prevent infinite loops.
5. Normal Desktop Invariance: Does NOT touch `app/desktop.py`. Default desktop startup
   remains fail-closed (`coordinator=None`).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from app.agents.adapters import ExecutorAdapter, PlannerAdapter
from app.agents.coordinator import CoordinatorBudget
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.core.config import JASPER_MODEL, OLLAMA_HOST
from app.core.orchestrator import Orchestrator
from app.core.permissions import PermissionManager
from app.core.scoped_permissions import ScopedPermissionManager
from app.memory.sqlite_memory import SQLiteMemory
from app.models.model_router import ModelRouter
from app.tools.registry import Risk, Tool, ToolRegistry
from app.tools.system import get_system_info
from app.ui.worker import JasperWorker


class HarnessMode(str, Enum):
    READ_ONLY = "read_only"
    APPROVAL = "approval"


@dataclass
class MockActionTracker:
    """In-memory call tracker for the safe mock action."""

    call_count: int = 0
    recorded_calls: list[dict[str, Any]] = field(default_factory=list)

    def handle(self, **kwargs: Any) -> dict[str, Any]:
        """Harmless in-memory handler with zero external side effects."""
        self.call_count += 1
        self.recorded_calls.append(dict(kwargs))
        return {
            "status": "success",
            "message": "Harmless mock action executed in memory.",
            "call_count": self.call_count,
        }

    def reset(self) -> None:
        self.call_count = 0
        self.recorded_calls.clear()


def build_isolated_registry(
    mode: HarnessMode | Literal["read_only", "approval"],
) -> tuple[ToolRegistry, MockActionTracker | None]:
    """Create a hermetic ToolRegistry containing ONLY the tools for the selected mode."""
    mode_val = HarnessMode(mode)
    registry = ToolRegistry()

    if mode_val == HarnessMode.READ_ONLY:
        registry.register(
            Tool(
                name="get_system_info",
                description="Read non-sensitive local system hardware and OS information.",
                risk=Risk.READ,
                handler=get_system_info,
                parameters={"type": "object", "properties": {}},
            )
        )
        return registry, None

    if mode_val == HarnessMode.APPROVAL:
        tracker = MockActionTracker()
        registry.register(
            Tool(
                name="mock_safe_action",
                description=(
                    "A harmless in-memory test action that requires user approval. "
                    "Does not access filesystem, network, subprocesses, or credentials."
                ),
                risk=Risk.WRITE,
                handler=tracker.handle,
                parameters={
                    "type": "object",
                    "properties": {
                        "payload": {"type": "string", "description": "Harmless test payload"},
                    },
                },
            )
        )
        return registry, tracker

    raise ValueError(f"Unsupported harness mode: {mode}")


def build_isolated_coordinator(
    registry: ToolRegistry,
    mode: HarnessMode | Literal["read_only", "approval"],
    approval_notifier: Callable[..., Any] | None = None,
    workspace_root: Path | None = None,
) -> MultiAgentCoordinator:
    """Build a MultiAgentCoordinator wired strictly to the isolated registry and permissions."""
    mode_val = HarnessMode(mode)
    allowed_risks = (
        frozenset({Risk.READ, Risk.WRITE})
        if mode_val == HarnessMode.APPROVAL
        else frozenset({Risk.READ})
    )
    permissions = ScopedPermissionManager(
        workspace_root=workspace_root,
        allowed_risks=allowed_risks,
        actor="live_test_harness",
    )
    budget = CoordinatorBudget(
        max_agent_rounds=3,
        max_tool_calls=2,
        max_approval_requests=2,
    )
    coordinator = MultiAgentCoordinator(
        registry=registry,
        permissions=permissions,
        budget=budget,
        approval_notifier=approval_notifier,
        workspace_root=workspace_root,
    )
    return coordinator


def build_isolated_worker(
    coordinator: MultiAgentCoordinator,
) -> JasperWorker:
    """Create a JasperWorker configured strictly with the isolated coordinator."""
    worker = JasperWorker(coordinator=coordinator)
    return worker


def build_isolated_orchestrator(
    registry: ToolRegistry,
    coordinator: MultiAgentCoordinator,
    models: ModelRouter | None = None,
) -> Orchestrator:
    """Create an Orchestrator wired to the isolated registry and coordinator."""
    models_router = models or ModelRouter()
    planner = PlannerAdapter(models_router, registry)
    executor = ExecutorAdapter(models_router, registry)
    orchestrator = Orchestrator(
        registry=registry,
        permissions=PermissionManager(),
        memory=SQLiteMemory(),
        multi_agent_coordinator=coordinator,
        planner_callable=planner,
        executor_callable=executor,
    )
    return orchestrator


async def run_isolated_live_test(
    mode: HarnessMode | Literal["read_only", "approval"],
    user_prompt: str,
    decision: Literal["allow", "deny", "timeout"] = "allow",
    gate_timeout: float = 15.0,
    overall_timeout: float = 45.0,
) -> dict[str, Any]:
    """Execute an opt-in live model test through the isolated harness.

    This function requires a running Ollama service with `qwen3:14b`.
    It must ONLY be called when explicitly invoked by the user.
    """
    mode_val = HarnessMode(mode)
    registry, tracker = build_isolated_registry(mode_val)

    decisions_log: list[tuple[str, bool]] = []
    active_gate_id: str | None = None

    def approval_callback(request: Any) -> None:
        nonlocal active_gate_id
        active_gate_id = request.gate_id
        loop = asyncio.get_running_loop()
        if decision == "allow":
            loop.call_soon(coordinator.resolve_approval, request.gate_id, True)
            decisions_log.append((request.gate_id, True))
        elif decision == "deny":
            loop.call_soon(coordinator.resolve_approval, request.gate_id, False)
            decisions_log.append((request.gate_id, False))
        elif decision == "timeout":
            # Do not resolve; let gate time out
            pass

    coordinator = build_isolated_coordinator(
        registry=registry,
        mode=mode_val,
        approval_notifier=approval_callback,
    )
    orchestrator = build_isolated_orchestrator(
        registry=registry,
        coordinator=coordinator,
    )

    clean_prompt = user_prompt if user_prompt.startswith("/auto") else f"/auto {user_prompt}"

    try:
        response = await asyncio.wait_for(
            orchestrator.respond(clean_prompt),
            timeout=overall_timeout,
        )
    except asyncio.TimeoutError:
        response = "[TIMED_OUT]"
    except PermissionError as exc:
        response = f"[DENIED] {exc}"
    except Exception as exc:
        response = f"[{type(exc).__name__}] {exc}"

    return {
        "mode": mode_val.value,
        "response": response,
        "call_count": tracker.call_count if tracker else 0,
        "recorded_calls": tracker.recorded_calls if tracker else [],
        "decisions": decisions_log,
        "final_coordinator_state": coordinator.state.value,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="JASPER Isolated Live-Model Test Harness")
    parser.add_argument(
        "--mode",
        choices=["read_only", "approval"],
        required=True,
        help="Mutually exclusive test configuration",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Prompt to send to /auto (defaults to appropriate prompt for the mode)",
    )
    parser.add_argument(
        "--decision",
        choices=["allow", "deny", "timeout"],
        default="allow",
        help="Simulated decision for approval-flow mode (default: allow)",
    )
    args = parser.parse_args()

    default_prompts = {
        "read_only": "Inspect system information and report OS and CPU.",
        "approval": "Call mock_safe_action with payload 'live_validation_test'.",
    }
    prompt = args.prompt or default_prompts[args.mode]

    print("=== Starting JASPER Isolated Live-Model Harness ===")
    print(f"Ollama Host: {OLLAMA_HOST}")
    print(f"Model: {JASPER_MODEL}")
    print(f"Mode: {args.mode}")
    print(f"Prompt: {prompt}")
    print(f"Decision: {args.decision}")

    result = asyncio.run(
        run_isolated_live_test(
            mode=args.mode,
            user_prompt=prompt,
            decision=args.decision,
        )
    )
    print("\n=== Live Test Result ===")
    print(f"Response: {result['response']}")
    print(f"Mock Tool Call Count: {result['call_count']}")
    print(f"Coordinator Final State: {result['final_coordinator_state']}")


if __name__ == "__main__":
    main()
