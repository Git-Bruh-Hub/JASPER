"""tests/test_settings_workspace.py -- Tests for SettingsWorkspace and model configuration."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

import app.core.config as cfg
from app.ui.main_window import MainWindow
from app.ui.settings_workspace import SettingsWorkspace
from app.ui.worker import JasperWorker


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_settings_workspace_initialization(qapp):
    widget = SettingsWorkspace()
    assert widget.input_host.text() == cfg.OLLAMA_HOST
    assert widget.combo_primary_model.currentText() == cfg.JASPER_MODEL
    assert widget.combo_fast_model.currentText() == cfg.JASPER_FAST_MODEL
    assert widget.combo_vision_model.currentText() == cfg.JASPER_VISION_MODEL
    assert widget.spin_max_turns.value() >= 1
    assert widget.spin_timeout.value() >= 10


def test_fetch_ollama_models_success(qapp):
    widget = SettingsWorkspace()

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "models": [
            {"name": "qwen3:14b"},
            {"name": "qwen3:8b"},
            {"name": "deepseek-r1:14b"},
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        models = widget.fetch_ollama_models()

    assert "deepseek-r1:14b" in models
    assert "qwen3:14b" in models
    assert "3 models available" in widget.label_connection_status.text()
    assert widget.combo_primary_model.findText("deepseek-r1:14b") >= 0


def test_fetch_ollama_models_failure(qapp):
    widget = SettingsWorkspace()

    with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("Host unreachable")):
        models = widget.fetch_ollama_models()

    assert models == []
    assert "Offline" in widget.label_connection_status.text()


def test_save_settings_updates_config_and_emits_signal(qapp, tmp_path):
    widget = SettingsWorkspace()

    # Modify some fields
    widget.input_host.setText("http://192.168.1.50:11434")
    widget.combo_primary_model.setEditText("custom-model:32b")
    widget.combo_fast_model.setEditText("custom-fast:7b")
    widget.spin_max_turns.setValue(7)
    widget.spin_timeout.setValue(60)

    # Mock env path
    fake_env = tmp_path / ".env"
    fake_env.write_text("OLD_KEY=value\n", encoding="utf-8")

    signal_received = []
    widget.settings_saved.connect(lambda s: signal_received.append(s))

    with patch.object(cfg, "ROOT", tmp_path):
        saved = widget.save_settings()

    assert len(signal_received) == 1
    assert signal_received[0]["JASPER_MODEL"] == "custom-model:32b"
    assert signal_received[0]["JASPER_FAST_MODEL"] == "custom-fast:7b"
    assert signal_received[0]["OLLAMA_HOST"] == "http://192.168.1.50:11434"
    assert signal_received[0]["MAX_TURNS"] == 7
    assert signal_received[0]["TIMEOUT_SECONDS"] == 60

    # In-memory config updated
    assert cfg.JASPER_MODEL == "custom-model:32b"
    assert cfg.OLLAMA_HOST == "http://192.168.1.50:11434"

    # Persisted to fake .env
    env_content = fake_env.read_text(encoding="utf-8")
    assert "JASPER_MODEL=custom-model:32b" in env_content
    assert "OLLAMA_HOST=http://192.168.1.50:11434" in env_content
    assert "OLD_KEY=value" in env_content


def test_reset_defaults(qapp):
    widget = SettingsWorkspace()
    widget.input_host.setText("http://random-host:9999")
    widget.spin_max_turns.setValue(9)

    widget.reset_defaults()

    assert widget.input_host.text() == "http://127.0.0.1:11434"
    assert widget.combo_primary_model.currentText() == "qwen3:14b"
    assert widget.spin_max_turns.value() == 4
    assert widget.spin_timeout.value() == 45
    assert "Reset to defaults" in widget.label_feedback.text()


def test_main_window_settings_tab_integration(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    assert window.page_stack.count() == 7
    with patch.object(window.settings_page, "fetch_ollama_models") as mock_fetch:
        window._select_page(6)
        mock_fetch.assert_called_once()
    assert isinstance(window.page_stack.currentWidget(), SettingsWorkspace)
    assert window.workspace_hint.text() == "Settings & Models"



def test_settings_workspace_browser_controls(qapp, tmp_path):
    widget = SettingsWorkspace()
    assert hasattr(widget, "combo_browser_channel")
    assert hasattr(widget, "check_browser_headless")
    assert hasattr(widget, "input_browser_profile")

    # Change browser channel to msedge and headless to True
    idx = widget.combo_browser_channel.findData("msedge")
    assert idx >= 0
    widget.combo_browser_channel.setCurrentIndex(idx)
    widget.check_browser_headless.setChecked(True)

    fake_env = tmp_path / ".env"
    with patch.object(cfg, "ROOT", tmp_path):
        saved = widget.save_settings()

    assert saved["JASPER_BROWSER_CHANNEL"] == "msedge"
    assert saved["JASPER_BROWSER_HEADLESS"] is True
    assert cfg.JASPER_BROWSER_CHANNEL == "msedge"
    assert cfg.JASPER_BROWSER_HEADLESS is True

    env_content = fake_env.read_text(encoding="utf-8")
    assert "JASPER_BROWSER_CHANNEL=msedge" in env_content
    assert "JASPER_BROWSER_HEADLESS=true" in env_content


def test_settings_workspace_launch_browser_session(qapp):
    widget = SettingsWorkspace()
    assert hasattr(widget, "btn_launch_browser")
    assert widget.btn_launch_browser.text() == "🌐 Launch Browser (Log into Accounts)"

    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        widget._launch_browser_session()

        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
        assert "Launching browser" in widget.label_feedback.text()


def test_settings_workspace_restart_button(qapp):
    widget = SettingsWorkspace()
    assert hasattr(widget, "btn_restart")
    assert "Reload App" in widget.btn_restart.text()

    restarted = []
    widget.restart_requested.connect(lambda: restarted.append(True))
    widget.btn_restart.click()
    assert restarted == [True]


def test_main_window_restart_wiring(qapp, tmp_path):
    from PySide6.QtCore import QThread
    from app.ui.main_window import MainWindow
    from app.ui.worker import JasperWorker

    worker = JasperWorker(coordinator=None)
    thread = QThread()
    window = MainWindow(worker, thread)

    assert hasattr(window, "_reload_shortcut")
    assert window._reload_shortcut.key().toString() == "Ctrl+R"

    # Verify tray menu has restart action
    tray_menu = window._build_tray_menu()
    action_texts = [action.text() for action in tray_menu.actions()]
    assert any("Restart / Reload JASPER" in text for text in action_texts)

    # Test restart_application calls QProcess.startDetached
    with patch("PySide6.QtCore.QProcess.startDetached") as mock_start, patch("PySide6.QtWidgets.QApplication.quit") as mock_quit:
        window.restart_application()
        mock_start.assert_called_once()
        mock_quit.assert_called_once()

    window.close()


