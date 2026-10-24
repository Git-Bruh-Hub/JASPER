"""tests/test_notifications.py -- Tests for ToastBanner and desktop notification integration."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import app.core.config as cfg
from app.core.approval import ApprovalRequest
from app.tools.registry import Risk
from app.ui.main_window import MainWindow
from app.ui.settings_workspace import SettingsWorkspace
from app.ui.toast_banner import ToastBanner
from app.ui.worker import JasperWorker


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_toast_banner_lifecycle(qapp):
    banner = ToastBanner()
    assert banner.isHidden()

    # Show info toast
    banner.show_toast("Task In Progress", "Reading email inbox...", level="info", timeout_ms=0)
    assert not banner.isHidden()
    assert banner.label_title.text() == "Task In Progress"
    assert banner.label_message.text() == "Reading email inbox..."
    assert banner.label_icon.text() == "ℹ"

    # Show success toast
    banner.show_toast("Done", "Email summarized", level="success", timeout_ms=0)
    assert banner.label_icon.text() == "✓"

    # Show warning toast
    banner.show_toast("Warning", "High risk action", level="warning", timeout_ms=0)
    assert banner.label_icon.text() == "⚠"

    # Show error toast
    banner.show_toast("Failed", "Connection refused", level="error", timeout_ms=0)
    assert banner.label_icon.text() == "✕"

    # Dismissal
    dismissed = []
    banner.dismissed.connect(lambda: dismissed.append(True))
    banner.btn_close.click()
    assert banner.isHidden()
    assert len(dismissed) == 1


def test_main_window_notify_user_when_enabled(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    assert hasattr(window, "toast_banner")
    assert isinstance(window.toast_banner, ToastBanner)

    window._tray = MagicMock(spec=QSystemTrayIcon)
    window._tray.isVisible.return_value = True

    with patch.object(cfg, "JASPER_NOTIFICATIONS_ENABLED", True):
        window.notify_user("Test Alert", "Operation completed", level="success")

        assert not window.toast_banner.isHidden()
        assert window.toast_banner.label_title.text() == "Test Alert"
        assert window.toast_banner.label_message.text() == "Operation completed"
        window._tray.showMessage.assert_called_once()


def test_main_window_notify_user_when_disabled(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    window._tray = MagicMock(spec=QSystemTrayIcon)
    window._tray.isVisible.return_value = True

    with patch.object(cfg, "JASPER_NOTIFICATIONS_ENABLED", False):
        window.notify_user("Test Alert", "Operation completed", level="success")

        assert window.toast_banner.isHidden()
        window._tray.showMessage.assert_not_called()


def test_notify_on_finished_and_approval(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)
    window.notify_user = MagicMock()

    # 1. Test notification on approval requested
    from datetime import datetime, timezone

    action = MagicMock()
    action.tool_name = "browser_click"
    action.description = "Click Login button"

    req = MagicMock(spec=ApprovalRequest)
    req.gate_id = "gate-notif-1"
    req.action = action
    req.expires_at = datetime.now(timezone.utc)

    window._on_approval_requested(req)
    window.notify_user.assert_called_with(
        "JASPER Approval Required",
        "browser_click: Click Login button",
        level="warning",
    )

    # 2. Test notification on task finished (Chat tab = Response Generated)
    window._messages.append(("JASPER", "**Summary of 7-Eleven email:** Discount voucher valid until Sunday."))
    window._on_finished()
    window.notify_user.assert_called_with(
        "Response Generated",
        "Summary of 7-Eleven email: Discount voucher valid until Sunday.",
        level="success",
    )

    # 3. Test dynamic title when on Tasks tab (tab index 1)
    window._select_page(1)
    window._on_finished()
    window.notify_user.assert_called_with(
        "Task Completed",
        "Summary of 7-Eleven email: Discount voucher valid until Sunday.",
        level="success",
    )


def test_settings_workspace_notification_toggle(qapp, tmp_path):
    widget = SettingsWorkspace()
    assert hasattr(widget, "check_notifications")

    # Toggle off and save
    widget.check_notifications.setChecked(False)
    fake_env = tmp_path / ".env"
    with patch.object(cfg, "ROOT", tmp_path):
        saved = widget.save_settings()

    assert saved["JASPER_NOTIFICATIONS_ENABLED"] is False
    assert cfg.JASPER_NOTIFICATIONS_ENABLED is False

    env_content = fake_env.read_text(encoding="utf-8")
    assert "JASPER_NOTIFICATIONS_ENABLED=false" in env_content
