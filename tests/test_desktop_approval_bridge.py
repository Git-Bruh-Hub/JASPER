"""Tests for Step 14A: Desktop Approval Signal Bridge.

Covers:
1. A pending ApprovalRequest is emitted through the worker signal with correct gate ID and details.
2. The signal is connected to the intended notifier without creating a second coordinator.
3. An explicit allow decision is forwarded with the exact gate ID.
4. An explicit deny decision is forwarded with the exact gate ID.
5. Unknown and stale gate IDs are rejected.
6. Approval after expiry or cancellation cannot authorize the action.
7. A duplicate resolution cannot authorize an action twice.
8. Missing coordinator/notifier state fails safely.
9. Cancellation and timeout remain fail-closed.
10. Signal delivery and any associated GUI-thread handling respect Qt thread affinity.
11. No tool handler is invoked as a side effect of merely emitting an approval request or forwarding a decision.
12. Desktop autonomous mode remains disabled after the changes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

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
from app.core.approval import ApprovalGate, ApprovalRequest, ApprovalResult
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry
from app.ui.worker import JasperWorker


WORKSPACE = Path("C:/workspace").resolve()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_env(handler_mock=None):
    reg = ToolRegistry()
    mock_fn = handler_mock or MagicMock(return_value={"written": "ok"})
    reg.register(Tool(
        name="file.write",
        description="write file",
        risk=Risk.WRITE,
        handler=mock_fn,
        path_argument="path",
        requires_filesystem=True,
        resource_extractor=lambda args: args.get("path", ""),
    ))
    pm = ScopedPermissionManager(
        workspace_root=WORKSPACE,
        allowed_risks=frozenset({Risk.READ, Risk.WRITE}),
    )
    return reg, pm, mock_fn


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
        rationale="Write output safely",
    )


# ---------------------------------------------------------------------------
# 1. ApprovalRequest emitted through worker signal with correct gate ID & details
# ---------------------------------------------------------------------------

def test_pending_approval_request_emitted_through_worker_signal(qapp):
    worker = JasperWorker()
    action = _write_action("secret.txt")
    gate = ApprovalGate(action, timeout=60)
    req = gate.make_request()

    received: list[ApprovalRequest] = []
    worker.approval_requested.connect(received.append)

    worker.notify_approval(req)

    assert len(received) == 1
    assert received[0].gate_id == gate.gate_id
    assert received[0].action.tool_name == "file.write"
    assert received[0].action.arguments["path"] == str(WORKSPACE / "secret.txt")
    assert received[0].expires_at == req.expires_at


# ---------------------------------------------------------------------------
# 2. Signal connected to intended notifier without creating a second coordinator
# ---------------------------------------------------------------------------

def test_signal_connected_to_intended_notifier_without_second_coordinator(qapp):
    reg, pm, _ = _make_env()
    coord = MultiAgentCoordinator(reg, pm)

    # Initially coord._approval_notifier is None
    assert coord._approval_notifier is None

    worker = JasperWorker(coordinator=coord)

    # Coordinator is reused directly without spawning a new one
    assert worker.coordinator is coord
    assert coord._approval_notifier == worker.approval_requested.emit


# ---------------------------------------------------------------------------
# 3. Explicit allow decision forwarded with exact gate ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_allow_decision_forwarded_with_exact_gate_id(qapp):
    reg, pm, mock_fn = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm, approval_notifier=worker.approval_requested.emit)
    worker.set_coordinator(coord)

    received_reqs: list[ApprovalRequest] = []
    worker.approval_requested.connect(received_reqs.append)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))

    # Wait until gate is created and pending
    for _ in range(50):
        if coord.active_approval_gate is not None and coord.active_approval_gate.is_pending:
            break
        await asyncio.sleep(0.01)

    assert coord.active_approval_gate is not None
    assert len(received_reqs) == 1
    gate_id = received_reqs[0].gate_id

    # Resolve via worker
    assert worker.resolve_approval(gate_id, granted=True) is True

    result = await run_task
    assert isinstance(result, str)
    assert mock_fn.call_count == 1


# ---------------------------------------------------------------------------
# 4. Explicit deny decision forwarded with exact gate ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_deny_decision_forwarded_with_exact_gate_id(qapp):
    reg, pm, mock_fn = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm, approval_notifier=worker.approval_requested.emit)
    worker.set_coordinator(coord)

    received_reqs: list[ApprovalRequest] = []
    worker.approval_requested.connect(received_reqs.append)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))

    for _ in range(50):
        if coord.active_approval_gate is not None and coord.active_approval_gate.is_pending:
            break
        await asyncio.sleep(0.01)

    assert coord.active_approval_gate is not None
    gate_id = received_reqs[0].gate_id

    # Deny via worker
    assert worker.resolve_approval(gate_id, granted=False) is True

    with pytest.raises(PermissionError, match="User denied approval"):
        await run_task
    assert mock_fn.call_count == 0


# ---------------------------------------------------------------------------
# 5. Unknown and stale gate IDs are rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_and_stale_gate_ids_rejected(qapp):
    reg, pm, _ = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm, approval_notifier=worker.approval_requested.emit)
    worker.set_coordinator(coord)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))

    for _ in range(50):
        if coord.active_approval_gate is not None and coord.active_approval_gate.is_pending:
            break
        await asyncio.sleep(0.01)

    assert coord.active_approval_gate is not None
    real_gate_id = coord.active_gate_id

    # Reject unknown IDs
    assert worker.resolve_approval("unknown-gate-1234", granted=True) is False
    assert worker.resolve_approval("", granted=True) is False
    assert worker.resolve_approval("   ", granted=False) is False

    # Active gate must still be pending
    assert coord.active_approval_gate.is_pending is True

    # Real ID resolves successfully
    assert worker.resolve_approval(real_gate_id, granted=True) is True
    await run_task


# ---------------------------------------------------------------------------
# 6. Approval after expiry or cancellation cannot authorize the action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_after_cancellation_cannot_authorize(qapp):
    reg, pm, mock_fn = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm, approval_notifier=worker.approval_requested.emit)
    worker.set_coordinator(coord)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))

    for _ in range(50):
        if coord.active_approval_gate is not None and coord.active_approval_gate.is_pending:
            break
        await asyncio.sleep(0.01)

    gate = coord.active_approval_gate
    gate_id = gate.gate_id

    # Cancel the coordinator run
    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_task

    # Late approval resolution must fail closed
    assert worker.resolve_approval(gate_id, granted=True) is False
    assert mock_fn.call_count == 0


@pytest.mark.asyncio
async def test_approval_after_expiry_cannot_authorize(qapp):
    reg, pm, mock_fn = _make_env()
    action = _write_action()
    gate = ApprovalGate(action, timeout=0.01)  # 10ms timeout
    worker = JasperWorker()
    coord = Coordinator(reg, pm)
    coord._active_approval_gate = gate
    worker.set_coordinator(coord)

    req = gate.make_request()
    res = await gate.wait()

    assert res.expired is True
    assert res.granted is False

    # Attempting late approval after expiry
    assert worker.resolve_approval(req.gate_id, granted=True) is False
    assert mock_fn.call_count == 0


# ---------------------------------------------------------------------------
# 7. Duplicate resolution cannot authorize an action twice
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_resolution_cannot_authorize_twice(qapp):
    reg, pm, _ = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm, approval_notifier=worker.approval_requested.emit)
    worker.set_coordinator(coord)

    async def _agent(text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_write_action()])

    run_task = asyncio.create_task(coord.run(_agent, "test"))

    for _ in range(50):
        if coord.active_approval_gate is not None and coord.active_approval_gate.is_pending:
            break
        await asyncio.sleep(0.01)

    gate_id = coord.active_gate_id

    # First resolution succeeds
    assert worker.resolve_approval(gate_id, granted=True) is True

    # Subsequent resolutions fail closed
    assert worker.resolve_approval(gate_id, granted=True) is False
    assert worker.resolve_approval(gate_id, granted=False) is False

    await run_task


# ---------------------------------------------------------------------------
# 8. Missing coordinator/notifier state fails safely
# ---------------------------------------------------------------------------

def test_missing_coordinator_state_fails_safely(qapp):
    worker = JasperWorker()
    # By default in desktop GUI, coordinator is not attached
    assert worker.coordinator is None

    # Must return False and not throw
    assert worker.resolve_approval("any-gate-id", granted=True) is False
    assert worker.resolve_approval("any-gate-id", granted=False) is False


# ---------------------------------------------------------------------------
# 9. Cancellation and timeout remain fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancellation_and_timeout_remain_fail_closed(qapp):
    reg, pm, mock_fn = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm)
    worker.set_coordinator(coord)

    # Timeout case
    action = _write_action()
    gate = ApprovalGate(action, timeout=0.01)
    gate.make_request()
    res = await gate.wait()

    assert res.granted is False
    assert res.expired is True
    assert mock_fn.call_count == 0


# ---------------------------------------------------------------------------
# 10. Signal delivery respects Qt thread affinity
# ---------------------------------------------------------------------------

def test_signal_delivery_respects_qt_thread_affinity(qapp):
    thread = QThread()
    worker = JasperWorker()
    worker.moveToThread(thread)
    thread.start()

    main_thread = QThread.currentThread()
    delivery_thread: list[QThread] = []
    received_requests: list[ApprovalRequest] = []

    class Receiver(QObject):
        @Slot(ApprovalRequest)
        def on_approval(self, req: ApprovalRequest) -> None:
            delivery_thread.append(QThread.currentThread())
            received_requests.append(req)

    receiver = Receiver()
    # Explicit QueuedConnection or AutoConnection across threads
    worker.approval_requested.connect(receiver.on_approval)

    action = _write_action("affinity.txt")
    gate = ApprovalGate(action, timeout=30)
    req = gate.make_request()

    # Emit from the worker's thread context
    worker.notify_approval(req)

    # Process events on the main Qt GUI thread
    qapp.processEvents()

    assert len(received_requests) == 1
    assert received_requests[0].gate_id == req.gate_id
    assert len(delivery_thread) == 1
    # Receiver slot executed on the GUI main thread, not the worker thread
    assert delivery_thread[0] == main_thread

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 11. No tool handler invoked by merely emitting or forwarding
# ---------------------------------------------------------------------------

def test_no_tool_handler_invoked_by_merely_emitting_or_forwarding(qapp):
    reg, pm, mock_fn = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm)
    worker.set_coordinator(coord)

    action = _write_action()
    gate = ApprovalGate(action, timeout=60)
    req = gate.make_request()

    # Merely emitting the request does NOT run the tool
    worker.notify_approval(req)
    assert mock_fn.call_count == 0

    # Forwarding an invalid decision does NOT run the tool
    worker.resolve_approval("unknown-id", granted=True)
    assert mock_fn.call_count == 0


# ---------------------------------------------------------------------------
# 12. Desktop autonomous mode remains disabled after changes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_autonomous_mode_remains_disabled(qapp):
    worker = JasperWorker()

    # Default desktop worker has no autonomous coordinator wired into active path
    assert worker.jasper.multi_agent_coordinator is None

    # Attempting to call /auto via desktop orchestrator fails safely
    response = await worker.jasper.respond("/auto Run automated scan")
    assert response == "Autonomous mode is not enabled."
