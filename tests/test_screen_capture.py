"""tests/test_screen_capture.py -- Deterministic tests for desktop screen capture and vision UX."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.agents.desktop_wiring import register_desktop_tools
from app.tools.registry import Risk, ToolRegistry
from app.tools.vision import validate_image_path
from app.ui.main_window import MainWindow
from app.ui.vision_workspace import VisionWorkspace
from app.ui.worker import JasperWorker
from app.ui.screen_snipper import ScreenSnipper
from app.vision.capture import (
    capture_active_screen,
    capture_primary_screen,
    capture_virtual_desktop,
    desktop_take_screenshot,
)


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_capture_primary_screen_creates_valid_image(qapp, tmp_path: Path):
    saved_path = capture_primary_screen(save_dir=tmp_path)
    assert saved_path.exists()
    assert saved_path.is_file()
    assert saved_path.suffix == ".png"
    assert saved_path.stat().st_size > 0

    # Must pass JASPER's image security validator
    validated = validate_image_path(str(saved_path))
    assert validated == saved_path.resolve()


def test_capture_active_screen_and_virtual_desktop(qapp, tmp_path: Path):
    active_path = capture_active_screen(save_dir=tmp_path)
    assert active_path.exists()
    assert active_path.stat().st_size > 0
    assert validate_image_path(str(active_path)) == active_path.resolve()

    virtual_path = capture_virtual_desktop(save_dir=tmp_path)
    assert virtual_path.exists()
    assert virtual_path.stat().st_size > 0
    assert validate_image_path(str(virtual_path)) == virtual_path.resolve()


def test_desktop_take_screenshot_tool_handler(qapp, tmp_path: Path):
    with patch("app.vision.capture.DATA_DIR", tmp_path):
        res = desktop_take_screenshot()
    assert res["status"] == "success"
    assert res["action"] == "desktop_take_screenshot"
    assert Path(res["path"]).exists()


def test_register_desktop_tools_includes_screenshot(qapp):
    reg = ToolRegistry()
    register_desktop_tools(reg)
    tool_names = {t.name for t in reg.list()}
    assert "desktop_take_screenshot" in tool_names
    assert reg.get("desktop_take_screenshot").risk == Risk.READ


def test_screen_snipper_selection_math(qapp):
    from PySide6.QtCore import QPoint
    snipper = ScreenSnipper()

    # Forward drag
    snipper._start_pos = QPoint(100, 150)
    snipper._current_pos = QPoint(350, 400)
    rect = snipper._get_selection_rect()
    assert rect.x() == 100
    assert rect.y() == 150
    assert rect.width() == 250
    assert rect.height() == 250

    # Reverse drag (up-left)
    snipper._start_pos = QPoint(350, 400)
    snipper._current_pos = QPoint(100, 150)
    rev_rect = snipper._get_selection_rect()
    assert rev_rect.x() == 100
    assert rev_rect.y() == 150
    assert rev_rect.width() == 250
    assert rev_rect.height() == 250


def test_main_window_screen_button_and_command_parsing(qapp, tmp_path: Path):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    assert hasattr(window, "screen_button")
    assert window.screen_button.toolTip() != ""
    assert hasattr(window, "watch_button")

    fake_img = tmp_path / "snip_mock.png"
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    pixmap.save(str(fake_img), "PNG")

    # Test snipped callback attaches image
    window._on_chat_snipped(str(fake_img))
    assert window._attached_image_path == str(fake_img)
    assert window.attachment_chip.isVisible()

    # Sending text begins request with the attached image
    window._send_text()
    assert window._attached_image_path is None  # cleared upon send
    assert window.worker.begin_request.called


def test_main_window_watch_screen_mode(qapp, tmp_path: Path):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    # Initial state: not watching
    assert window._is_watching_screen is False
    assert window.watch_button.text() == "👁"
    assert window.watch_status.isHidden()

    fake_img = tmp_path / "live_watch.png"
    pixmap = QPixmap(50, 50)
    pixmap.fill()
    pixmap.save(str(fake_img), "PNG")

    received = []
    window.request_text_with_image.connect(lambda text, path: received.append((text, path)))

    with patch("app.vision.capture.capture_virtual_desktop", return_value=fake_img):
        # Toggle on (proactively triggers live situational analysis)
        window._toggle_watch_screen()
        assert window._is_watching_screen is True
        assert window.watch_button.text() == "⏹"
        assert not window.watch_status.isHidden()
        assert "WATCHING" in window.watch_status.text()
        assert len(received) == 1
        assert "What is on my screen" in received[0][0]

        # Simulate worker completion to test follow-up query
        window._set_busy(False)

        window.input.setText("What error is this?")
        window._send_text()

    assert len(received) == 2
    assert received[1][0] == "What error is this?"
    assert received[1][1] == str(fake_img)

    # Command: /unwatch
    window.input.setText("/unwatch")
    window._send_text()
    assert window._is_watching_screen is False
    assert window.watch_button.text() == "👁"
    assert window.watch_status.isHidden()


def test_get_active_desktop_tasks():
    from app.vision.capture import get_active_desktop_tasks
    tasks = get_active_desktop_tasks()
    assert isinstance(tasks, list)


def test_vision_workspace_capture_button(qapp, tmp_path: Path):
    vw = VisionWorkspace()
    assert hasattr(vw, "capture_button")

    fake_img = tmp_path / "screen_mock2.png"
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    pixmap.save(str(fake_img), "PNG")

    vw._on_snipped(str(fake_img))
    assert vw._image_path == str(fake_img.resolve())
    assert vw.analyze_button.isEnabled()

