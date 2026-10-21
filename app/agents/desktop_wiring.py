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
    browser_close_tab,
    browser_get_dom,
    browser_list_tabs,
    browser_navigate,
    browser_new_tab,
    browser_read_inbox,
    browser_read_text,
    browser_search,
    browser_summarize,
    browser_switch_tab,
    browser_type,
)
from app.tools.filesystem import edit_file_chunk, write_text_file
from app.tools.terminal import run_terminal_command
from app.tools.registry import Risk, Tool, ToolRegistry
from app.ui.worker import JasperWorker

_LOG = logging.getLogger("jasper.desktop_wiring")


def get_default_desktop_workspace() -> Path:
    """Return the resolved directory for desktop autonomy tasks."""
    raw = os.environ.get("JASPER_WORKSPACE", "")
    workspace = (Path(raw) if raw else (Path.cwd() / "workspace")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def register_desktop_tools(registry: ToolRegistry, vision: Any = None) -> None:
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

    # 1.1. Filesystem surgical edit tool (Risk.WRITE -> requires human approval)
    if "edit_file_chunk" not in existing_tools:
        registry.register(Tool(
            name="edit_file_chunk",
            description="Surgically replace a unique target chunk in an existing file within the workspace. Requires human approval.",
            risk=Risk.WRITE,
            handler=edit_file_chunk,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit within the workspace.",
                    },
                    "target": {
                        "type": "string",
                        "description": "The exact existing text chunk to find and replace. Must match uniquely.",
                    },
                    "replacement": {
                        "type": "string",
                        "description": "The new replacement text content.",
                    },
                },
                "required": ["path", "target", "replacement"],
            },
            path_argument="path",
            requires_filesystem=True,
            resource_extractor=lambda args: args.get("path", ""),
        ))

    # 1.2. Terminal command execution tool (Risk.EXECUTE -> requires human approval)
    if "run_terminal_command" not in existing_tools:
        registry.register(Tool(
            name="run_terminal_command",
            description="Execute a shell command with a timeout and return stdout/stderr. Requires human approval.",
            risk=Risk.EXECUTE,
            handler=run_terminal_command,
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g. 'pytest tests/test_system.py' or 'git status').",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory path. Defaults to workspace root.",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Optional execution timeout in seconds (default 30, max 120).",
                    },
                },
                "required": ["command"],
            },
            requires_filesystem=False,
            resource_extractor=lambda args: f"terminal://{args.get('command', '')[:40]}",
        ))

    # 1.5. Browser Search (Risk.READ -> read-only web search)
    if "browser_search" not in existing_tools:
        registry.register(Tool(
            name="browser_search",
            description="Search the web using DuckDuckGo and inspect the search results snapshot.",
            risk=Risk.READ,
            handler=browser_search,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'local AI models 2026').",
                    },
                },
                "required": ["query"],
            },
            resource_extractor=lambda args: f"https://duckduckgo.com/?q={args.get('query', '')}",
            requires_filesystem=False,
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

    # 4.5. Browser Summarize (Risk.READ -> read-only web page & topic summarization)
    if "browser_summarize" not in existing_tools:
        registry.register(Tool(
            name="browser_summarize",
            description="Extract readable content from the active browser or navigate to a URL and summarize information matching a topic or email query (e.g. '7-Eleven receipt', 'order summary', 'flight details').",
            risk=Risk.READ,
            handler=browser_summarize,
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Optional URL to navigate to first. If omitted, summarizes the currently open web page.",
                    },
                    "topic_or_query": {
                        "type": "string",
                        "description": "Topic, keywords, or search term to summarize from the page (e.g. '7-eleven', 'receipt', 'order #').",
                    },
                },
                "required": [],
            },
            resource_extractor=lambda args: f"browser://summarize?topic={args.get('topic_or_query', '')}&url={args.get('url', '')}",
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

    # 7.1. Browser Read Inbox (Risk.READ -> read-only email extraction)
    if "browser_read_inbox" not in existing_tools:
        registry.register(Tool(
            name="browser_read_inbox",
            description="Extract email headers and previews (sender, subject, snippet) from webmail / inbox pages matching an optional query (e.g. '7-eleven', 'order', 'voucher').",
            risk=Risk.READ,
            handler=browser_read_inbox,
            parameters={
                "type": "object",
                "properties": {
                    "filter_query": {
                        "type": "string",
                        "description": "Optional keyword or sender name to filter inbox emails.",
                    },
                },
                "required": [],
            },
            resource_extractor=lambda args: f"browser://inbox?filter={args.get('filter_query', '')}",
            requires_filesystem=False,
        ))

    # 7.2. Browser Multi-Tab Management Tools (Risk.READ)
    if "browser_list_tabs" not in existing_tools:
        registry.register(Tool(
            name="browser_list_tabs",
            description="List all currently open browser tabs with index, title, URL, and active status.",
            risk=Risk.READ,
            handler=browser_list_tabs,
            parameters={"type": "object", "properties": {}},
            resource_extractor=lambda _: "browser://tabs",
            requires_filesystem=False,
        ))

    if "browser_new_tab" not in existing_tools:
        registry.register(Tool(
            name="browser_new_tab",
            description="Open a new browser tab, optionally navigating directly to a target URL.",
            risk=Risk.READ,
            handler=browser_new_tab,
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Optional URL to navigate to in the new tab.",
                    },
                },
                "required": [],
            },
            resource_extractor=lambda args: f"browser://new_tab?url={args.get('url', '')}",
            requires_filesystem=False,
        ))

    if "browser_switch_tab" not in existing_tools:
        registry.register(Tool(
            name="browser_switch_tab",
            description="Switch active focus to a specific open tab by its integer index.",
            risk=Risk.READ,
            handler=browser_switch_tab,
            parameters={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "The integer index of the tab to switch to.",
                    },
                },
                "required": ["index"],
            },
            resource_extractor=lambda args: f"browser://switch_tab/[{args.get('index', '')}]",
            requires_filesystem=False,
        ))

    if "browser_close_tab" not in existing_tools:
        registry.register(Tool(
            name="browser_close_tab",
            description="Close a specific tab by its index, or the active tab if index is omitted.",
            risk=Risk.READ,
            handler=browser_close_tab,
            parameters={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "Optional integer index of the tab to close.",
                    },
                },
                "required": [],
            },
            resource_extractor=lambda args: f"browser://close_tab/[{args.get('index', '')}]",
            requires_filesystem=False,
        ))

    # 8. Desktop Take Screenshot (Risk.READ -> read-only desktop observation)
    if "desktop_take_screenshot" not in existing_tools:
        from app.vision.capture import capture_active_screen

        async def _desktop_take_screenshot(question: str = "") -> dict[str, Any]:
            path = capture_active_screen()
            res = {
                "status": "success",
                "action": "desktop_take_screenshot",
                "path": str(path),
                "filename": path.name,
            }
            vm = vision
            if vm is None:
                try:
                    from app.main import build_vision_manager
                    vm = build_vision_manager()
                except Exception:
                    vm = None

            if vm is not None:
                try:
                    prompt = question.strip() if question and question.strip() else (
                        "Describe everything visible across the entire screen in detail, "
                        "including all open windows, applications, text, and active content."
                    )
                    analysis = await vm.analyze(path, prompt=prompt)
                    res["observation"] = analysis.answer
                except Exception as exc:
                    _LOG.debug("Automatic vision analysis for screenshot skipped or failed: %s", exc)
                    res["observation"] = f"Screenshot saved to {path.name}."
            else:
                res["observation"] = f"Screenshot saved to {path.name}."
            return res

        registry.register(Tool(
            name="desktop_take_screenshot",
            description=(
                "Capture the user's desktop display and visually analyze what is visible on the screen. "
                "Use this tool when the user asks what is on their screen, wants a screenshot described, "
                "or wants to observe the current desktop."
            ),
            risk=Risk.READ,
            handler=_desktop_take_screenshot,
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Optional specific question or element to check on screen. If omitted, the full screen is analyzed.",
                    },
                },
                "required": [],
            },
            resource_extractor=lambda _: "desktop://screen",
            requires_filesystem=False,
        ))


def build_desktop_autonomy(
    worker: JasperWorker,
    workspace_root: Path | None = None,
    timeout_seconds: float = 180.0,
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
    register_desktop_tools(worker.jasper.registry, vision=getattr(worker, "vision", None))

    permissions = ScopedPermissionManager(
        workspace_root=workspace,
        allowed_risks=frozenset({Risk.READ, Risk.WRITE, Risk.EXECUTE}),
        actor="desktop_coordinator",
    )

    coordinator = MultiAgentCoordinator(
        registry=worker.jasper.registry,
        permissions=permissions,
        budget=CoordinatorBudget(timeout_seconds=timeout_seconds, max_agent_rounds=24),
        workspace_root=workspace,
    )

    worker.set_coordinator(coordinator)
    _LOG.info("Desktop autonomy enabled with workspace root: %s", workspace)
    return coordinator
