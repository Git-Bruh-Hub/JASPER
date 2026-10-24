"""tests/test_audit_timeline.py -- Unit and integration tests for AuditTimelineDrawer and safety ledger."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.core.audit import (
    AuditEvent,
    add_audit_listener,
    clear_audit_records,
    get_recent_audit_records,
    record,
    remove_audit_listener,
)
from app.ui.audit_timeline import AuditTimelineDrawer
from app.ui.main_window import MainWindow
from app.ui.tasks_workspace import TasksWorkspace
from app.ui.worker import JasperWorker


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# 1. In-Memory Audit Records & Listeners
# ---------------------------------------------------------------------------

def test_audit_record_in_memory_and_listeners():
    clear_audit_records()

    captured = []
    listener = lambda rec: captured.append(rec)
    add_audit_listener(listener)

    try:
        record(
            AuditEvent.TOOL_EXECUTION,
            actor="coordinator",
            tool_name="run_terminal_command",
            resource="pytest tests/",
            status="SUCCESS",
        )
        record(
            AuditEvent.APPROVAL_GRANTED,
            actor="user",
            tool_name="edit_file_chunk",
            resource="config.json",
            user_approved=True,
        )

        assert len(captured) == 2
        assert captured[0]["tool_name"] == "run_terminal_command"
        assert captured[1]["event"] == "approval_granted"

        history = get_recent_audit_records()
        assert len(history) == 2
        # Newest first
        assert history[0]["event"] == "approval_granted"
        assert history[1]["event"] == "tool_execution"

        # Filter check
        tools_only = get_recent_audit_records(filter_event="tool_execution")
        assert len(tools_only) == 1
        assert tools_only[0]["tool_name"] == "run_terminal_command"

    finally:
        remove_audit_listener(listener)
        clear_audit_records()


# ---------------------------------------------------------------------------
# 2. AuditTimelineDrawer UI Components & Filtering
# ---------------------------------------------------------------------------

def test_audit_timeline_drawer_ui(qapp):
    drawer = AuditTimelineDrawer()
    drawer.clear_timeline()

    ev1 = {
        "timestamp": "2026-10-22T03:00:00Z",
        "event": "tool_execution",
        "actor": "coordinator",
        "tool_name": "read_text_file",
        "resource": "src/main.py",
        "status": "SUCCESS",
    }
    ev2 = {
        "timestamp": "2026-10-22T03:01:00Z",
        "event": "approval_granted",
        "actor": "user",
        "tool_name": "edit_file_chunk",
        "resource": "src/main.py",
        "status": "SUCCESS",
        "user_approved": True,
    }
    ev3 = {
        "timestamp": "2026-10-22T03:02:00Z",
        "event": "approval_denied",
        "actor": "user",
        "tool_name": "run_terminal_command",
        "resource": "rm -rf /",
        "status": "DENIED",
        "user_approved": False,
    }
    ev4 = {
        "timestamp": "2026-10-22T03:03:00Z",
        "event": "scope_denied",
        "actor": "permissions",
        "resource": "../outside_sandbox",
        "status": "DENIED",
    }

    drawer.add_event(ev1)
    drawer.add_event(ev2)
    drawer.add_event(ev3)
    drawer.add_event(ev4)

    assert len(drawer._events) == 4

    # Metrics check
    lbl_tot = drawer.badge_total.findChild(type(drawer.subtitle), "metric_total")
    lbl_tls = drawer.badge_tools.findChild(type(drawer.subtitle), "metric_tools")
    lbl_app = drawer.badge_approved.findChild(type(drawer.subtitle), "metric_approved")
    lbl_den = drawer.badge_denied.findChild(type(drawer.subtitle), "metric_denied")

    assert lbl_tot.text() == "4"
    assert lbl_tls.text() == "1"
    assert lbl_app.text() == "1"
    assert lbl_den.text() == "2"

    # Test Tools filter
    drawer._set_filter(AuditTimelineDrawer.FILTER_TOOLS)
    matching = [e for e in drawer._events if drawer._matches_filter(e)]
    assert len(matching) == 1
    assert matching[0]["tool_name"] == "read_text_file"

    # Test Approvals filter
    drawer._set_filter(AuditTimelineDrawer.FILTER_APPROVALS)
    matching_appr = [e for e in drawer._events if drawer._matches_filter(e)]
    assert len(matching_appr) == 2

    # Test Search filter
    drawer._set_filter(AuditTimelineDrawer.FILTER_ALL)
    drawer._on_search_changed("sandbox")
    matching_search = [e for e in drawer._events if drawer._matches_filter(e)]
    assert len(matching_search) == 1
    assert matching_search[0]["event"] == "scope_denied"

    # Clear timeline
    drawer.clear_timeline()
    assert len(drawer._events) == 0


# ---------------------------------------------------------------------------
# 3. TasksWorkspace Live Audit Events
# ---------------------------------------------------------------------------

def test_tasks_workspace_add_audit_event(qapp):
    tasks_page = TasksWorkspace()
    assert tasks_page.timeline_layout.count() == 0

    tasks_page.add_audit_event({
        "event": "tool_execution",
        "tool_name": "run_terminal_command",
        "resource": "pytest tests/test_math.py",
        "status": "SUCCESS",
    })
    assert tasks_page.timeline_layout.count() == 1

    tasks_page.add_audit_event({
        "event": "approval_requested",
        "tool_name": "edit_file_chunk",
    })
    assert tasks_page.timeline_layout.count() == 2

    tasks_page.add_audit_event({
        "event": "approval_granted",
        "tool_name": "edit_file_chunk",
    })
    assert tasks_page.timeline_layout.count() == 3


# ---------------------------------------------------------------------------
# 4. MainWindow Integration & /audit Command
# ---------------------------------------------------------------------------

def test_main_window_audit_integration(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    # 1. Drawer exists and is initially hidden
    assert hasattr(window, "audit_drawer")
    assert isinstance(window.audit_drawer, AuditTimelineDrawer)
    assert window.audit_drawer.isHidden()

    # 2. Header toggle button exists
    assert hasattr(window, "btn_audit_timeline")
    assert "🛡️ Audit" in window.btn_audit_timeline.text()

    # 3. Toggle drawer open
    window._toggle_audit_timeline()
    assert not window.audit_drawer.isHidden()
    assert window.btn_audit_timeline.isChecked()

    # 4. Toggle drawer closed
    window._toggle_audit_timeline()
    assert window.audit_drawer.isHidden()
    assert not window.btn_audit_timeline.isChecked()

    # 5. Chat command /audit opens drawer
    window.input.setText("/audit")
    window._on_send_clicked()
    assert not window.audit_drawer.isHidden()
    assert window.btn_audit_timeline.isChecked()
    assert any("Audit & Safety Timeline" in msg[1] for msg in window._messages)

    # 6. Incoming audit event updates counter
    window._on_audit_event({
        "timestamp": "2026-10-22T03:10:00Z",
        "event": "tool_execution",
        "actor": "coordinator",
        "tool_name": "surgical_edit",
        "status": "SUCCESS",
    })
    cnt = len(window.audit_drawer._events)
    assert f"🛡️ Audit ({cnt})" in window.btn_audit_timeline.text()
