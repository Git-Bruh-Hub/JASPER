"""Settings workspace widget for configuring local models, Ollama host, and autonomy limits."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import urllib.request
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import app.core.config as cfg

_LOG = logging.getLogger("jasper.ui.settings")


class SettingsWorkspace(QWidget):
    """Desktop workspace for configuring local models, Ollama host, and autonomy limits."""

    settings_saved = Signal(dict)
    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._detected_models: list[str] = []
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._clear_feedback)

        self._init_ui()
        self.load_from_config()

        # Check Ollama connection and populate available models (in real desktop execution)
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            QTimer.singleShot(150, self.fetch_ollama_models)

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        # Scroll Area for clean presentation across window sizes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 16, 16)
        container_layout.setSpacing(16)

        # Title & Subtitle Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Settings & Configuration")
        title.setObjectName("workspaceTitle")
        title.setStyleSheet("font-size: 15pt; font-weight: 700; color: #ffffff;")
        subtitle = QLabel("Configure local Ollama models, host connectivity, autonomous reasoning limits, and permissions.")
        subtitle.setStyleSheet("color: #8c8c8c; font-size: 9.5pt;")
        header.addWidget(title)
        header.addWidget(subtitle)
        container_layout.addLayout(header)

        # Section 1: Ollama Server & Connectivity
        container_layout.addWidget(self._build_server_card())

        # Section 2: Model Selection
        container_layout.addWidget(self._build_models_card())

        # Section 3: Autonomous Agent Execution & Safety
        container_layout.addWidget(self._build_autonomy_card())

        # Section 4: System & Memory
        container_layout.addWidget(self._build_system_card())

        # Section 5: Browser & Web Automation
        container_layout.addWidget(self._build_browser_card())

        container_layout.addStretch(1)

        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        # Bottom Action Bar
        action_bar = self._build_action_bar()
        root_layout.addWidget(action_bar)

    def _build_server_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("class", "settingsCard")
        card.setStyleSheet("background: #1e1e1e; border: 1px solid #303030; border-radius: 8px; padding: 14px;")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        sec_title = QLabel("Ollama Host & Connectivity")
        sec_title.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 10.5pt;")
        header_row.addWidget(sec_title)
        header_row.addStretch(1)

        self.label_connection_status = QLabel("Checking connection…")
        self.label_connection_status.setStyleSheet("color: #888888; font-size: 9pt;")
        header_row.addWidget(self.label_connection_status)
        layout.addLayout(header_row)

        desc = QLabel("JASPER routes inference requests directly to your local Ollama server.")
        desc.setStyleSheet("color: #8c8c8c; font-size: 9pt;")
        layout.addWidget(desc)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        lbl = QLabel("Server URL:")
        lbl.setStyleSheet("color: #d0d0d0; font-size: 9.5pt; font-weight: 500;")
        input_row.addWidget(lbl)

        self.input_host = QLineEdit()
        self.input_host.setPlaceholderText("http://127.0.0.1:11434")
        self.input_host.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 6px 10px;"
        )
        input_row.addWidget(self.input_host, 1)

        self.btn_refresh_models = QPushButton("Test & Refresh Models")
        self.btn_refresh_models.setStyleSheet(
            "background: #282828; border: 1px solid #444; border-radius: 5px; color: #e0e0e0; padding: 6px 12px; font-weight: 500;"
        )
        self.btn_refresh_models.clicked.connect(self.fetch_ollama_models)
        input_row.addWidget(self.btn_refresh_models)

        layout.addLayout(input_row)
        return card

    def _build_models_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("class", "settingsCard")
        card.setStyleSheet("background: #1e1e1e; border: 1px solid #303030; border-radius: 8px; padding: 14px;")
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        sec_title = QLabel("Model Routing & Selection")
        sec_title.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 10.5pt;")
        layout.addWidget(sec_title)

        desc = QLabel("Assign specialized local models for reasoning, fast responses, and vision.")
        desc.setStyleSheet("color: #8c8c8c; font-size: 9pt;")
        layout.addWidget(desc)

        # Primary / Deep Reasoning Model
        row1 = QVBoxLayout()
        row1.setSpacing(4)
        lbl1 = QLabel("Primary / Deep Reasoning Model (JASPER_MODEL)")
        lbl1.setStyleSheet("color: #d0d0d0; font-size: 9.5pt; font-weight: 500;")
        hint1 = QLabel("Used for autonomous planning, multi-step execution, and complex synthesis.")
        hint1.setStyleSheet("color: #777777; font-size: 8.5pt;")
        self.combo_primary_model = QComboBox()
        self.combo_primary_model.setEditable(True)
        self.combo_primary_model.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 6px 10px;"
        )
        row1.addWidget(lbl1)
        row1.addWidget(hint1)
        row1.addWidget(self.combo_primary_model)
        layout.addLayout(row1)

        # Fast / Chat Model
        row2 = QVBoxLayout()
        row2.setSpacing(4)
        lbl2 = QLabel("Fast Conversational Model (JASPER_FAST_MODEL)")
        lbl2.setStyleSheet("color: #d0d0d0; font-size: 9.5pt; font-weight: 500;")
        hint2 = QLabel("Used for simple chat queries, fast classifications, and direct answers.")
        hint2.setStyleSheet("color: #777777; font-size: 8.5pt;")
        self.combo_fast_model = QComboBox()
        self.combo_fast_model.setEditable(True)
        self.combo_fast_model.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 6px 10px;"
        )
        row2.addWidget(lbl2)
        row2.addWidget(hint2)
        row2.addWidget(self.combo_fast_model)
        layout.addLayout(row2)

        # Vision Model
        row3 = QVBoxLayout()
        row3.setSpacing(4)
        lbl3 = QLabel("Vision / Multimodal Model (JASPER_VISION_MODEL)")
        lbl3.setStyleSheet("color: #d0d0d0; font-size: 9.5pt; font-weight: 500;")
        hint3 = QLabel("Used for image analysis, OCR, visual layout inspection, and attached photos.")
        hint3.setStyleSheet("color: #777777; font-size: 8.5pt;")
        self.combo_vision_model = QComboBox()
        self.combo_vision_model.setEditable(True)
        self.combo_vision_model.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 6px 10px;"
        )
        row3.addWidget(lbl3)
        row3.addWidget(hint3)
        row3.addWidget(self.combo_vision_model)
        layout.addLayout(row3)

        # Thinking Tags Option
        self.check_think = QCheckBox("Enable CoT Reasoning Tags (<think>)")
        self.check_think.setStyleSheet("color: #d0d0d0; font-size: 9.5pt;")
        self.check_think.setToolTip("When enabled, models supporting internal chain-of-thought generate thinking tokens.")
        layout.addWidget(self.check_think)

        return card

    def _build_autonomy_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("class", "settingsCard")
        card.setStyleSheet("background: #1e1e1e; border: 1px solid #303030; border-radius: 8px; padding: 14px;")
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        sec_title = QLabel("Autonomous Agent Execution & Safety")
        sec_title.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 10.5pt;")
        layout.addWidget(sec_title)

        desc = QLabel("Configure autonomous ReAct loop ceilings and permission safeguards.")
        desc.setStyleSheet("color: #8c8c8c; font-size: 9pt;")
        layout.addWidget(desc)

        row_spins = QHBoxLayout()
        row_spins.setSpacing(20)

        # Max Turns
        spin1_layout = QVBoxLayout()
        spin1_layout.setSpacing(4)
        lbl1 = QLabel("Max Autonomous Turns:")
        lbl1.setStyleSheet("color: #d0d0d0; font-size: 9pt; font-weight: 500;")
        self.spin_max_turns = QSpinBox()
        self.spin_max_turns.setRange(1, 10)
        self.spin_max_turns.setValue(4)
        self.spin_max_turns.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 4px 8px;"
        )
        spin1_layout.addWidget(lbl1)
        spin1_layout.addWidget(self.spin_max_turns)
        row_spins.addLayout(spin1_layout)

        # Timeout Seconds
        spin2_layout = QVBoxLayout()
        spin2_layout.setSpacing(4)
        lbl2 = QLabel("Autonomy Budget Timeout (s):")
        lbl2.setStyleSheet("color: #d0d0d0; font-size: 9pt; font-weight: 500;")
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 180)
        self.spin_timeout.setValue(45)
        self.spin_timeout.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 4px 8px;"
        )
        spin2_layout.addWidget(lbl2)
        spin2_layout.addWidget(self.spin_timeout)
        row_spins.addLayout(spin2_layout)

        layout.addLayout(row_spins)

        # Interactive Human Approval
        self.check_approval_gate = QCheckBox("Require Interactive Approval for File Modifications & Web Clicks")
        self.check_approval_gate.setChecked(True)
        self.check_approval_gate.setStyleSheet("color: #d0d0d0; font-size: 9.5pt;")
        self.check_approval_gate.setToolTip("Gated actions require your explicit Allow/Deny confirmation dialog.")
        layout.addWidget(self.check_approval_gate)

        return card

    def _build_system_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("class", "settingsCard")
        card.setStyleSheet("background: #1e1e1e; border: 1px solid #303030; border-radius: 8px; padding: 14px;")
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        sec_title = QLabel("Memory & Logging")
        sec_title.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 10.5pt;")
        layout.addWidget(sec_title)

        self.check_memory = QCheckBox("Enable Persistent Conversation Memory (SQLite)")
        self.check_memory.setStyleSheet("color: #d0d0d0; font-size: 9.5pt;")
        layout.addWidget(self.check_memory)

        self.check_notifications = QCheckBox("Enable Desktop Notifications & Tray Banners")
        self.check_notifications.setStyleSheet("color: #d0d0d0; font-size: 9.5pt;")
        self.check_notifications.setToolTip("Show native Windows notification toasts and in-app banners when tasks finish.")
        layout.addWidget(self.check_notifications)

        log_row = QHBoxLayout()
        log_row.setSpacing(8)
        lbl_log = QLabel("Log Level:")
        lbl_log.setStyleSheet("color: #d0d0d0; font-size: 9.5pt; font-weight: 500;")
        log_row.addWidget(lbl_log)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["INFO", "DEBUG", "WARNING", "ERROR"])
        self.combo_log_level.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 4px 10px;"
        )
        log_row.addWidget(self.combo_log_level)
        log_row.addStretch(1)
        layout.addLayout(log_row)

        return card

    def _build_browser_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("class", "settingsCard")
        card.setStyleSheet("background: #1e1e1e; border: 1px solid #303030; border-radius: 8px; padding: 14px;")
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        sec_title = QLabel("Browser & Web Automation")
        sec_title.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 10.5pt;")
        header_row.addWidget(sec_title)
        header_row.addStretch(1)

        self.label_browser_status = QLabel("● Ready")
        self.label_browser_status.setStyleSheet("color: #8ee6a1; font-size: 9pt;")
        header_row.addWidget(self.label_browser_status)
        layout.addLayout(header_row)

        desc = QLabel("JASPER automates web tasks (email, online services) using a persistent profile where your logins stay saved.")
        desc.setStyleSheet("color: #8c8c8c; font-size: 9pt;")
        layout.addWidget(desc)

        # Row 1: Browser Engine Selection
        browser_row = QHBoxLayout()
        lbl_engine = QLabel("Default Browser Engine:")
        lbl_engine.setStyleSheet("color: #e0e0e0; font-size: 9.5pt;")
        lbl_engine.setFixedWidth(180)
        browser_row.addWidget(lbl_engine)

        self.combo_browser_channel = QComboBox()
        self.combo_browser_channel.addItem("Google Chrome (Recommended)", "chrome")
        self.combo_browser_channel.addItem("Microsoft Edge", "msedge")
        self.combo_browser_channel.addItem("Bundled Chromium", "chromium")
        self.combo_browser_channel.setStyleSheet(
            "background: #252525; border: 1px solid #3a3a3a; border-radius: 5px; color: #ffffff; padding: 4px 10px;"
        )
        browser_row.addWidget(self.combo_browser_channel, 1)
        layout.addLayout(browser_row)

        # Row 2: Headless Mode Checkbox
        self.check_browser_headless = QCheckBox("Run browser in background (Headless)")
        self.check_browser_headless.setToolTip("When unchecked, browser opens visibly on desktop so you can watch actions.")
        self.check_browser_headless.setStyleSheet("color: #e0e0e0; font-size: 9.5pt;")
        layout.addWidget(self.check_browser_headless)

        # Row 3: Profile Folder Path & Open Button
        profile_row = QHBoxLayout()
        lbl_profile = QLabel("Profile Storage:")
        lbl_profile.setStyleSheet("color: #e0e0e0; font-size: 9.5pt;")
        lbl_profile.setFixedWidth(180)
        profile_row.addWidget(lbl_profile)

        from app.tools.browser import get_default_profile_dir
        self.input_browser_profile = QLineEdit(str(get_default_profile_dir()))
        self.input_browser_profile.setReadOnly(True)
        self.input_browser_profile.setStyleSheet(
            "background: #181818; border: 1px solid #333333; border-radius: 5px; color: #a0a0a0; padding: 4px 8px;"
        )
        profile_row.addWidget(self.input_browser_profile, 1)

        self.btn_open_profile = QPushButton("Open Folder")
        self.btn_open_profile.setStyleSheet(
            "background: #282828; border: 1px solid #404040; border-radius: 5px; color: #ffffff; padding: 5px 12px; font-size: 8.5pt;"
        )
        self.btn_open_profile.clicked.connect(self._open_profile_folder)
        profile_row.addWidget(self.btn_open_profile)
        layout.addLayout(profile_row)

        # Row 4: Launch browser to pre-authenticate / sign in
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_launch_browser = QPushButton("🌐 Launch Browser (Log into Accounts)")
        self.btn_launch_browser.setToolTip("Opens your selected browser visibly with the persistent profile so you can log into Gmail, Outlook, etc.")
        self.btn_launch_browser.setStyleSheet(
            "background: #1c3644; border: 1px solid #00bcd4; border-radius: 5px; color: #ffffff; padding: 6px 14px; font-weight: 500; font-size: 9pt;"
        )
        self.btn_launch_browser.clicked.connect(self._launch_browser_session)
        btn_row.addWidget(self.btn_launch_browser)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        hint = QLabel("💡 Tip: Sign into your accounts once in this browser. Future JASPER web tasks will use the saved login session.")
        hint.setStyleSheet("color: #00bcd4; font-size: 8.5pt; font-style: italic;")
        layout.addWidget(hint)

        return card

    @Slot()
    def _open_profile_folder(self) -> None:
        import os
        from app.tools.browser import get_default_profile_dir
        folder = get_default_profile_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))
        except Exception as e:
            _LOG.warning("Could not open profile folder: %s", e)

    @Slot()
    def _launch_browser_session(self) -> None:
        """Launch browser visibly in a background thread so user can log into web accounts."""
        import threading

        def _runner():
            try:
                from app.tools.browser import BrowserConfig, BrowserController
                channel = self.combo_browser_channel.currentData() or "chrome"
                ctrl = BrowserController(
                    config=BrowserConfig(
                        channel=channel,
                        headless=False,
                    )
                )
                ctrl.navigate("https://www.google.com")
            except Exception as e:
                _LOG.warning("Could not launch browser for login: %s", e)

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        self.label_feedback.setText("✓ Launching browser... Log into your services, then close the window.")
        self.label_feedback.setStyleSheet("color: #00bcd4; font-weight: 600; font-size: 9.5pt;")
        self._feedback_timer.start(5000)

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet("background: #151515; border-top: 1px solid #2a2a2a; padding: 10px 14px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.label_feedback = QLabel("")
        self.label_feedback.setStyleSheet("color: #8ee6a1; font-weight: 600; font-size: 9.5pt;")
        layout.addWidget(self.label_feedback)
        layout.addStretch(1)

        self.btn_restart = QPushButton("🔄 Reload App (Ctrl+R)")
        self.btn_restart.setToolTip("Restart JASPER immediately to reload any updated source code")
        self.btn_restart.setStyleSheet(
            "background: #232d25; border: 1px solid #366141; border-radius: 6px; color: #8ee6a1; padding: 8px 14px; font-weight: 500;"
        )
        self.btn_restart.clicked.connect(self.restart_requested.emit)
        layout.addWidget(self.btn_restart)

        self.btn_reset = QPushButton("Reset Defaults")
        self.btn_reset.setStyleSheet(
            "background: #262626; border: 1px solid #3e3e3e; border-radius: 6px; color: #cccccc; padding: 8px 16px; font-weight: 500;"
        )
        self.btn_reset.clicked.connect(self.reset_defaults)
        layout.addWidget(self.btn_reset)

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setStyleSheet(
            "background: #235832; border: 1px solid #36854c; border-radius: 6px; color: #ffffff; padding: 8px 18px; font-weight: 600;"
        )
        self.btn_save.clicked.connect(self.save_settings)
        layout.addWidget(self.btn_save)

        return bar

    def load_from_config(self) -> None:
        """Populate form controls from currently loaded application config."""
        self.input_host.setText(cfg.OLLAMA_HOST)
        self._set_combo_value(self.combo_primary_model, cfg.JASPER_MODEL)
        self._set_combo_value(self.combo_fast_model, cfg.JASPER_FAST_MODEL)
        self._set_combo_value(self.combo_vision_model, cfg.JASPER_VISION_MODEL)
        self.check_think.setChecked(bool(cfg.JASPER_THINK))
        self.check_memory.setChecked(bool(cfg.JASPER_MEMORY_ENABLED))
        self.check_notifications.setChecked(bool(getattr(cfg, "JASPER_NOTIFICATIONS_ENABLED", True)))

        current_log = getattr(cfg, "LOG_LEVEL", "INFO")
        idx = self.combo_log_level.findText(current_log, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.combo_log_level.setCurrentIndex(idx)

        # Browser automation settings
        current_channel = getattr(cfg, "JASPER_BROWSER_CHANNEL", "chrome").lower()
        b_idx = self.combo_browser_channel.findData(current_channel)
        if b_idx >= 0:
            self.combo_browser_channel.setCurrentIndex(b_idx)
        else:
            self.combo_browser_channel.setCurrentIndex(0)
        self.check_browser_headless.setChecked(bool(getattr(cfg, "JASPER_BROWSER_HEADLESS", False)))

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        idx = combo.findText(value, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.insertItem(0, value)
            combo.setCurrentIndex(0)

    @Slot()
    def fetch_ollama_models(self) -> list[str]:
        """Query Ollama API to detect installed local models and refresh dropdowns."""
        import threading
        host = self.input_host.text().strip().rstrip("/")
        if not host:
            host = cfg.OLLAMA_HOST
        url = f"{host}/api/tags"

        # In automated test suites, run synchronously for deterministic assertions
        if os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "JASPER/Settings"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = sorted([m["name"] for m in data.get("models", []) if "name" in m])
                    self._apply_fetched_models(models, host)
                    return self._detected_models
            except Exception as exc:
                self._apply_fetched_models([], host, error=str(exc))
                return []

        # In interactive desktop GUI, query asynchronously so tab switching never stutters
        def _bg() -> None:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "JASPER/Settings"})
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = sorted([m["name"] for m in data.get("models", []) if "name" in m])
                    QTimer.singleShot(0, lambda: self._apply_fetched_models(models, host))
            except Exception as exc:
                _LOG.debug("Failed to connect to Ollama at %s: %s", url, exc)
                QTimer.singleShot(0, lambda: self._apply_fetched_models([], host, error=str(exc)))

        threading.Thread(target=_bg, daemon=True).start()
        return self._detected_models

    def _apply_fetched_models(self, models: list[str], host: str, error: str | None = None) -> None:
        if models:
            self._detected_models = models
            self.label_connection_status.setText(f"● Connected ({len(models)} models available)")
            self.label_connection_status.setStyleSheet("color: #8ee6a1; font-weight: 600; font-size: 9pt;")
            self._update_model_dropdowns(self._detected_models)
        elif error:
            self.label_connection_status.setText(f"○ Offline (could not reach {host})")
            self.label_connection_status.setStyleSheet("color: #e06c75; font-size: 9pt;")

    def _update_model_dropdowns(self, models: list[str]) -> None:
        """Update combobox options while preserving the currently active model."""
        for combo in (self.combo_primary_model, self.combo_fast_model, self.combo_vision_model):
            current = combo.currentText()
            combo.clear()
            for m in models:
                combo.addItem(m)
            self._set_combo_value(combo, current)

    @Slot()
    def reset_defaults(self) -> None:
        """Reset inputs to default configuration values."""
        self.input_host.setText("http://127.0.0.1:11434")
        self._set_combo_value(self.combo_primary_model, "qwen3:14b")
        self._set_combo_value(self.combo_fast_model, "qwen3:8b")
        self._set_combo_value(self.combo_vision_model, "qwen3-vl:8b")
        self.check_think.setChecked(False)
        self.spin_max_turns.setValue(4)
        self.spin_timeout.setValue(45)
        self.check_approval_gate.setChecked(True)
        self.check_memory.setChecked(True)
        self.check_notifications.setChecked(True)
        self.combo_log_level.setCurrentText("INFO")

        b_idx = self.combo_browser_channel.findData("chrome")
        if b_idx >= 0:
            self.combo_browser_channel.setCurrentIndex(b_idx)
        self.check_browser_headless.setChecked(False)

        self.label_feedback.setText("Reset to defaults (click Save Changes to apply)")
        self.label_feedback.setStyleSheet("color: #bdbdbd; font-size: 9pt;")
        self._feedback_timer.start(4000)

    @Slot()
    def save_settings(self) -> dict[str, Any]:
        """Save form settings to memory and persist to the workspace .env file."""
        settings = {
            "OLLAMA_HOST": self.input_host.text().strip().rstrip("/") or "http://127.0.0.1:11434",
            "JASPER_MODEL": self.combo_primary_model.currentText().strip() or "qwen3:14b",
            "JASPER_FAST_MODEL": self.combo_fast_model.currentText().strip() or "qwen3:8b",
            "JASPER_VISION_MODEL": self.combo_vision_model.currentText().strip() or "qwen3-vl:8b",
            "JASPER_THINK": self.check_think.isChecked(),
            "MAX_TURNS": self.spin_max_turns.value(),
            "TIMEOUT_SECONDS": self.spin_timeout.value(),
            "APPROVAL_GATE_STRICT": self.check_approval_gate.isChecked(),
            "JASPER_MEMORY_ENABLED": self.check_memory.isChecked(),
            "JASPER_NOTIFICATIONS_ENABLED": self.check_notifications.isChecked(),
            "LOG_LEVEL": self.combo_log_level.currentText(),
            "JASPER_BROWSER_CHANNEL": self.combo_browser_channel.currentData() or "chrome",
            "JASPER_BROWSER_HEADLESS": self.check_browser_headless.isChecked(),
        }

        # Update in-memory config variables
        cfg.OLLAMA_HOST = settings["OLLAMA_HOST"]
        cfg.JASPER_MODEL = settings["JASPER_MODEL"]
        cfg.JASPER_FAST_MODEL = settings["JASPER_FAST_MODEL"]
        cfg.JASPER_VISION_MODEL = settings["JASPER_VISION_MODEL"]
        cfg.JASPER_THINK = settings["JASPER_THINK"]
        cfg.JASPER_MEMORY_ENABLED = settings["JASPER_MEMORY_ENABLED"]
        cfg.JASPER_NOTIFICATIONS_ENABLED = settings["JASPER_NOTIFICATIONS_ENABLED"]
        cfg.LOG_LEVEL = settings["LOG_LEVEL"]
        cfg.JASPER_BROWSER_CHANNEL = settings["JASPER_BROWSER_CHANNEL"]
        cfg.JASPER_BROWSER_HEADLESS = settings["JASPER_BROWSER_HEADLESS"]

        # Sync browser controller with updated settings
        try:
            from app.tools.browser import BrowserConfig, get_browser_controller
            get_browser_controller(
                config=BrowserConfig(
                    channel=cfg.JASPER_BROWSER_CHANNEL,
                    headless=cfg.JASPER_BROWSER_HEADLESS,
                )
            )
        except Exception as e:
            _LOG.warning("Could not sync browser controller with new settings: %s", e)

        # Persist to .env file in project root
        self._persist_to_dotenv(settings)

        # Notify application
        self.settings_saved.emit(settings)

        self.label_feedback.setText("✓ Settings saved and active!")
        self.label_feedback.setStyleSheet("color: #8ee6a1; font-weight: 600; font-size: 9.5pt;")
        self._feedback_timer.start(3500)
        return settings

    def _persist_to_dotenv(self, settings: dict[str, Any]) -> None:
        """Update or insert key-value pairs in the .env file cleanly."""
        env_path = cfg.ROOT / ".env"
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        keys_to_write = {
            "OLLAMA_HOST": settings["OLLAMA_HOST"],
            "JASPER_MODEL": settings["JASPER_MODEL"],
            "JASPER_FAST_MODEL": settings["JASPER_FAST_MODEL"],
            "JASPER_VISION_MODEL": settings["JASPER_VISION_MODEL"],
            "JASPER_THINK": str(settings["JASPER_THINK"]).lower(),
            "JASPER_MEMORY_ENABLED": str(settings["JASPER_MEMORY_ENABLED"]).lower(),
            "JASPER_NOTIFICATIONS_ENABLED": str(settings.get("JASPER_NOTIFICATIONS_ENABLED", True)).lower(),
            "LOG_LEVEL": settings["LOG_LEVEL"],
            "JASPER_BROWSER_CHANNEL": settings.get("JASPER_BROWSER_CHANNEL", "chrome"),
            "JASPER_BROWSER_HEADLESS": str(settings.get("JASPER_BROWSER_HEADLESS", False)).lower(),
        }

        updated_keys: set[str] = set()
        new_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                key = k.strip()
                if key in keys_to_write:
                    new_lines.append(f"{key}={keys_to_write[key]}")
                    updated_keys.add(key)
                    continue
            new_lines.append(line)

        # Append any new keys not already present
        for key, val in keys_to_write.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        _LOG.info("Persisted updated settings to %s", env_path)

    def _clear_feedback(self) -> None:
        self.label_feedback.setText("")
