"""app/agents/desktop_wiring.py -- Factory for Desktop Autonomy Coordinator.

Wired into PySide6 desktop runtime to safely enable autonomous execution (/auto)
with ScopedPermissionManager, workspace root containment, and modal ApprovalDialog.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.agents.coordinator import CoordinatorBudget
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.filesystem import write_text_file
from app.tools.registry import Risk, Tool, ToolRegistry
from app.ui.worker import JasperWorker

_LOG = logging.getLogger("jasper.desktop_wiring")


def get_default_desktop_workspace() -> Path:
    """Return the resolved directory for desktop autonomy tasks."""
    raw = os.environ.get("JASPER_WORKSPACE", "")
    workspace = (Path(raw) if raw else (Path.cwd() / "workspace")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def register_desktop_tools(registry: ToolRegistry) -> None:
    """Register safe autonomous desktop tools into the provided registry."""
    if "write_text_file" not in {t.name for t in registry.list()}:
        registry.register(Tool(
            name="write_text_file",
            description="Write text content to a file inside the allowed workspace directory. Requires human approval.",
            risk=Risk.WRITE,
            handler=write_text_file,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to write within the workspace, e.g. workspace/output.txt or script.py.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
            path_argument="path",
            requires_filesystem=True,
            resource_extractor=lambda args: args.get("path", ""),
        ))


def build_desktop_autonomy(
    worker: JasperWorker,
    workspace_root: Path | None = None,
    timeout_seconds: float = 60.0,
) -> MultiAgentCoordinator:
    """Configure and attach MultiAgentCoordinator to JasperWorker for desktop autonomy.

    - Resolves workspace root containment boundary.
    - Registers safe autonomous tools (write_text_file) in worker.jasper.registry.
    - Enforces ScopedPermissionManager with allowed risks (READ, WRITE).
    - Attaches coordinator to JasperWorker so /auto triggers approval dialogs.
    """
    workspace = (workspace_root or get_default_desktop_workspace()).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Register write tools in orchestrator's shared tool registry
    register_desktop_tools(worker.jasper.registry)

    permissions = ScopedPermissionManager(
        workspace_root=workspace,
        allowed_risks=frozenset({Risk.READ, Risk.WRITE}),
        actor="desktop_coordinator",
    )

    coordinator = MultiAgentCoordinator(
        registry=worker.jasper.registry,
        permissions=permissions,
        budget=CoordinatorBudget(timeout_seconds=timeout_seconds),
        workspace_root=workspace,
    )

    worker.set_coordinator(coordinator)
    _LOG.info("Desktop autonomy enabled with workspace root: %s", workspace)
    return coordinator
