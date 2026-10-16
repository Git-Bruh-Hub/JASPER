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
from app.vision.capture import capture_primary_screen, desktop_take_screenshot


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


def test_main_window_screen_button_and_command_parsing(qapp, tmp_path: Path):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    assert hasattr(window, "screen_button")
    assert window.screen_button.toolTip() != ""

    fake_img = tmp_path / "screen_mock.png"
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    pixmap.save(str(fake_img), "PNG")

    # Test /screen command parsing in _send_text
    with patch("app.vision.capture.capture_primary_screen", return_value=fake_img):
        window.input.setText("/screen what is this compiler error?")
        window._send_text()

    assert window.input.text() == ""


def test_vision_workspace_capture_button(qapp, tmp_path: Path):
    vw = VisionWorkspace()
    assert hasattr(vw, "capture_button")

    fake_img = tmp_path / "screen_mock2.png"
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    pixmap.save(str(fake_img), "PNG")

    with patch("app.vision.capture.capture_primary_screen", return_value=fake_img):
        vw.set_image(str(fake_img))

    assert vw._image_path == str(fake_img.resolve())
    assert vw.analyze_button.isEnabled()
