"""tests/test_live_harness_contracts.py — Deterministic Unit Tests for Step 18A Live Harness.

Tests the safety boundaries, registry isolation, containment, and fail-closed
invariants of the isolated live harness without invoking live model inference or
accessing external networks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.adapters import _parse_llm_actions
from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    PlannerResult,
    PlannerTask,
    ProposedAction,
)
from app.agents.coordinator import CoordinatorState
from app.core.approval import ApprovalRequest
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry
from app.ui.worker import JasperWorker
from tests.support.live_harness import (
    HarnessMode,
    MockActionTracker,
    build_isolated_coordinator,
    build_isolated_orchestrator,
    build_isolated_registry,
    build_isolated_worker,
)


WORKSPACE = Path("C:/workspace").resolve()


# ---------------------------------------------------------------------------
# 1. Read-only registry allowlisting
# ---------------------------------------------------------------------------

def test_read_only_registry_allowlisting():
    registry, tracker = build_isolated_registry(HarnessMode.READ_ONLY)

    assert tracker is None
    tools = registry.list()
    assert len(tools) == 1
    assert tools[0].name == "get_system_info"
    assert tools[0].risk == Risk.READ

    # Attempting to retrieve an unregistered tool fails closed
    with pytest.raises(KeyError):
        registry.get("mock_safe_action")

    with pytest.raises(KeyError):
        registry.get("file.write")

    with pytest.raises(KeyError):
        registry.get("terminal.run")

    # Permissions enforcement in read-only mode allows READ, denies WRITE
    pm = ScopedPermissionManager(workspace_root=WORKSPACE, allowed_risks=frozenset({Risk.READ}))
    pm.check_tool(tools[0])  # Should pass

    write_tool = Tool(name="fake_write", description="", risk=Risk.WRITE, handler=lambda: None)
    with pytest.raises(PermissionError):
        pm.check_tool(write_tool)


# ---------------------------------------------------------------------------
# 2. Approval mock registry containment
# ---------------------------------------------------------------------------

def test_approval_mock_registry_containment():
    registry, tracker = build_isolated_registry(HarnessMode.APPROVAL)

    assert tracker is not None
    assert tracker.call_count == 0
    assert len(tracker.recorded_calls) == 0

    tools = registry.list()
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "mock_safe_action"
    assert tool.risk == Risk.WRITE

    # Tool invocation operates purely in memory with zero external side effects
    result = tool.handler(payload="test_payload", param_int=123)
    assert result["status"] == "success"
    assert result["call_count"] == 1
    assert tracker.call_count == 1
    assert len(tracker.recorded_calls) == 1
    assert tracker.recorded_calls[0] == {"payload": "test_payload", "param_int": 123}

    # Reset cleans in-memory state
    tracker.reset()
    assert tracker.call_count == 0
    assert len(tracker.recorded_calls) == 0


# ---------------------------------------------------------------------------
# 3. Safe handling of unexpected planner tool names
# ---------------------------------------------------------------------------

def test_unexpected_planner_tool_names_safely_ignored():
    read_registry, _ = build_isolated_registry(HarnessMode.READ_ONLY)

    raw_llm_tool_calls = [
        {"function": {"name": "get_system_info", "arguments": "{}"}},
        {"function": {"name": "malicious_tool", "arguments": '{"cmd": "rm -rf"}'}},
        {"function": {"name": "file.write", "arguments": '{"path": "foo.txt"}'}},
        {"function": {"name": "mock_safe_action", "arguments": "{}"}},
    ]

    # In read-only mode, only get_system_info is recognized; others are dropped
    actions = _parse_llm_actions(raw_llm_tool_calls, read_registry)
    assert len(actions) == 1
    assert actions[0].tool_name == "get_system_info"
    assert actions[0].scope.risk == "read"

    approval_registry, _ = build_isolated_registry(HarnessMode.APPROVAL)

    # In approval mode, get_system_info and unknown tools are dropped; only mock_safe_action is recognized
    approval_actions = _parse_llm_actions(raw_llm_tool_calls, approval_registry)
    assert len(approval_actions) == 1
    assert approval_actions[0].tool_name == "mock_safe_action"
    assert approval_actions[0].scope.risk == "write"


# ---------------------------------------------------------------------------
# 4. Default desktop fail-closed behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_desktop_fail_closed_behavior():
    worker = JasperWorker()

    # In normal desktop startup, coordinator is None and autonomy is disabled
    assert worker.coordinator is None
    assert worker.jasper.multi_agent_coordinator is None

    # Resolving approval fails closed without a coordinator
    resolved = worker.resolve_approval("any-gate-id", granted=True)
    assert resolved is False

    # Autonomous /auto requests fail safely without executing anything
    response = await worker.jasper.respond("/auto Run high-risk operation")
    assert response == "Autonomous mode is not enabled."


# ---------------------------------------------------------------------------
# 5. Coordinator authorization and approval with mock action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_coordinator_approval_granted_executes_mock():
    registry, tracker = build_isolated_registry(HarnessMode.APPROVAL)
    assert tracker is not None

    coordinator = None

    def auto_allow_notifier(request: ApprovalRequest) -> None:
        assert coordinator is not None
        loop = asyncio.get_running_loop()
        loop.call_soon(coordinator.resolve_approval, request.gate_id, True)

    coordinator = build_isolated_coordinator(
        registry=registry,
        mode=HarnessMode.APPROVAL,
        approval_notifier=auto_allow_notifier,
        workspace_root=WORKSPACE,
    )

    action = ProposedAction(
        tool_name="mock_safe_action",
        arguments={"payload": "approved_data"},
        scope=PermissionScope(
            risk="write",
            resource_scope="global",
            operation="mock_safe_action",
            approval_requirement=ApprovalRequirement.ALWAYS,
        ),
        rationale="Simulated test plan",
    )

    async def mock_planner(task: PlannerTask) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Plan created."],
            proposed_actions=[action],
        )

    async def mock_executor(plan: PlannerResult, feedback: Any) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Executing approved action."],
            proposed_actions=[action],
        )

    answer = await coordinator.run_multi_agent(
        planner_callable=mock_planner,
        executor_callable=mock_executor,
        user_text="Perform harmless mock action",
    )

    assert tracker.call_count == 1
    assert tracker.recorded_calls[0] == {"payload": "approved_data"}
    assert coordinator.state == CoordinatorState.IDLE


@pytest.mark.asyncio
async def test_coordinator_approval_denied_fails_closed():
    registry, tracker = build_isolated_registry(HarnessMode.APPROVAL)
    assert tracker is not None

    coordinator = None

    def auto_deny_notifier(request: ApprovalRequest) -> None:
        assert coordinator is not None
        loop = asyncio.get_running_loop()
        loop.call_soon(coordinator.resolve_approval, request.gate_id, False)

    coordinator = build_isolated_coordinator(
        registry=registry,
        mode=HarnessMode.APPROVAL,
        approval_notifier=auto_deny_notifier,
        workspace_root=WORKSPACE,
    )

    action = ProposedAction(
        tool_name="mock_safe_action",
        arguments={"payload": "denied_data"},
        scope=PermissionScope(
            risk="write",
            resource_scope="global",
            operation="mock_safe_action",
            approval_requirement=ApprovalRequirement.ALWAYS,
        ),
        rationale="Simulated test plan",
    )

    async def mock_planner(task: PlannerTask) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Plan created."],
            proposed_actions=[action],
        )

    async def mock_executor(plan: PlannerResult, feedback: Any) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Executing action."],
            proposed_actions=[action],
        )

    with pytest.raises(PermissionError) as exc_info:
        await coordinator.run_multi_agent(
            planner_callable=mock_planner,
            executor_callable=mock_executor,
            user_text="Perform harmless mock action",
        )

    assert "User denied approval" in str(exc_info.value)
    # Denied action MUST NOT execute handler
    assert tracker.call_count == 0
    assert len(tracker.recorded_calls) == 0
    assert coordinator.state == CoordinatorState.ERROR
    coordinator.reset()
    assert coordinator.state == CoordinatorState.IDLE


# ---------------------------------------------------------------------------
# 6. Isolated orchestrator routing with simulated callables
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_isolated_orchestrator_routing():
    registry, _ = build_isolated_registry(HarnessMode.READ_ONLY)
    coordinator = build_isolated_coordinator(registry=registry, mode=HarnessMode.READ_ONLY)
    orchestrator = build_isolated_orchestrator(registry=registry, coordinator=coordinator)

    action = ProposedAction(
        tool_name="get_system_info",
        arguments={},
        scope=PermissionScope(
            risk="read",
            resource_scope="global",
            operation="get_system_info",
            approval_requirement=ApprovalRequirement.NEVER,
        ),
        rationale="Read system info",
    )

    async def mock_planner(task: PlannerTask) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Read system info."],
            proposed_actions=[action],
        )

    async def mock_executor(plan: PlannerResult, feedback: Any) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Executed get_system_info."],
            proposed_actions=[action],
        )

    orchestrator.planner_callable = mock_planner
    orchestrator.executor_callable = mock_executor

    response = await orchestrator.respond("/auto Inspect system")
    assert isinstance(response, str)
    assert len(response) > 0


# ---------------------------------------------------------------------------
# 7. app/desktop.py remains strictly untouched and fail-closed
# ---------------------------------------------------------------------------

def test_app_desktop_remains_untouched():
    desktop_path = Path("app/desktop.py")
    assert desktop_path.exists()
    content = desktop_path.read_text(encoding="utf-8")
    assert "MultiAgentCoordinator" not in content
    assert "JasperWorker()" in content or "JasperWorker(coordinator=" not in content
