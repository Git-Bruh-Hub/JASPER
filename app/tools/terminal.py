"""app/tools/terminal.py -- Scoped shell command execution tool for JASPER."""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess
from typing import Any

from app.tools.registry import Risk, Tool

_LOG = logging.getLogger("jasper.tools.terminal")

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_CHARS = 100_000

# Safety blacklist of destructive commands
PROHIBITED_COMMANDS = (
    "rmdir /s /q c:\\",
    "format ",
    "diskpart",
    "shutdown",
    "del /f /s /q c:\\",
    ":(){ :|:& };:",
)


def run_terminal_command(
    command: str,
    cwd: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute a shell command with a timeout and return captured output.

    Guarded by Risk.EXECUTE, requiring explicit human approval via the
    ApprovalDialog before execution.
    """
    clean_cmd = command.strip()
    if not clean_cmd:
        raise ValueError("Command cannot be empty.")

    cmd_lower = clean_cmd.lower()
    for prohibited in PROHIBITED_COMMANDS:
        if prohibited in cmd_lower:
            raise PermissionError(f"Command contains prohibited operation: {prohibited.strip()}")

    target_cwd = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    if not target_cwd.exists() or not target_cwd.is_dir():
        raise FileNotFoundError(f"Working directory does not exist: {target_cwd}")

    timeout = min(max(1.0, float(timeout_seconds)), 120.0)

    try:
        proc = subprocess.run(
            clean_cmd,
            shell=True,
            cwd=str(target_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = (proc.stdout or "")[:MAX_OUTPUT_CHARS]
        stderr = (proc.stderr or "")[:MAX_OUTPUT_CHARS]
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "command": clean_cmd,
            "cwd": str(target_cwd),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "")[:MAX_OUTPUT_CHARS] if hasattr(exc, "stdout") and exc.stdout else ""
        stderr = (exc.stderr or "")[:MAX_OUTPUT_CHARS] if hasattr(exc, "stderr") and exc.stderr else ""
        return {
            "status": "timeout",
            "exit_code": -1,
            "stdout": stdout,
            "stderr": f"Command timed out after {timeout} seconds.",
            "command": clean_cmd,
            "cwd": str(target_cwd),
        }
    except Exception as exc:
        _LOG.exception("Execution failed for command: %s", clean_cmd)
        return {
            "status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "command": clean_cmd,
            "cwd": str(target_cwd),
        }
