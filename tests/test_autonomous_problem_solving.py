"""tests/test_autonomous_problem_solving.py -- Tests for autonomous problem-solving & auto-test loop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
from app.agents.router import CognitiveMode, CognitiveRouter
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry
from app.tools.filesystem import edit_file_chunk, read_text_file


# ---------------------------------------------------------------------------
# 1. Router Intent Detection Tests
# ---------------------------------------------------------------------------

def test_router_detects_coding_and_fixing_intents():
    router = CognitiveRouter()

    assert router.route("run the regression tests") == CognitiveMode.AUTONOMOUS
    assert router.route("run pytest and fix any failures") == CognitiveMode.AUTONOMOUS
    assert router.route("run tests and fix the bug in math_ops.py") == CognitiveMode.AUTONOMOUS
    assert router.route("fix failing tests in test_system.py") == CognitiveMode.AUTONOMOUS
    assert router.route("debug the failing tests") == CognitiveMode.AUTONOMOUS
    assert router.route("resolve the failing test issue") == CognitiveMode.AUTONOMOUS
    assert router.route("/auto inspect the directory and run pytest") == CognitiveMode.AUTONOMOUS
    assert router.route("autonomously verify and fix the test suite") == CognitiveMode.AUTONOMOUS

    # Non-autonomous queries should stay SIMPLE or COLLABORATIVE
    assert router.route("what is a unit test in python?") == CognitiveMode.SIMPLE
    assert router.route("how do I write a pytest fixture?") == CognitiveMode.SIMPLE


# ---------------------------------------------------------------------------
# 2. Observation Formatting Tests
# ---------------------------------------------------------------------------

def test_format_turn_observations_terminal_and_chunks():
    # Terminal command success
    term_success_out = [{
        "tool": "run_terminal_command",
        "status": "success",
        "result": {
            "command": "pytest tests/test_calc.py",
            "exit_code": 0,
            "stdout": "collected 1 item\n1 passed in 0.05s",
            "stderr": "",
            "duration_seconds": 0.05,
            "status": "success",
        },
    }]
    formatted_success = MultiAgentCoordinator._format_turn_observations(term_success_out)
    assert "Command `pytest tests/test_calc.py` exited with code 0" in formatted_success
    assert "STDOUT:\ncollected 1 item\n1 passed in 0.05s" in formatted_success

    # Terminal command failure
    term_fail_out = [{
        "tool": "run_terminal_command",
        "status": "success",
        "result": {
            "command": "pytest tests/test_calc.py",
            "exit_code": 1,
            "stdout": "FAILURES: test_add",
            "stderr": "AssertionError: assert 1 - 2 == 3",
            "duration_seconds": 0.08,
            "status": "success",
        },
    }]
    formatted_fail = MultiAgentCoordinator._format_turn_observations(term_fail_out)
    assert "Command `pytest tests/test_calc.py` exited with code 1" in formatted_fail
    assert "STDOUT:\nFAILURES: test_add" in formatted_fail
    assert "STDERR:\nAssertionError: assert 1 - 2 == 3" in formatted_fail

    # Surgical chunk replacement
    edit_out = [{
        "tool": "edit_file_chunk",
        "status": "success",
        "result": {
            "status": "success",
            "path": "C:/workspace/calc.py",
            "filename": "calc.py",
            "bytes_written": 42,
            "message": "Successfully replaced target chunk in calc.py.",
        },
    }]
    formatted_edit = MultiAgentCoordinator._format_turn_observations(edit_out)
    assert "Successfully replaced target chunk in calc.py" in formatted_edit

    # Desktop screenshot
    screen_out = [{
        "tool": "desktop_take_screenshot",
        "status": "success",
        "result": {
            "status": "success",
            "path": "C:/workspace/screen_01.png",
            "filename": "screen_01.png",
            "observation": "Terminal window open with red traceback.",
        },
    }]
    formatted_screen = MultiAgentCoordinator._format_turn_observations(screen_out)
    assert "Screenshot 'screen_01.png' captured" in formatted_screen
    assert "Terminal window open with red traceback" in formatted_screen


# ---------------------------------------------------------------------------
# 3. Multi-Turn Autonomous Problem-Solving Loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_turn_auto_fix_and_test_loop(tmp_path: Path):
    """Simulate a complete 4-turn autonomous test -> inspect -> fix -> verify cycle."""
    code_file = tmp_path / "calc.py"
    code_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    reg = ToolRegistry()

    # Tool 1: Terminal Runner
    terminal_calls: list[str] = []

    def mock_terminal(command: str, cwd: str = "", timeout_seconds: float = 30.0) -> dict:
        terminal_calls.append(command)
        # Check current file content to determine whether test passes
        content = code_file.read_text(encoding="utf-8")
        if "return a + b" in content:
            return {
                "command": command,
                "exit_code": 0,
                "stdout": "test_add PASSED [100%]\n1 passed in 0.02s",
                "stderr": "",
                "duration_seconds": 0.02,
                "status": "success",
            }
        else:
            return {
                "command": command,
                "exit_code": 1,
                "stdout": "FAILED test_add - AssertionError: assert -1 == 3",
                "stderr": "",
                "duration_seconds": 0.03,
                "status": "success",
            }

    reg.register(Tool(
        name="run_terminal_command",
        description="Run terminal command",
        risk=Risk.READ,  # Set to READ for headless multi-turn test
        handler=mock_terminal,
        parameters={"type": "object", "properties": {"command": {"type": "string"}}},
        resource_extractor=lambda a: f"terminal://{a.get('command')}",
    ))

    # Tool 2: Read Text File
    reg.register(Tool(
        name="read_text_file",
        description="Read file",
        risk=Risk.READ,
        handler=lambda path, start_line=None, end_line=None: read_text_file(path, start_line, end_line),
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        resource_extractor=lambda a: a.get("path", ""),
    ))

    # Tool 3: Edit File Chunk
    reg.register(Tool(
        name="edit_file_chunk",
        description="Edit chunk",
        risk=Risk.READ,  # Set to READ for headless multi-turn test
        handler=lambda path, target, replacement: edit_file_chunk(path, target, replacement),
        parameters={"type": "object", "properties": {"path": {"type": "string"}, "target": {"type": "string"}, "replacement": {"type": "string"}}},
        resource_extractor=lambda a: a.get("path", ""),
    ))

    pm = ScopedPermissionManager(workspace_root=tmp_path, allowed_risks=frozenset({Risk.READ, Risk.WRITE}))
    coord = MultiAgentCoordinator(
        registry=reg,
        permissions=pm,
        budget=CoordinatorBudget(timeout_seconds=30.0, max_agent_rounds=20),
        workspace_root=tmp_path,
    )

    turn_count = 0

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        nonlocal turn_count
        turn_count += 1

        if turn_count == 1:
            # Turn 1: Run test suite to check baseline
            action = ProposedAction(
                tool_name="run_terminal_command",
                arguments={"command": "pytest tests/test_calc.py"},
                scope=PermissionScope(risk="read", resource_scope="terminal://pytest", operation="run_terminal_command", approval_requirement=ApprovalRequirement.NEVER),
                rationale="Run initial test suite",
            )
            return AgentResult(agent_id="planner", observations=["Running tests"], proposed_actions=[action])

        elif turn_count == 2:
            # Turn 2: Saw test failed in task.user_text, inspect code
            assert "FAILED test_add" in task.user_text or "exit code 1" in task.user_text
            action = ProposedAction(
                tool_name="read_text_file",
                arguments={"path": str(code_file), "start_line": 1, "end_line": 5},
                scope=PermissionScope(risk="read", resource_scope=str(code_file), operation="read_text_file", approval_requirement=ApprovalRequirement.NEVER),
                rationale="Inspect buggy function",
            )
            return AgentResult(agent_id="planner", observations=["Reading file to find bug"], proposed_actions=[action])

        elif turn_count == 3:
            # Turn 3: Saw `return a - b` in code, surgically edit chunk
            assert "return a - b" in task.user_text
            action = ProposedAction(
                tool_name="edit_file_chunk",
                arguments={"path": str(code_file), "target": "return a - b", "replacement": "return a + b"},
                scope=PermissionScope(risk="read", resource_scope=str(code_file), operation="edit_file_chunk", approval_requirement=ApprovalRequirement.NEVER),
                rationale="Fix subtraction bug in add function",
            )
            return AgentResult(agent_id="planner", observations=["Applying surgical fix"], proposed_actions=[action])

        elif turn_count == 4:
            # Turn 4: Saw edit confirmed, re-run test to verify
            assert "Successfully replaced target chunk" in task.user_text
            action = ProposedAction(
                tool_name="run_terminal_command",
                arguments={"command": "pytest tests/test_calc.py"},
                scope=PermissionScope(risk="read", resource_scope="terminal://pytest", operation="run_terminal_command", approval_requirement=ApprovalRequirement.NEVER),
                rationale="Verify test passes after fix",
            )
            return AgentResult(agent_id="planner", observations=["Verifying fix with pytest"], proposed_actions=[action])

        else:
            # Turn 5: Test passed! Conclude and report
            assert "test_add PASSED" in task.user_text or "exit code 0" in task.user_text
            return AgentResult(
                agent_id="planner",
                observations=["Bug in calc.py was identified as subtraction instead of addition. Surgically fixed and verified with pytest: 1 passed."],
                proposed_actions=[],
            )

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return plan.planner_result

    answer = await coord.run_multi_agent(
        planner_callable=fake_planner,
        executor_callable=fake_executor,
        user_text="Please run the tests and fix any failing tests in calc.py",
        max_turns=6,
    )

    # 4 tool execution turns + 1 final conclusion turn
    assert turn_count == 5
    assert len(terminal_calls) == 2
    # Verify file was actually modified on disk
    assert "return a + b" in code_file.read_text(encoding="utf-8")
    assert "Bug in calc.py was identified" in answer
    assert "verified with pytest" in answer


# ---------------------------------------------------------------------------
# 4. Approval Gate Enforcement in Problem-Solving Loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_fix_approval_gate_enforcement(tmp_path: Path):
    """Verify that edit_file_chunk and run_terminal_command require approval in multi-turn loop."""
    code_file = tmp_path / "hello.py"
    code_file.write_text("print('bad')\n", encoding="utf-8")

    reg = ToolRegistry()
    reg.register(Tool(
        name="edit_file_chunk",
        description="Edit chunk",
        risk=Risk.WRITE,  # Requires approval
        handler=lambda path, target, replacement: edit_file_chunk(path, target, replacement),
        path_argument="path",
        requires_filesystem=True,
        resource_extractor=lambda a: a.get("path", ""),
    ))

    pm = ScopedPermissionManager(workspace_root=tmp_path, allowed_risks=frozenset({Risk.READ, Risk.WRITE}))

    received_requests = []

    def mock_approval_notifier(req):
        received_requests.append(req)
        # Asynchronously approve the gate
        asyncio.create_task(_resolve_after_delay(coord, req.gate_id, True))

    async def _resolve_after_delay(coord_obj, gate_id, granted):
        await asyncio.sleep(0.01)
        coord_obj.resolve_approval(gate_id, granted)

    coord = MultiAgentCoordinator(
        registry=reg,
        permissions=pm,
        approval_notifier=mock_approval_notifier,
        budget=CoordinatorBudget(timeout_seconds=30.0),
        workspace_root=tmp_path,
    )

    async def single_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        action = ProposedAction(
            tool_name="edit_file_chunk",
            arguments={"path": str(code_file), "target": "print('bad')", "replacement": "print('good')"},
            scope=PermissionScope(risk="write", resource_scope=str(code_file), operation="edit_file_chunk", approval_requirement=ApprovalRequirement.ALWAYS),
            rationale="Fix greeting",
        )
        return AgentResult(agent_id="planner", observations=["Editing file"], proposed_actions=[action])

    async def single_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return plan.planner_result

    answer = await coord.run_multi_agent(
        planner_callable=single_planner,
        executor_callable=single_executor,
        user_text="Fix the file",
        max_turns=1,
    )

    # Proves ApprovalGate was engaged, notifier received request, and action was executed
    assert len(received_requests) == 1
    assert received_requests[0].action.tool_name == "edit_file_chunk"
    assert "print('good')" in code_file.read_text(encoding="utf-8")

