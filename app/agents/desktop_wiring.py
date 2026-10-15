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
from app.tools.browser import (
    browser_click,
    browser_close,
    browser_get_dom,
    browser_navigate,
    browser_read_text,
    browser_type,
)
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
    existing_tools = {t.name for t in registry.list()}

    # 1. Filesystem write tool (Risk.WRITE -> requires human approval)
    if "write_text_file" not in existing_tools:
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

    # 2. Browser Navigation (Risk.READ -> read-only page inspection)
    if "browser_navigate" not in existing_tools:
        registry.register(Tool(
            name="browser_navigate",
            description="Navigate to a web URL and inspect the page title and interactive element snapshot.",
            risk=Risk.READ,
            handler=browser_navigate,
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to (e.g. 'https://news.ycombinator.com' or 'google.com').",
                    },
                },
                "required": ["url"],
            },
            resource_extractor=lambda args: str(args.get("url", "")),
            requires_filesystem=False,
        ))

    # 3. Browser DOM Snapshot (Risk.READ -> read-only DOM inspection)
    if "browser_get_dom" not in existing_tools:
        registry.register(Tool(
            name="browser_get_dom",
            description="Get the indexed interactive DOM snapshot of the currently open web page.",
            risk=Risk.READ,
            handler=browser_get_dom,
            parameters={"type": "object", "properties": {}},
            resource_extractor=lambda _: "browser://dom",
            requires_filesystem=False,
        ))

    # 4. Browser Read Text (Risk.READ -> read-only full-text reader)
    if "browser_read_text" not in existing_tools:
        registry.register(Tool(
            name="browser_read_text",
            description="Extract readable text content from the current web page.",
            risk=Risk.READ,
            handler=browser_read_text,
            parameters={"type": "object", "properties": {}},
            resource_extractor=lambda _: "browser://text",
            requires_filesystem=False,
        ))

    # 5. Browser Click (Risk.WRITE -> mutates page state, requires human approval)
    if "browser_click" not in existing_tools:
        registry.register(Tool(
            name="browser_click",
            description="Click on an indexed interactive element on the current web page. Requires human approval.",
            risk=Risk.WRITE,
            handler=browser_click,
            parameters={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "The integer index of the interactive element to click from the DOM snapshot, e.g. 1.",
                    },
                },
                "required": ["index"],
            },
            resource_extractor=lambda args: f"browser://click/[{args.get('index', '')}]",
            requires_filesystem=False,
        ))

    # 6. Browser Type (Risk.WRITE -> enters text into forms, requires human approval)
    if "browser_type" not in existing_tools:
        registry.register(Tool(
            name="browser_type",
            description="Type text into an indexed input field on the current web page. Requires human approval.",
            risk=Risk.WRITE,
            handler=browser_type,
            parameters={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "The integer index of the input field to type into from the DOM snapshot, e.g. 2.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to fill into the input field.",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Whether to press Enter after typing (defaults to false).",
                    },
                },
                "required": ["index", "text"],
            },
            resource_extractor=lambda args: f"browser://type/[{args.get('index', '')}]: {args.get('text', '')}",
            requires_filesystem=False,
        ))

    # 7. Browser Close (Risk.READ -> cleans up browser session)
    if "browser_close" not in existing_tools:
        registry.register(Tool(
            name="browser_close",
            description="Close the active browser session.",
            risk=Risk.READ,
            handler=browser_close,
            parameters={"type": "object", "properties": {}},
            resource_extractor=lambda _: "browser://close",
            requires_filesystem=False,
        ))


def build_desktop_autonomy(
    worker: JasperWorker,
    workspace_root: Path | None = None,
    timeout_seconds: float = 60.0,
) -> MultiAgentCoordinator:
    """Configure and attach MultiAgentCoordinator to JasperWorker for desktop autonomy.

    - Resolves workspace root containment boundary.
    - Registers safe autonomous tools (write_text_file, browser tools) in worker.jasper.registry.
    - Enforces ScopedPermissionManager with allowed risks (READ, WRITE).
    - Attaches coordinator to JasperWorker so /auto triggers approval dialogs.
    """
    workspace = (workspace_root or get_default_desktop_workspace()).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Register write and browser tools in orchestrator's shared tool registry
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
