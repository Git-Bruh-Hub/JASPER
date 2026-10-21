"""Unit and integration tests for surgical file editing and terminal command execution."""

from __future__ import annotations

from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.tools.filesystem import edit_file_chunk, read_text_file, write_text_file
from app.tools.terminal import run_terminal_command
from app.tools.registry import Risk, ToolRegistry
from app.agents.adapters import _map_approval
from app.agents.contracts import ApprovalRequirement
from app.core.scoped_permissions import ScopedPermissionManager


# ---------------------------------------------------------------------------
# 1. read_text_file with line slicing
# ---------------------------------------------------------------------------

def test_read_text_file_full_and_sliced(tmp_path: Path):
    test_file = tmp_path / "sample.py"
    content = (
        "def func_a():\n"
        "    return 1\n"
        "\n"
        "def func_b():\n"
        "    return 2\n"
    )
    test_file.write_text(content, encoding="utf-8")

    # Full read without slice parameters
    full = read_text_file(str(test_file))
    assert full == content

    # Sliced read lines 1 to 2
    slice_1_2 = read_text_file(str(test_file), start_line=1, end_line=2)
    assert slice_1_2 == "1: def func_a():\n2:     return 1"

    # Sliced read lines 4 to 5
    slice_4_5 = read_text_file(str(test_file), start_line=4, end_line=5)
    assert slice_4_5 == "4: def func_b():\n5:     return 2"

    # Beyond end of file
    beyond = read_text_file(str(test_file), start_line=10, end_line=12)
    assert "beyond end of file" in beyond


# ---------------------------------------------------------------------------
# 2. edit_file_chunk surgical replace
# ---------------------------------------------------------------------------

def test_edit_file_chunk_success(tmp_path: Path):
    test_file = tmp_path / "code.py"
    test_file.write_text("def hello():\n    print('old')\n", encoding="utf-8")

    res = edit_file_chunk(
        str(test_file),
        target="print('old')",
        replacement="print('new')",
    )

    assert res["status"] == "success"
    assert test_file.read_text(encoding="utf-8") == "def hello():\n    print('new')\n"


def test_edit_file_chunk_target_not_found(tmp_path: Path):
    test_file = tmp_path / "code.py"
    test_file.write_text("x = 10\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Target string not found"):
        edit_file_chunk(str(test_file), target="y = 20", replacement="y = 30")


def test_edit_file_chunk_ambiguous_duplicate_target(tmp_path: Path):
    test_file = tmp_path / "code.py"
    test_file.write_text("return 42\nreturn 42\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Target string occurs 2 times"):
        edit_file_chunk(str(test_file), target="return 42", replacement="return 99")


def test_edit_file_chunk_disallowed_extension(tmp_path: Path):
    exe_file = tmp_path / "binary.exe"
    exe_file.write_text("some text", encoding="utf-8")

    with pytest.raises(ValueError, match="File extension '.exe' is not allowlisted"):
        edit_file_chunk(str(exe_file), target="some", replacement="other")


# ---------------------------------------------------------------------------
# 3. run_terminal_command execution and security boundaries
# ---------------------------------------------------------------------------

def test_run_terminal_command_success(tmp_path: Path):
    res = run_terminal_command(
        command="python -c \"print('hello from terminal')\"",
        cwd=str(tmp_path),
        timeout_seconds=10.0,
    )
    assert res["status"] == "success"
    assert res["exit_code"] == 0
    assert "hello from terminal" in res["stdout"]


def test_run_terminal_command_non_zero_exit(tmp_path: Path):
    res = run_terminal_command(
        command="python -c \"import sys; sys.exit(42)\"",
        cwd=str(tmp_path),
        timeout_seconds=10.0,
    )
    assert res["status"] == "error"
    assert res["exit_code"] == 42


def test_run_terminal_command_prohibited_blocked():
    with pytest.raises(PermissionError, match="prohibited operation"):
        run_terminal_command("format C: /fs:ntfs")

    with pytest.raises(PermissionError, match="prohibited operation"):
        run_terminal_command("rmdir /s /q c:\\")


def test_run_terminal_command_timeout(tmp_path: Path):
    res = run_terminal_command(
        command="python -c \"import time; time.sleep(5)\"",
        cwd=str(tmp_path),
        timeout_seconds=0.5,
    )
    assert res["status"] == "timeout"
    assert res["exit_code"] == -1
    assert "timed out" in res["stderr"]


# ---------------------------------------------------------------------------
# 4. Wiring and approval risk policy
# ---------------------------------------------------------------------------

def test_wiring_and_approval_policy():
    reg = ToolRegistry()
    from app.agents.desktop_wiring import register_desktop_tools
    register_desktop_tools(reg)

    edit_tool = reg.get("edit_file_chunk")
    assert edit_tool is not None
    assert edit_tool.risk == Risk.WRITE

    term_tool = reg.get("run_terminal_command")
    assert term_tool is not None
    assert term_tool.risk == Risk.EXECUTE

    # Both tools require ALWAYS human approval before execution
    assert _map_approval(edit_tool.risk) == ApprovalRequirement.ALWAYS
    assert _map_approval(term_tool.risk) == ApprovalRequirement.ALWAYS

    # ScopedPermissionManager allows READ, WRITE, and EXECUTE
    perms = ScopedPermissionManager(
        workspace_root=Path.cwd(),
        allowed_risks=frozenset({Risk.READ, Risk.WRITE, Risk.EXECUTE}),
    )
    perms.check_tool(edit_tool)
    perms.check_tool(term_tool)
