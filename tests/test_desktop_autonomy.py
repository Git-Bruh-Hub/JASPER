"""Tests for Desktop Autonomy Wiring and Execution (Phase 1).

Validates:
1. build_desktop_autonomy correctly configures and attaches MultiAgentCoordinator.
2. write_text_file tool enforcement (extension allowlisting, size limits, parent creation).
3. End-to-end /auto approval lifecycle:
   - Approval granted -> executes write_text_file within workspace.
   - Approval denied -> blocks write_text_file and fails closed.
4. Out-of-bounds containment: ScopedPermissionManager denies operations outside workspace.
5. Standard chat regression: standard chat bypasses coordinator and remains intact.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    PlannerResult,
    PlannerTask,
    ProposedAction,
)
from app.agents.desktop_wiring import (
    build_desktop_autonomy,
    get_default_desktop_workspace,
    register_desktop_tools,
)
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.core.approval import ApprovalRequest
from app.core.orchestrator import CognitiveMode
from app.tools.filesystem import TEXT_EXTENSIONS, write_text_file
from app.tools.registry import Risk, ToolRegistry
from app.ui.worker import JasperWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# 1. Unit Tests for write_text_file
# ---------------------------------------------------------------------------

def test_write_text_file_creates_file_and_parents(tmp_path: Path):
    target = tmp_path / "sub" / "nested" / "test.txt"
    result = write_text_file(str(target), "hello jasper autonomy")
    assert result["status"] == "written"
    assert result["bytes_written"] == len("hello jasper autonomy".encode("utf-8"))
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello jasper autonomy"


def test_write_text_file_rejects_disallowed_extension(tmp_path: Path):
    target = tmp_path / "malicious.exe"
    with pytest.raises(ValueError, match="not allowlisted"):
        write_text_file(str(target), "binary data")


def test_write_text_file_rejects_oversized_content(tmp_path: Path):
    target = tmp_path / "big.txt"
    huge_content = "a" * (512_000 + 1)
    with pytest.raises(ValueError, match="exceeds 512000 byte safety limit"):
        write_text_file(str(target), huge_content)


# ---------------------------------------------------------------------------
# 2. Desktop Autonomy Factory & Wiring
# ---------------------------------------------------------------------------

def test_register_desktop_tools_is_idempotent():
    reg = ToolRegistry()
    register_desktop_tools(reg)
    tools = {t.name for t in reg.list()}
    assert "write_text_file" in tools
    assert "browser_summarize" in tools
    count = len(reg.list())
    register_desktop_tools(reg)
    assert len(reg.list()) == count


def test_build_desktop_autonomy_attaches_coordinator(tmp_path: Path):
    worker = JasperWorker()
    assert worker.coordinator is None
    assert worker.jasper.multi_agent_coordinator is None

    coord = build_desktop_autonomy(worker, workspace_root=tmp_path)
    assert isinstance(coord, MultiAgentCoordinator)
    assert worker.coordinator is coord
    assert worker.jasper.multi_agent_coordinator is coord
    assert coord._workspace == tmp_path.resolve()
    assert "write_text_file" in {t.name for t in worker.jasper.registry.list()}


# ---------------------------------------------------------------------------
# 3. Controlled End-to-End Autonomous Approval (Allow Flow)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_autonomy_e2e_approval_allow_writes_file(tmp_path: Path, qapp):
    worker = JasperWorker()
    coord = build_desktop_autonomy(worker, workspace_root=tmp_path)

    target_file = tmp_path / "script.py"
    target_content = "print('Hello from Desktop Autonomy!')"

    action = ProposedAction(
        tool_name="write_text_file",
        arguments={"path": str(target_file), "content": target_content},
        scope=PermissionScope(
            risk="write",
            resource_scope=str(target_file),
            operation="write_text_file",
            approval_requirement=ApprovalRequirement.ALWAYS,
            requires_filesystem=True,
        ),
        rationale="Write python test script",
    )

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Plan file creation"],
            proposed_actions=[action],
        )

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Execute file creation"],
            proposed_actions=[action],
        )

    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    captured_requests: list[ApprovalRequest] = []

    def on_approval_request(req: ApprovalRequest):
        captured_requests.append(req)
        # Schedule resolution once gate enters wait() on event loop
        asyncio.get_running_loop().call_soon(
            lambda: worker.resolve_approval(req.gate_id, granted=True)
        )

    worker.approval_requested.connect(on_approval_request)

    response = await worker.jasper.respond("/auto Create hello world script")

    assert len(captured_requests) == 1
    assert captured_requests[0].action.tool_name == "write_text_file"
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == target_content


# ---------------------------------------------------------------------------
# 4. Controlled End-to-End Autonomous Approval (Deny Flow)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_autonomy_e2e_approval_deny_blocks_write(tmp_path: Path, qapp):
    worker = JasperWorker()
    coord = build_desktop_autonomy(worker, workspace_root=tmp_path)

    target_file = tmp_path / "should_not_exist.py"

    action = ProposedAction(
        tool_name="write_text_file",
        arguments={"path": str(target_file), "content": "content"},
        scope=PermissionScope(
            risk="write",
            resource_scope=str(target_file),
            operation="write_text_file",
            approval_requirement=ApprovalRequirement.ALWAYS,
            requires_filesystem=True,
        ),
        rationale="Write file that user denies",
    )

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Plan file creation"],
            proposed_actions=[action],
        )

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Execute file creation"],
            proposed_actions=[action],
        )

    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    captured_requests: list[ApprovalRequest] = []

    def on_approval_request(req: ApprovalRequest):
        captured_requests.append(req)
        # Schedule denial once gate enters wait() on event loop
        asyncio.get_running_loop().call_soon(
            lambda: worker.resolve_approval(req.gate_id, granted=False)
        )

    worker.approval_requested.connect(on_approval_request)

    with pytest.raises(PermissionError, match="User denied approval"):
        await worker.jasper.respond("/auto Create file to deny")

    assert len(captured_requests) == 1
    assert not target_file.exists()


# ---------------------------------------------------------------------------
# 5. Out-of-Bounds Filesystem Containment Guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_autonomy_blocks_out_of_bounds_write(tmp_path: Path, qapp):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"

    worker = JasperWorker()
    coord = build_desktop_autonomy(worker, workspace_root=workspace)

    action = ProposedAction(
        tool_name="write_text_file",
        arguments={"path": str(outside), "content": "escape"},
        scope=PermissionScope(
            risk="write",
            resource_scope=str(outside),
            operation="write_text_file",
            approval_requirement=ApprovalRequirement.ALWAYS,
            requires_filesystem=True,
        ),
        rationale="Attempt path traversal out of workspace",
    )

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="planner",
            observations=["Escape workspace"],
            proposed_actions=[action],
        )

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return AgentResult(
            agent_id="executor",
            observations=["Escape workspace"],
            proposed_actions=[action],
        )

    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    with pytest.raises(PermissionError, match="outside the allowed workspace"):
        await worker.jasper.respond("/auto Write outside")

    assert not outside.exists()


# ---------------------------------------------------------------------------
# 6. Browser Tools Integration & Autonomy
# ---------------------------------------------------------------------------

def test_register_desktop_tools_registers_browser_suite():
    reg = ToolRegistry()
    register_desktop_tools(reg)
    tool_names = {t.name for t in reg.list()}

    assert "browser_navigate" in tool_names
    assert "browser_get_dom" in tool_names
    assert "browser_read_text" in tool_names
    assert "browser_click" in tool_names
    assert "browser_type" in tool_names
    assert "browser_close" in tool_names

    # Check risk mappings
    assert reg.get("browser_navigate").risk == Risk.READ
    assert reg.get("browser_get_dom").risk == Risk.READ
    assert reg.get("browser_read_text").risk == Risk.READ
    assert reg.get("browser_click").risk == Risk.WRITE
    assert reg.get("browser_type").risk == Risk.WRITE
    assert reg.get("browser_close").risk == Risk.READ


@pytest.mark.asyncio
async def test_desktop_autonomy_browser_navigate_auto_executes(tmp_path: Path, qapp):
    worker = JasperWorker()
    coord = build_desktop_autonomy(worker, workspace_root=tmp_path)

    test_url = "data:text/html,<html><head><title>Autonomy Web Test</title></head><body><button id='b1'>Start</button></body></html>"

    action = ProposedAction(
        tool_name="browser_navigate",
        arguments={"url": test_url},
        scope=PermissionScope(
            risk="read",
            resource_scope=test_url,
            operation="browser_navigate",
            approval_requirement=ApprovalRequirement.NEVER,
            requires_filesystem=False,
        ),
        rationale="Inspect test page",
    )

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        return AgentResult(agent_id="planner", observations=["Navigate web"], proposed_actions=[action])

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return AgentResult(agent_id="executor", observations=["Execute web navigation"], proposed_actions=[action])

    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    captured_approvals = []
    worker.approval_requested.connect(lambda req: captured_approvals.append(req))

    response = await worker.jasper.respond("/auto browse test page")

    # READ operations do not trigger approval dialogs
    assert len(captured_approvals) == 0
    assert "Autonomy Web Test" in response
    assert "Navigated to" in response


@pytest.mark.asyncio
async def test_desktop_autonomy_browser_click_requires_approval(tmp_path: Path, qapp):
    worker = JasperWorker()
    coord = build_desktop_autonomy(worker, workspace_root=tmp_path)

    action = ProposedAction(
        tool_name="browser_click",
        arguments={"index": 1},
        scope=PermissionScope(
            risk="write",
            resource_scope="browser://click/[1]",
            operation="browser_click",
            approval_requirement=ApprovalRequirement.ALWAYS,
            requires_filesystem=False,
        ),
        rationale="Click submit button",
    )

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        return AgentResult(agent_id="planner", observations=["Plan click"], proposed_actions=[action])

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return AgentResult(agent_id="executor", observations=["Execute click"], proposed_actions=[action])

    worker.jasper.planner_callable = fake_planner
    worker.jasper.executor_callable = fake_executor

    captured_requests: list[ApprovalRequest] = []

    def on_approval_request(req: ApprovalRequest):
        captured_requests.append(req)
        asyncio.get_running_loop().call_soon(
            lambda: worker.resolve_approval(req.gate_id, granted=False)
        )

    worker.approval_requested.connect(on_approval_request)

    with pytest.raises(PermissionError, match="User denied approval"):
        await worker.jasper.respond("/auto click button 1")

    # WRITE operations MUST trigger approval
    assert len(captured_requests) == 1
    assert captured_requests[0].action.tool_name == "browser_click" 
