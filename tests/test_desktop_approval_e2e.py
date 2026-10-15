"""Tests for Step 15: Controlled End-to-End Desktop Approval Verification.

Exercises the complete lifecycle:
Request -> coordinator proposal -> approval request -> GUI-thread dialog ->
explicit decision -> coordinator authorization -> controlled execution or rejection ->
response and audit.

Covers all 15 required scenarios:
1. Controlled desktop request reaches coordinator path in test harness.
2. Planner proposes registered, valid action.
3. Request requiring approval emits correct ApprovalRequest.
4. GUI handler receives request on correct thread.
5. Allow resolves exact gate and invokes fake tool exactly once.
6. Deny does not invoke fake tool.
7. Closing dialog or pressing Esc denies request.
8. Expiry prevents execution and rejects late approval.
9. Cancellation while approval is pending prevents execution.
10. Stale or duplicate gate ID cannot authorize another request.
11. Coordinator failure and recovery do not reuse stale approval state.
12. Window shutdown with pending request fails closed.
13. Standard chat continues to use existing path (does not enter autonomous coordinator).
14. Desktop autonomous mode remains disabled in normal configuration.
15. No unauthorized or denied action reaches tool handler.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    PlannerResult,
    PlannerTask,
    ProposedAction,
)
from app.agents.coordinator import CoordinatorBudget, CoordinatorState
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.core.approval import ApprovalGate, ApprovalRequest
from app.core.permissions import PermissionManager
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry
from app.ui.approval_dialog import ApprovalDialog
from app.ui.main_window import MainWindow
from app.ui.worker import JasperWorker


WORKSPACE = Path("C:/workspace").resolve()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _build_test_harness(tool_mock=None):
    """Build controlled registry, permission manager, coordinator, and fake agents."""
    reg = ToolRegistry()
    mock_tool = tool_mock or MagicMock(return_value={"status": "ok", "bytes_written": 42})
    reg.register(Tool(
        name="test_write_tool",
        description="Write controlled test output",
        risk=Risk.WRITE,
        handler=mock_tool,
        path_argument="target_path",
        requires_filesystem=True,
        resource_extractor=lambda args: args.get("target_path", ""),
    ))
    read_mock = MagicMock(return_value={"content": "hello world"})
    reg.register(Tool(
        name="test_read_tool",
        description="Read controlled test output",
        risk=Risk.READ,
        handler=read_mock,
        path_argument="target_path",
        requires_filesystem=True,
        resource_extractor=lambda args: args.get("target_path", ""),
    ))

    pm = ScopedPermissionManager(
        workspace_root=WORKSPACE,
        allowed_risks=frozenset({Risk.READ, Risk.WRITE}),
    )
    coord = MultiAgentCoordinator(
        registry=reg,
        permissions=pm,
        budget=CoordinatorBudget(timeout_seconds=30.0),
    )

    action = ProposedAction(
        tool_name="test_write_tool",
        arguments={"target_path": str(WORKSPACE / "test.txt")},
        scope=PermissionScope(
            risk="write",
            resource_scope=str(WORKSPACE / "test.txt"),
            operation="test_write_tool",
            approval_requirement=ApprovalRequirement.ALWAYS,
            requires_filesystem=True,
        ),
        rationale="Write test output safely",
    )

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Proposed controlled test tool action"],
            proposed_actions=[action],
        )

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Executing approved test tool action"],
            proposed_actions=[action],
        )

    return reg, pm, coord, mock_tool, read_mock, fake_planner, fake_executor


# ---------------------------------------------------------------------------
# 1. Controlled request reaches coordinator path in test harness
# 2. Planner proposes registered, valid action
# 3. Request requiring approval emits correct ApprovalRequest
# 4. GUI handler receives request on correct thread
# 5. Allow resolves exact gate and invokes fake tool exactly once
# ---------------------------------------------------------------------------

def test_e2e_allow_flow_invokes_fake_tool_once(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    # Trigger autonomous request
    responses: list[tuple[str, str]] = []
    worker.response_ready.connect(lambda k, c: responses.append((k, c)))

    # Start request via window
    window.input.setText("/auto Perform controlled file write")
    window._send_text()

    # Process events until approval dialog opens on GUI thread
    dialog_opened = False
    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            dialog_opened = True
            break
        QThread.msleep(20)

    assert dialog_opened is True
    dialog = window._active_approval_dialog
    assert dialog.gate_id == coord.active_gate_id
    assert "test_write_tool" in dialog.action_label.text()
    assert dialog.thread() == qapp.thread()  # GUI thread affinity

    # Click Allow
    dialog.allow_btn.click()

    # Wait for completion
    finished = False
    for _ in range(100):
        qapp.processEvents()
        if len(responses) > 0:
            finished = True
            break
        QThread.msleep(20)

    assert finished is True
    assert mock_tool.call_count == 1
    assert window._active_approval_dialog is None

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 6. Deny does not invoke fake tool
# ---------------------------------------------------------------------------

def test_e2e_deny_flow_does_not_invoke_tool(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    responses: list[tuple[str, str]] = []
    errors: list[str] = []
    worker.response_ready.connect(lambda k, c: responses.append((k, c)))
    worker.error.connect(errors.append)

    window.input.setText("/auto Run denied task")
    window._send_text()

    # Wait until dialog is active
    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    assert window._active_approval_dialog is not None

    # Click Deny
    window._active_approval_dialog.deny_btn.click()

    # Wait for finish
    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    # Tool was never called
    assert mock_tool.call_count == 0
    assert window._active_approval_dialog is None

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 7. Closing dialog or pressing Esc denies request
# ---------------------------------------------------------------------------

def test_e2e_esc_or_closing_dialog_denies_request(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    window.input.setText("/auto Run esc test")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    assert window._active_approval_dialog is not None

    # User presses Esc (triggers reject())
    window._active_approval_dialog.reject()

    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    assert mock_tool.call_count == 0
    assert window._active_approval_dialog is None

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 8. Expiry prevents execution and rejects late approval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_expiry_prevents_execution_and_rejects_late_approval(qapp):
    reg, pm, _, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    # Use 20ms timeout on coordinator approval gate
    coord = MultiAgentCoordinator(
        registry=reg,
        permissions=pm,
        budget=CoordinatorBudget(timeout_seconds=0.05),
    )

    worker = JasperWorker()
    worker.set_coordinator(coord)
    worker.jasper.registry = reg
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    received_reqs: list[ApprovalRequest] = []
    worker.approval_requested.connect(received_reqs.append)

    # Run request directly in asyncio
    task = asyncio.create_task(
        worker.jasper.respond("/auto test with quick expiry")
    )

    # Wait for approval request to be emitted
    for _ in range(50):
        if len(received_reqs) > 0:
            break
        await asyncio.sleep(0.01)

    assert len(received_reqs) == 1
    gate_id = received_reqs[0].gate_id

    # Allow the gate to expire
    await asyncio.sleep(0.1)

    # Late approval attempt fails closed
    resolved = worker.resolve_approval(gate_id, granted=True)
    assert resolved is False

    try:
        await task
    except Exception:
        pass

    assert mock_tool.call_count == 0


# ---------------------------------------------------------------------------
# 9. Cancellation while approval is pending prevents execution
# ---------------------------------------------------------------------------

def test_e2e_cancellation_while_pending_prevents_execution(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    window.input.setText("/auto Run cancelled test")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    assert window._active_approval_dialog is not None
    dialog = window._active_approval_dialog

    # User clicks Stop button in GUI
    window._on_send_clicked()

    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    assert mock_tool.call_count == 0
    assert window._active_approval_dialog is None
    assert dialog.is_resolved is True

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 10. Stale or duplicate gate ID cannot authorize another request
# ---------------------------------------------------------------------------

def test_e2e_stale_or_duplicate_gate_id_rejected(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    window.input.setText("/auto Stale ID test")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    real_gate_id = window._active_gate_id

    # Attempt resolution with mismatched/stale gate ID
    assert worker.resolve_approval("stale-uuid-1234", granted=True) is False
    assert mock_tool.call_count == 0

    # Dialog must still be active for the real gate
    assert window._active_approval_dialog is not None

    # Real resolution works
    window._active_approval_dialog.allow_btn.click()

    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    assert mock_tool.call_count == 1

    # Duplicate resolution attempt is rejected
    assert worker.resolve_approval(real_gate_id, granted=True) is False
    assert mock_tool.call_count == 1

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 11. Coordinator failure and recovery do not reuse stale approval state
# ---------------------------------------------------------------------------

def test_e2e_coordinator_failure_and_recovery_resets_approval_state(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    # First run: Deny
    window.input.setText("/auto First run to fail")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    old_gate_id = window._active_gate_id
    window._active_approval_dialog.deny_btn.click()

    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    assert mock_tool.call_count == 0
    # Old gate ID cannot be reused after recovery
    assert worker.resolve_approval(old_gate_id, granted=True) is False

    # Second run: Allow succeeds cleanly with new gate ID
    window.input.setText("/auto Second run to succeed")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    new_gate_id = window._active_gate_id
    assert new_gate_id != old_gate_id

    window._active_approval_dialog.allow_btn.click()

    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    assert mock_tool.call_count == 1

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 12. Window shutdown with pending request fails closed
# ---------------------------------------------------------------------------

def test_e2e_window_shutdown_with_pending_request_fails_closed(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)
    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    window.input.setText("/auto Request before close")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if window._active_approval_dialog is not None:
            break
        QThread.msleep(20)

    assert window._active_approval_dialog is not None

    # Close window while approval is pending
    event = QCloseEvent()
    window.closeEvent(event)

    for _ in range(50):
        qapp.processEvents()
        QThread.msleep(20)

    assert mock_tool.call_count == 0
    assert window._active_approval_dialog is None

    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 13. Standard chat continues to use existing path (no coordinator)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_standard_chat_bypasses_autonomous_coordinator(qapp):
    reg, pm, coord, mock_tool, read_mock, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.set_coordinator(coord)
    worker.jasper.registry = reg

    # Mock CognitiveEngine run so it doesn't call live models
    worker.jasper.engine.run = AsyncMock(return_value="Four")

    # Send regular query
    answer = await worker.jasper.respond("What is 2+2?")

    assert answer == "Four"
    # Coordinator was not entered
    assert coord.state == CoordinatorState.IDLE
    assert coord.active_approval_gate is None
    assert mock_tool.call_count == 0


# ---------------------------------------------------------------------------
# 14. Desktop autonomous mode remains disabled in normal configuration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_desktop_autonomous_mode_disabled_by_default(qapp):
    # Normal worker without set_coordinator
    worker = JasperWorker()

    assert worker.coordinator is None
    assert worker.jasper.multi_agent_coordinator is None

    # Normal user sending /auto receives disabled message
    response = await worker.jasper.respond("/auto Run automated workflow")
    assert response == "Autonomous mode is not enabled."


# ---------------------------------------------------------------------------
# 15. No unauthorized or denied action reaches tool handler
# ---------------------------------------------------------------------------

def test_e2e_unauthorized_actions_never_reach_tool_handler(qapp):
    reg, pm, coord, mock_tool, _, fake_planner, fake_executor = _build_test_harness()

    worker = JasperWorker()
    worker.jasper.registry = reg
    worker.set_coordinator(coord)

    # Unknown tool requested
    unknown_action = ProposedAction(
        tool_name="nonexistent_tool",
        arguments={},
        scope=PermissionScope(
            risk="write",
            resource_scope="*",
            operation="nonexistent_tool",
            approval_requirement=ApprovalRequirement.ALWAYS,
        ),
        rationale="Unknown tool test",
    )

    async def bad_planner(task, cancel_callback=None):
        return AgentResult(agent_id="planner", proposed_actions=[unknown_action])

    worker.jasper.planner_callable = bad_planner
    worker.jasper.executor_callable = fake_executor

    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)

    window.input.setText("/auto Bad tool test")
    window._send_text()

    for _ in range(100):
        qapp.processEvents()
        if not window.busy:
            break
        QThread.msleep(20)

    # No approval dialog shown, no tool executed
    assert window._active_approval_dialog is None
    assert mock_tool.call_count == 0

    thread.quit()
    thread.wait(2000)
