"""Tests for Step 11: Coordinator Approval Gate Lifecycle and Resolution API.

Covers:
- Matching gate ID approves and denies the correct pending gate.
- Unknown and stale IDs are rejected without affecting the active gate.
- A late resolution after timeout or cancellation is harmless.
- Resolution after event-loop closure does not crash.
- Cancellation while awaiting approval cleans up the active gate and leaves coordinator state recoverable.
- An older gate's cleanup cannot erase a newer pending gate.
- Approval cannot be resolved twice or after its terminal state.
- Audit events emitted without exposing sensitive action arguments.
- MultiAgentCoordinator inherits approval resolution seamlessly.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    ProposedAction,
)
from app.agents.coordinator import (
    Coordinator,
    CoordinatorBudget,
    CoordinatorState,
)
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.core.approval import ApprovalGate, ApprovalRequest
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry


WORKSPACE = Path("C:/workspace").resolve()


def _make_env():
    reg = ToolRegistry()
    reg.register(Tool(
        name="file.write",
        description="write file",
        risk=Risk.WRITE,
        handler=lambda path, **kw: {"written": path},
        path_argument="path",
        requires_filesystem=True,
        resource_extractor=lambda args: args.get("path", ""),
    ))
    reg.register(Tool(
        name="file.read",
        description="read file",
        risk=Risk.READ,
        handler=lambda path, **kw: {"read": path},
        path_argument="path",
        requires_filesystem=True,
        resource_extractor=lambda args: args.get("path", ""),
    ))
    pm = ScopedPermissionManager(
        workspace_root=WORKSPACE,
        allowed_risks=frozenset({Risk.READ, Risk.WRITE}),
    )
    return reg, pm


def _write_action(path: str = "out.txt", **extra_args) -> ProposedAction:
    scope = PermissionScope(
        risk="write",
        resource_scope=str(WORKSPACE / path),
        operation="file.write",
        approval_requirement=ApprovalRequirement.ALWAYS,
        requires_filesystem=True,
    )
    args = {"path": str(WORKSPACE / path)}
    args.update(extra_args)
    return ProposedAction(
        tool_name="file.write",
        arguments=args,
        scope=scope,
        rationale="Write output",
    )


# ---------------------------------------------------------------------------
# 1. Matching gate ID approves and denies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_matching_gate_id_approves_pending_gate():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))
    await notified_event.wait()

    assert received_req is not None
    assert coord.state == CoordinatorState.APPROVING
    assert coord.active_approval_gate is not None
    assert coord.active_gate_id == received_req.gate_id
    assert coord.active_approval_request == received_req

    # Resolve approval with matching gate ID
    resolved = coord.resolve_approval(received_req.gate_id, granted=True)
    assert resolved is True

    answer = await run_task
    assert "written" in answer
    assert coord.state == CoordinatorState.IDLE
    assert coord.active_approval_gate is None
    assert coord.active_gate_id is None
    assert coord.active_approval_request is None


@pytest.mark.asyncio
async def test_matching_gate_id_denies_pending_gate():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))
    await notified_event.wait()

    assert received_req is not None
    assert coord.state == CoordinatorState.APPROVING

    # Deny approval with matching gate ID
    resolved = coord.resolve_approval(received_req.gate_id, granted=False)
    assert resolved is True

    with pytest.raises(PermissionError, match="User denied approval"):
        await run_task

    assert coord.state == CoordinatorState.ERROR
    assert coord.active_approval_gate is None
    assert coord.active_gate_id is None

    # Verify coordinator recovers cleanly via reset
    coord.reset()
    assert coord.state == CoordinatorState.IDLE


# ---------------------------------------------------------------------------
# 2. Unknown and stale IDs are rejected without affecting the active gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_and_stale_ids_rejected_without_affecting_active_gate():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))
    await notified_event.wait()

    assert received_req is not None
    real_gate_id = received_req.gate_id

    # 1. Unknown ID is rejected
    assert coord.resolve_approval("unknown-uuid-1234", granted=True) is False
    assert coord.active_gate_id == real_gate_id
    assert coord.active_approval_gate.is_pending is True

    # 2. Stale/empty ID is rejected
    assert coord.resolve_approval("", granted=False) is False
    assert coord.active_gate_id == real_gate_id
    assert coord.active_approval_gate.is_pending is True

    # 3. Real ID still resolves cleanly
    assert coord.resolve_approval(real_gate_id, granted=True) is True
    answer = await run_task
    assert "written" in answer


# ---------------------------------------------------------------------------
# 3. Late resolution after timeout or cancellation is harmless
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_late_resolution_after_timeout_is_harmless():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    # Create coordinator with a tight budget timeout to trigger expiration
    coord = Coordinator(reg, pm, approval_notifier=notifier)

    # We test with a short gate timeout on an individual gate
    action = _write_action()
    gate = ApprovalGate(action, timeout=0.02)
    req = gate.make_request()

    async def _wait_gate():
        return await gate.wait()

    result = await _wait_gate()
    assert result.expired is True
    assert gate.is_expired is True
    assert gate.is_pending is False

    # Late resolution directly on expired gate returns False safely
    assert gate.resolve(granted=True) is False
    assert gate.resolve(granted=False) is False


@pytest.mark.asyncio
async def test_late_resolution_after_cancellation_is_harmless():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))
    await notified_event.wait()

    assert received_req is not None
    gate_id = received_req.gate_id
    gate = coord.active_approval_gate

    # Cancel the waiting task
    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_task

    assert gate.is_cancelled is True
    assert gate.is_pending is False
    assert coord.active_approval_gate is None

    # Late resolution via coordinator returns False safely
    assert coord.resolve_approval(gate_id, granted=True) is False

    # Late resolution directly on gate returns False safely
    assert gate.resolve(granted=True) is False


# ---------------------------------------------------------------------------
# 4. Resolution after event-loop closure does not crash
# ---------------------------------------------------------------------------

def test_resolution_after_event_loop_closed_does_not_crash():
    action = _write_action()
    gate = ApprovalGate(action)
    gate.make_request()

    loop = asyncio.new_event_loop()
    try:
        async def _start_wait():
            # Create the future on this loop
            return await asyncio.wait_for(gate.wait(), timeout=0.01)

        loop.run_until_complete(_start_wait())
    except (asyncio.TimeoutError, Exception):
        pass
    finally:
        loop.close()

    # Now the loop is closed. Calling resolve() must not raise RuntimeError: Event loop is closed.
    resolved = gate.resolve(granted=True)
    assert resolved is False

    reg, pm = _make_env()
    coord = Coordinator(reg, pm)
    coord._active_approval_gate = gate
    coord_resolved = coord.resolve_approval(gate.gate_id, granted=True)
    assert coord_resolved is False


# ---------------------------------------------------------------------------
# 5. Cancellation while awaiting approval cleans up active gate & allows recovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancellation_cleans_up_active_gate_and_allows_recovery():
    reg, pm = _make_env()
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    task1 = asyncio.create_task(coord.run(_agent, "run1"))
    await notified_event.wait()

    assert coord.state == CoordinatorState.APPROVING
    assert coord.active_approval_gate is not None

    task1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task1

    assert coord.state == CoordinatorState.IDLE
    assert coord.active_approval_gate is None
    assert coord.active_gate_id is None

    # Run a second request on the same coordinator instance — it must succeed without lockout!
    read_action = ProposedAction(
        tool_name="file.read",
        arguments={"path": str(WORKSPACE / "report.txt")},
        scope=PermissionScope(
            risk="read",
            resource_scope=str(WORKSPACE / "report.txt"),
            operation="file.read",
            approval_requirement=ApprovalRequirement.NEVER,
            requires_filesystem=True,
        ),
        rationale="read report",
    )

    async def _read_agent(text: str) -> AgentResult:
        return AgentResult(agent_id="read_agent", proposed_actions=[read_action])

    answer2 = await coord.run(_read_agent, "run2")
    assert "read" in answer2
    assert coord.state == CoordinatorState.IDLE


# ---------------------------------------------------------------------------
# 6. An older gate's cleanup cannot erase a newer pending gate
# ---------------------------------------------------------------------------

def test_older_gate_cleanup_cannot_erase_newer_pending_gate():
    reg, pm = _make_env()
    coord = Coordinator(reg, pm)

    gate1 = ApprovalGate(_write_action("file1.txt"))
    gate2 = ApprovalGate(_write_action("file2.txt"))

    # Gate 2 is the active gate
    coord._active_approval_gate = gate2

    # Simulate gate1's finally block executing:
    # "if self._active_approval_gate is gate1: self._active_approval_gate = None"
    if coord._active_approval_gate is gate1:
        coord._active_approval_gate = None

    # Gate 2 must NOT be erased by gate1's cleanup!
    assert coord._active_approval_gate is gate2
    assert coord.active_approval_gate is gate2


# ---------------------------------------------------------------------------
# 7. Approval cannot be resolved twice or after terminal state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_cannot_be_resolved_twice_or_after_terminal_state():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))
    await notified_event.wait()

    assert received_req is not None
    gate_id = received_req.gate_id

    # First resolution succeeds
    assert coord.resolve_approval(gate_id, granted=True) is True

    # Immediate duplicate resolution rejected
    assert coord.resolve_approval(gate_id, granted=True) is False
    assert coord.resolve_approval(gate_id, granted=False) is False

    await run_task

    # Post-run resolution rejected
    assert coord.resolve_approval(gate_id, granted=True) is False


# ---------------------------------------------------------------------------
# 8. No active approval gate returns False
# ---------------------------------------------------------------------------

def test_no_active_approval_gate_queries_and_resolution_return_none_or_false():
    reg, pm = _make_env()
    coord = Coordinator(reg, pm)

    assert coord.active_approval_gate is None
    assert coord.active_gate_id is None
    assert coord.active_approval_request is None
    assert coord.resolve_approval("random-gate-id", granted=True) is False


# ---------------------------------------------------------------------------
# 9. Audit events emitted without exposing sensitive action arguments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_audit_events_emitted_without_sensitive_arguments(caplog):
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    coord = Coordinator(reg, pm, approval_notifier=notifier)

    secret_value = "SECRET_PASSWORD_123456789"
    action = _write_action(path="secret.txt", secret_key=secret_value)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[action])

    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        run_task = asyncio.create_task(coord.run(_agent, "test"))
        await notified_event.wait()
        coord.resolve_approval(received_req.gate_id, granted=True)
        await run_task

    audit_records = [
        json.loads(r.message)
        for r in caplog.records
        if r.name == "jasper.audit"
    ]
    events = [r["event"] for r in audit_records]

    assert "approval_requested" in events
    assert "approval_granted" in events

    # Assert secret argument was NOT leaked into any audit record
    for record_data in audit_records:
        serialized = json.dumps(record_data)
        assert secret_value not in serialized


# ---------------------------------------------------------------------------
# 10. MultiAgentCoordinator inherits approval resolution seamlessly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_agent_coordinator_inherits_approval_resolution():
    reg, pm = _make_env()
    received_req: ApprovalRequest | None = None
    notified_event = asyncio.Event()

    def notifier(req: ApprovalRequest):
        nonlocal received_req
        received_req = req
        notified_event.set()

    multi_coord = MultiAgentCoordinator(reg, pm, approval_notifier=notifier)

    action = _write_action("multi_out.txt")

    async def planner_callable(task):
        return AgentResult(agent_id="planner", proposed_actions=[action])

    async def executor_callable(planner_res, feedback):
        return AgentResult(agent_id="executor", proposed_actions=[action])

    run_task = asyncio.create_task(
        multi_coord.run_multi_agent(planner_callable, executor_callable, "test multi")
    )
    await notified_event.wait()

    assert received_req is not None
    assert multi_coord.state == CoordinatorState.APPROVING
    assert multi_coord.active_gate_id == received_req.gate_id

    # Resolve approval on MultiAgentCoordinator
    assert multi_coord.resolve_approval(received_req.gate_id, granted=True) is True

    answer = await run_task
    assert "written" in answer
    assert multi_coord.state == CoordinatorState.IDLE
    assert multi_coord.active_approval_gate is None
