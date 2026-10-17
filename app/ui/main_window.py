from __future__ import annotations

import logging
from html import escape

from PySide6.QtCore import QMimeData, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.approval import ApprovalRequest
from app.core.config import JASPER_VOICE_ENABLED
from app.ui.approval_dialog import ApprovalDialog
from app.ui.markdown_renderer import markdown_to_html
from app.ui.plugins_workspace import PluginsWorkspace
from app.ui.scheduled_workspace import ScheduledWorkspace
from app.ui.settings_workspace import SettingsWorkspace
from app.ui.styles import APP_STYLE
from app.ui.tasks_workspace import TasksWorkspace
from app.ui.toast_banner import ToastBanner
from app.ui.vision_workspace import OPEN_IMAGE_FILTER, VisionWorkspace
from app.ui.worker import JasperWorker
from app.vision.image import SUPPORTED_IMAGE_EXTENSIONS

_LOG = logging.getLogger("jasper.ui.main_window")


class MainWindow(QMainWindow):
    request_text = Signal(str)
    request_text_with_image = Signal(str, str)   # text, image_path
    request_voice = Signal()
    request_vision = Signal(str, str)
    request_refresh_status = Signal()

    NAV_ITEMS = (
        ("💬  Chat", "Chat"),
        ("⚡  Tasks", "Tasks"),
        ("🕒  Scheduled", "Scheduled"),
        ("🧩  Plugins", "Plugins"),
        ("📁  Files", "Files"),
        ("🔀  Git", "Git"),
        ("⚙  Settings", "Settings"),
    )

    def __init__(self, worker: JasperWorker, thread: QThread) -> None:
        super().__init__()
        self.worker = worker
        self.thread = thread
        self.busy = False
        self._shutdown_clean = True
        self._tray: QSystemTrayIcon | None = None
        self.nav_buttons: list[QPushButton] = []
        self._thinking_step = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(450)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._messages: list[tuple[str, str]] = []
        self._streaming_content = ""
        self._streaming_active = False
        self._attached_image_path: str | None = None
        self._chat_drag_active = False
        self._active_approval_dialog: ApprovalDialog | None = None
        self._active_gate_id: str | None = None
        self._snipper = None
        self._pending_snip_prompt: str | None = None
        self._is_watching_screen = False
        self._latest_watch_path: str | None = None
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(4000)
        self._watch_timer.timeout.connect(self._grab_watch_frame)
        self._ask_for_approval = True
        self._selected_model = "qwen3:8b"

        # Periodic status refresh (every 30 seconds)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(30000)
        self._status_timer.timeout.connect(self.request_refresh_status.emit)
        self._status_timer.start()

        self.setWindowTitle("JASPER")
        self._setup_icon()
        self.resize(1120, 720)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(APP_STYLE)
        self._build_ui()
        self._connect_worker()
        self._setup_tray()
        self.request_refresh_status.emit()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_bar = QFrame(objectName="topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 12, 18, 12)
        top_layout.setSpacing(10)

        brand_layout = QHBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)

        if getattr(self, "_app_icon", None) and not self._app_icon.isNull():
            brand_icon = QLabel()
            brand_icon.setPixmap(self._app_icon.pixmap(24, 24))
            brand_icon.setFixedSize(24, 24)
            brand_layout.addWidget(brand_icon)

        brand = QLabel("JASPER")
        brand.setObjectName("brand")
        brand_layout.addWidget(brand)
        top_layout.addLayout(brand_layout)
        top_layout.addStretch(1)
        self.active_status = QLabel("● STANDBY")
        self.active_status.setObjectName("activeStatus")
        top_layout.addWidget(self.active_status)
        root_layout.addWidget(top_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root_layout.addLayout(body, 1)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(4)
        sidebar_title = QLabel("WORKSPACES")
        sidebar_title.setObjectName("sidebarTitle")
        sidebar_layout.addWidget(sidebar_title)
        self.page_stack = QStackedWidget()
        for index, (label, _) in enumerate(self.NAV_ITEMS):
            button = QPushButton(label)
            button.setProperty("class", "navButton")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked, i=index: self._select_page(i))
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch(1)
        body.addWidget(sidebar)

        content = QFrame(objectName="contentFrame")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 24, 18)
        content_layout.setSpacing(10)
        self.toast_banner = ToastBanner(self)
        content_layout.addWidget(self.toast_banner)
        self._build_pages()
        content_layout.addWidget(self.page_stack, 1)
        body.addWidget(content, 1)
        root_layout.addWidget(self._build_status_bar())
        self._select_page(0)

    def _build_pages(self) -> None:
        self.chat_page = QWidget()
        chat_layout = QVBoxLayout(self.chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Conversation / Task")
        title.setObjectName("workspaceTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.workspace_hint = QLabel("Ready")
        self.workspace_hint.setObjectName("workspaceHint")
        header.addWidget(self.workspace_hint)
        chat_layout.addLayout(header)

        self.system_readiness_label = QLabel()
        self.system_readiness_label.setObjectName("systemReadiness")
        self.system_readiness_label.setWordWrap(True)
        self.system_readiness_label.setStyleSheet("background: #242424; padding: 10px; border-radius: 4px; color: #bdbdbd; margin-bottom: 8px;")
        self.system_readiness_label.hide()
        chat_layout.addWidget(self.system_readiness_label)

        self.conversation = QTextBrowser()
        self.conversation.setObjectName("conversation")
        self.conversation.setOpenExternalLinks(True)
        self.conversation.setReadOnly(True)
        self.conversation.document().setDefaultStyleSheet("body{margin:0;padding:0;} h1{font-size:20pt;margin:12px 0 8px 0;} h2{font-size:16pt;margin:12px 0 7px 0;} h3{font-size:13pt;margin:10px 0 6px 0;} h4,h5,h6{font-size:11pt;margin:9px 0 5px 0;} p{margin:5px 0;line-height:1.35;} ul,ol{margin-top:5px;margin-bottom:7px;} li{margin:2px 0;} table{border-collapse:collapse;margin:8px 0;} th,td{border:1px solid #454545;padding:6px 9px;} th{background:#242424;font-weight:600;} blockquote{border-left:3px solid #555;padding-left:11px;color:#bdbdbd;margin:8px 0;} code{background:#242424;padding:2px 4px;} pre{background:#101010;border:1px solid #282828;padding:10px;margin:8px 0;} hr{border:0;border-top:1px solid #2b2b2b;margin:12px 0;} a{color:#8ee6a1;}")
        chat_layout.addWidget(self.conversation, 1)

        self.thinking_indicator = QLabel("JASPER is working…")
        self.thinking_indicator.setObjectName("thinkingIndicator")
        self.thinking_indicator.hide()
        chat_layout.addWidget(self.thinking_indicator)

        composer = QFrame(objectName="composer")
        composer.setAcceptDrops(True)
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(8, 6, 8, 6)
        composer_layout.setSpacing(6)

        # --- Attach button (📎) ---
        self.attach_button = QPushButton("📎")
        self.attach_button.setObjectName("micButton")
        self.attach_button.setToolTip("Attach an image (PNG, JPG, WebP)")
        self.attach_button.clicked.connect(self._open_attachment)
        composer_layout.addWidget(self.attach_button)

        # --- Screen button (📸) ---
        self.screen_button = QPushButton("📸")
        self.screen_button.setObjectName("micButton")
        self.screen_button.setToolTip("Snip screen region or double-click to capture monitor")
        self.screen_button.clicked.connect(self._on_screen_button_clicked)
        composer_layout.addWidget(self.screen_button)

        # --- Watch screen button (👁) ---
        self.watch_button = QPushButton("👁")
        self.watch_button.setObjectName("micButton")
        self.watch_button.setToolTip("Watch Screen mode (continuous screen awareness until stopped)")
        self.watch_button.clicked.connect(self._toggle_watch_screen)
        composer_layout.addWidget(self.watch_button)

        # --- Image chip (hidden by default) ---
        self.attachment_chip = QFrame(objectName="attachmentChip")
        self.attachment_chip.setContentsMargins(0, 0, 0, 0)
        chip_layout = QHBoxLayout(self.attachment_chip)
        chip_layout.setContentsMargins(6, 2, 4, 2)
        chip_layout.setSpacing(4)
        self.attachment_label = QLabel()
        self.attachment_label.setObjectName("attachmentLabel")
        chip_layout.addWidget(self.attachment_label)
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setObjectName("attachmentDismiss")
        dismiss_btn.setFixedSize(18, 18)
        dismiss_btn.clicked.connect(self._clear_attachment)
        chip_layout.addWidget(dismiss_btn)
        self.attachment_chip.hide()
        composer_layout.addWidget(self.attachment_chip)

        # --- Text input ---
        self.input = QLineEdit()
        self.input.setObjectName("input")
        self.input.setPlaceholderText("Ask JASPER...")
        self.input.returnPressed.connect(self._send_text)
        self.input.setAcceptDrops(False)
        composer_layout.addWidget(self.input, 1)

        self.mic_button = QPushButton("🎤")
        self.mic_button.setObjectName("micButton")
        self.mic_button.setToolTip("Speak to JASPER")
        self.mic_button.setEnabled(JASPER_VOICE_ENABLED)
        self.mic_button.clicked.connect(self._listen)
        composer_layout.addWidget(self.mic_button)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._on_send_clicked)
        composer_layout.addWidget(self.send_button)

        chat_layout.addWidget(composer)
        self.chat_page.setAcceptDrops(True)

        # Stack Pages (Total 7 pages)
        self.page_stack.addWidget(self.chat_page)  # 0: Chat

        self.tasks_page = TasksWorkspace()
        self.tasks_page.task_started.connect(self._on_task_started)
        self.page_stack.addWidget(self.tasks_page)  # 1: Tasks

        self.scheduled_page = ScheduledWorkspace()
        self.scheduled_page.task_triggered.connect(self._on_scheduled_task_triggered)
        self.page_stack.addWidget(self.scheduled_page)  # 2: Scheduled

        self.plugins_page = PluginsWorkspace()
        self.plugins_page.use_item_requested.connect(self._on_plugin_use_requested)
        self.plugins_page.plugin_toggled.connect(self._on_plugin_toggled)
        self.page_stack.addWidget(self.plugins_page)  # 3: Plugins

        self.page_stack.addWidget(self._placeholder_page("Files"))  # 4: Files
        self.page_stack.addWidget(self._placeholder_page("Git"))  # 5: Git

        self.settings_page = SettingsWorkspace()
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.page_stack.addWidget(self.settings_page)  # 6: Settings

        # VisionWorkspace preserved as attribute for direct tests and tools
        self.vision_page = VisionWorkspace()

    def _placeholder_page(self, name: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(name)
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(self._page_description(name))
        body.setObjectName("pageBody")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(body)
        return page

    @staticmethod
    def _page_description(name: str) -> str:
        descriptions = {
            "Tasks": "Complex work, progress, and future automation will live here.",
            "Pull Requests": "Git branch, diff status, and pull request review will live here.",
            "Files": "Safe file browsing and document workflows will be surfaced here.",
            "Settings": "Application, model, voice, permissions, and resource settings will live here.",
        }
        return descriptions.get(name, "Workspace details will live here.")

    def _build_status_bar(self) -> QFrame:
        frame = QFrame(objectName="statusBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(14)
        self.status_state = QLabel("STANDBY")
        self.status_state.setProperty("class", "statusChip")
        layout.addWidget(self.status_state)
        self.ollama_status = QLabel("Ollama ○")
        self.ollama_status.setProperty("class", "statusChip")
        layout.addWidget(self.ollama_status)
        self.voice_status = QLabel("Voice ○")
        self.voice_status.setProperty("class", "statusChip")
        layout.addWidget(self.voice_status)
        self.gpu_status = QLabel("GPU ○")
        self.gpu_status.setProperty("class", "statusChip")
        layout.addWidget(self.gpu_status)
        self.watch_status = QLabel("")
        self.watch_status.setObjectName("watchStatus")
        self.watch_status.setProperty("class", "statusChip")
        self.watch_status.hide()
        layout.addWidget(self.watch_status)
        layout.addStretch(1)
        return frame

    def _connect_worker(self) -> None:
        self.request_text.connect(self.worker.send_text)
        self.request_text_with_image.connect(self.worker.send_text_with_image)
        self.request_voice.connect(self.worker.listen_once)
        self.request_vision.connect(self.worker.analyze_vision)
        self.request_refresh_status.connect(self.worker.refresh_system_status)
        self.vision_page.analyze_requested.connect(self._analyze_vision)
        self.worker.response_stream.connect(self._on_stream_chunk)
        self.worker.response_ready.connect(self._on_response)
        self.worker.vision_ready.connect(self.vision_page.show_result)
        self.worker.status_changed.connect(self._set_status)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.system_status_ready.connect(self._on_system_status)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_finished)
        if hasattr(self.worker, "approval_requested"):
            self.worker.approval_requested.connect(self._on_approval_requested)

    def _setup_icon(self) -> None:
        import sys
        from pathlib import Path
        from PySide6.QtGui import QIcon

        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
        icon_path = Path("assets/jasper_icon.png")
        if not icon_path.exists():
            icon_path = base_dir / "assets" / "jasper_icon.png"

        if icon_path.exists():
            self._app_icon = QIcon(str(icon_path))
            self.setWindowIcon(self._app_icon)
        else:
            self._app_icon = None

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        if getattr(self, "_app_icon", None) and not self._app_icon.isNull():
            self._tray.setIcon(self._app_icon)
        self._tray.setToolTip("JASPER")
        self._tray.setContextMenu(self._build_tray_menu())
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _build_tray_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        open_action = QAction("Open JASPER", self)
        open_action.triggered.connect(self.showNormal)
        menu.addAction(open_action)
        menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)
        return menu

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()

    @Slot(str)
    def _on_task_started(self, goal: str) -> None:
        self._select_page(0)
        self.input.setText(goal)
        self._send_text()

    @Slot(str, str)
    def _on_scheduled_task_triggered(self, title: str, prompt: str) -> None:
        self._select_page(0)
        self.input.setText(prompt)
        self._send_text()

    @Slot(str, str)
    def _on_plugin_use_requested(self, item_name: str, prompt: str) -> None:
        self._select_page(0)
        self.input.setText(prompt)
        self._send_text()

    @Slot(str, bool)
    def _on_plugin_toggled(self, plugin_id: str, enabled: bool) -> None:
        _LOG.info("Plugin %s toggled: %s", plugin_id, enabled)

    def _select_page(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        hints = {
            0: "Ready",
            1: "Autonomous Tasks & Execution",
            2: "Scheduled Tasks & Monitors",
            3: "Plugins & Skills Ecosystem",
            4: "File workspace",
            5: "Git & Pull Requests",
            6: "Settings & Models",
        }
        self.workspace_hint.setText(hints.get(index, "Workspace"))
        if index == 6 and hasattr(self, "settings_page"):
            self.settings_page.fetch_ollama_models()

    @Slot(dict)
    def _on_settings_saved(self, settings: dict) -> None:
        """Handle settings updates from the Settings workspace."""
        model_name = settings.get("JASPER_MODEL", "")
        self.workspace_hint.setText(f"Active model: {model_name}")

    @Slot()
    def _on_screen_button_clicked(self) -> None:
        """Handle click on composer 📸 button."""
        prompt = self.input.text().strip()
        self.input.clear()
        self._capture_screen_and_ask(custom_prompt=prompt)

    def _capture_screen_and_ask(self, custom_prompt: str | None = None) -> None:
        """Launch interactive screen snipping overlay across all monitors."""
        if self.busy:
            return

        self._pending_snip_prompt = custom_prompt if custom_prompt else "What is on my screen and what is this doing?"
        self.hide()

        def do_snip() -> None:
            try:
                from app.ui.screen_snipper import ScreenSnipper
                if self._snipper is None:
                    self._snipper = ScreenSnipper()
                    self._snipper.snipped.connect(self._on_chat_snipped)
                    self._snipper.cancelled.connect(self._on_chat_snip_cancelled)
                self._snipper.start_snip()
            except Exception as exc:
                _LOG.exception("Screen snipper launch failed: %s", exc)
                self.show()
                self.activateWindow()
                self._on_error(f"Failed to launch screen snipper: {exc}")

        QTimer.singleShot(150, do_snip)

    @Slot(str)
    def _on_chat_snipped(self, file_path: str) -> None:
        self.show()
        self.activateWindow()
        self._set_attachment(file_path)
        prompt = getattr(self, "_pending_snip_prompt", None) or "What is on my screen and what is this doing?"
        self._pending_snip_prompt = None
        self.input.setText(prompt)
        self._send_text()

    @Slot()
    def _on_chat_snip_cancelled(self) -> None:
        self.show()
        self.activateWindow()
        self._pending_snip_prompt = None

    @Slot()
    def _toggle_watch_screen(self) -> None:
        """Toggle continuous screen watch mode."""
        if not self._is_watching_screen:
            self._start_watch_screen()
        else:
            self._stop_watch_screen()

    def _start_watch_screen(self, proactive: bool = True) -> None:
        self._is_watching_screen = True
        self.watch_button.setText("⏹")
        self.watch_button.setProperty("watching", "true")
        self.watch_button.style().unpolish(self.watch_button)
        self.watch_button.style().polish(self.watch_button)
        self.watch_button.setToolTip("Stop Watching Screen (currently watching desktop)")
        self.watch_status.setText("● WATCHING SCREEN")
        self.watch_status.show()
        self._grab_watch_frame()
        self._watch_timer.start()

        # Proactive: immediately trigger a live situational analysis
        if proactive and not self.busy and self._latest_watch_path:
            self.input.setText("What is on my screen and what is currently happening?")
            self._send_text()

    def _stop_watch_screen(self) -> None:
        self._is_watching_screen = False
        self._watch_timer.stop()
        self.watch_button.setText("👁")
        self.watch_button.setProperty("watching", "false")
        self.watch_button.style().unpolish(self.watch_button)
        self.watch_button.style().polish(self.watch_button)
        self.watch_button.setToolTip("Watch Screen mode (continuous screen awareness until stopped)")
        self.watch_status.setText("")
        self.watch_status.hide()
        self._latest_watch_path = None

    def _grab_watch_frame(self) -> None:
        """Periodically grab virtual desktop across all monitors for watch mode."""
        if self.busy:
            return
        try:
            from app.vision.capture import capture_virtual_desktop
            path = capture_virtual_desktop()
            self._latest_watch_path = str(path)
        except Exception as exc:
            _LOG.debug("Background watch screen capture failed: %s", exc)

    @Slot()
    def _on_send_clicked(self) -> None:
        if self.busy:
            self.worker.cancel_request()
            self.send_button.setEnabled(False)
        else:
            self._send_text()

    def _send_text(self) -> None:
        text = self.input.text().strip()
        if not text:
            return

        # Quick command: /watch
        if text.lower() in ("/watch", "/watchscreen", "watch screen"):
            self.input.clear()
            self._start_watch_screen(proactive=True)
            return

        # Quick command: /unwatch or /stopwatch
        if text.lower() in ("/unwatch", "/stopwatch", "stop watching"):
            self.input.clear()
            self._stop_watch_screen()
            self._append_message("JASPER", "Screen watching stopped.")
            return

        if self.busy:
            return

        # Quick command: /screen or /snip [optional query]
        if text.startswith("/screen") or text.startswith("/snip"):
            prefix_len = 7 if text.startswith("/screen") else 5
            query = text[prefix_len:].strip()
            self.input.clear()
            self._capture_screen_and_ask(custom_prompt=query)
            return

        image_path = self._attached_image_path
        live_watch = False
        if not image_path and self._is_watching_screen:
            self._grab_watch_frame()
            image_path = self._latest_watch_path
            live_watch = True

        display_text = text
        if image_path:
            from pathlib import Path as _Path
            if live_watch:
                display_text = f"{text}\n\n👁 live screen ({_Path(image_path).name})"
            else:
                display_text = f"{text}\n\n📎 {_Path(image_path).name}"
        self.worker.begin_request()
        self._append_message("You", display_text)
        self.input.clear()
        self._clear_attachment()
        self._streaming_active = True
        self._streaming_content = ""
        self._show_thinking("JASPER is working")
        self._set_busy(True)
        if image_path:
            self.request_text_with_image.emit(text, image_path)
        else:
            self.request_text.emit(text)

    def _listen(self) -> None:
        if self.busy or not JASPER_VOICE_ENABLED:
            return
        self._streaming_active = False
        self._streaming_content = ""
        self.worker.begin_request()
        self._set_busy(True)
        self._show_thinking("Listening")
        self.request_voice.emit()

    @Slot(str, str)
    def _analyze_vision(self, image_path: str, prompt: str) -> None:
        self._select_page(2)
        self.worker.begin_request()
        self.request_vision.emit(image_path, prompt)

    @Slot(str)
    def _on_stream_chunk(self, chunk: str) -> None:
        if not self._streaming_active:
            self._streaming_active = True
            self._streaming_content = ""
        self._streaming_content += chunk
        self._thinking_timer.stop()
        self.thinking_indicator.hide()
        if self._messages and self._messages[-1][0] == "JASPER":
            self._messages[-1] = ("JASPER", self._streaming_content)
        else:
            self._messages.append(("JASPER", self._streaming_content))
        self._render_conversation()

    @Slot(str, str)
    def _on_response(self, kind: str, content: str) -> None:
        if kind == "voice":
            self._streaming_active = False
            self._streaming_content = ""
            self._stop_thinking()
            spoken, _, answer = content.partition("\n\n")
            self._append_message("You (voice)", spoken)
            self._append_message("JASPER", answer)
        elif kind == "voice_empty":
            self._streaming_active = False
            self._streaming_content = ""
            self._stop_thinking()
            self._append_message("JASPER", content)
        elif self._streaming_active:
            self._streaming_content = content
            if self._messages and self._messages[-1][0] == "JASPER":
                self._messages[-1] = ("JASPER", content)
            else:
                self._messages.append(("JASPER", content))
            self._streaming_active = False
            self._stop_thinking()
            self._render_conversation()
        else:
            self._append_message("JASPER", content)

    @Slot(str)
    def _set_status(self, state: str) -> None:
        self.active_status.setText(f"● {state}")
        self.status_state.setText(state)
        if self.page_stack.currentIndex() == 0:
            self.workspace_hint.setText({"STANDBY": "Ready", "ACTIVE": "Working...", "LISTENING": "Listening...", "SPEAKING": "Speaking..."}.get(state, state.title()))
        if state == "ACTIVE" and not self._streaming_content:
            self._show_thinking("JASPER is working")
        elif state == "LISTENING":
            self._show_thinking("Listening")
        elif state == "SPEAKING":
            self._show_thinking("Speaking")

    @Slot()
    def _on_cancelled(self) -> None:
        """Render a truthful interrupted-request state without treating Stop as an error."""
        self._streaming_active = False
        self._stop_thinking()
        if self.page_stack.currentIndex() == 2 and self.vision_page._busy:
            self.vision_page.show_error("Vision analysis stopped.")
        elif self._messages and self._messages[-1][0] == "JASPER" and self._streaming_content:
            self._messages[-1] = ("JASPER", self._streaming_content + "\n\n*Request stopped.*")
            self._streaming_content = ""
            self._render_conversation()
        else:
            self._streaming_content = ""
            self._append_message("JASPER", "*Request stopped.*")
        if hasattr(self, "_active_approval_dialog") and self._active_approval_dialog is not None:
            try:
                self._active_approval_dialog.handle_cancelled()
            except Exception:
                pass
            self._active_approval_dialog = None
            self._active_gate_id = None
        self._set_busy(False)

    @Slot(ApprovalRequest)
    def _on_approval_requested(self, request: ApprovalRequest) -> None:
        """Present incoming approval request to user on the GUI thread."""
        if hasattr(self, "_active_approval_dialog") and self._active_approval_dialog is not None and not self._active_approval_dialog.is_resolved:
            _LOG.warning(
                "Rejecting concurrent approval request %s; dialog already active for %s",
                request.gate_id,
                self._active_gate_id,
            )
            self.worker.resolve_approval(request.gate_id, granted=False)
            return

        dialog = ApprovalDialog(request, parent=self)
        self._active_approval_dialog = dialog
        self._active_gate_id = request.gate_id

        tool_name = getattr(request.action, "tool_name", "action") if hasattr(request, "action") else getattr(request, "tool_name", "action")
        desc = getattr(request.action, "description", "") if hasattr(request, "action") else getattr(request, "description", "")
        summary = f"{tool_name}: {desc[:80]}" if desc else f"{tool_name} requires confirmation"

        self.notify_user(
            "JASPER Approval Required",
            summary,
            level="warning",
        )

        dialog.decision_made.connect(self._on_approval_decision)

        def _cleanup():
            if getattr(self, "_active_approval_dialog", None) is dialog:
                self._active_approval_dialog = None
                self._active_gate_id = None

        dialog.finished.connect(_cleanup)
        dialog.open()

    @Slot(str, bool)
    def _on_approval_decision(self, gate_id: str, granted: bool) -> None:
        """Forward user approval decision to worker."""
        if getattr(self, "_active_gate_id", None) == gate_id:
            self._active_approval_dialog = None
            self._active_gate_id = None
        success = self.worker.resolve_approval(gate_id, granted)
        if not success:
            _LOG.warning("Approval resolution rejected for gate_id=%s, granted=%s", gate_id, granted)

    def notify_user(self, title: str, message: str, level: str = "info") -> None:
        """Deliver user notifications both via in-app toast banner and system tray."""
        import app.core.config as _cfg
        if not getattr(_cfg, "JASPER_NOTIFICATIONS_ENABLED", True):
            return

        # 1. In-app toast banner
        if hasattr(self, "toast_banner"):
            self.toast_banner.show_toast(title, message, level=level, timeout_ms=5000)

        # 2. System tray notification (native OS toast)
        if getattr(self, "_tray", None) and self._tray.isVisible():
            icon_map = {
                "success": QSystemTrayIcon.MessageIcon.Information,
                "info": QSystemTrayIcon.MessageIcon.Information,
                "warning": QSystemTrayIcon.MessageIcon.Warning,
                "error": QSystemTrayIcon.MessageIcon.Critical,
            }
            tray_icon = icon_map.get(level.lower(), QSystemTrayIcon.MessageIcon.Information)
            try:
                self._tray.showMessage(title, message, tray_icon, 4500)
            except Exception as e:
                _LOG.warning("Could not show tray message: %s", e)

    @Slot()
    def _on_finished(self) -> None:
        self._set_busy(False)
        if hasattr(self, "tasks_page"):
            self.tasks_page.task_completed()

        snippet = ""
        if self._messages and self._messages[-1][0] == "JASPER":
            content = self._messages[-1][1]
            clean = content.replace("**", "").replace("#", "").strip()
            snippet = (clean[:90] + "...") if len(clean) > 90 else clean
        if snippet:
            self.notify_user("JASPER Task Complete", snippet, level="success")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        if hasattr(self, "vision_page") and self.vision_page._busy:
            self.vision_page.show_error(message)
            return
        self._streaming_active = False
        self._streaming_content = ""
        self._stop_thinking()
        self._append_message("JASPER", f"I couldn't complete that request.\n\n{message}")
        self._set_busy(False)
        self.notify_user("JASPER Error", message[:100], level="error")

    @Slot(dict)
    def _on_system_status(self, info: dict) -> None:
        ollama = info.get("ollama") or {}
        self.ollama_status.setText("Ollama ●" if ollama.get("available") else "Ollama ○")
        self.voice_status.setText("Voice ●" if JASPER_VOICE_ENABLED else "Voice ○")
        gpus = info.get("gpu") or []
        if gpus:
            self.gpu_status.setText(f"{gpus[0].get('name', 'GPU')} ●")
        else:
            self.gpu_status.setText("GPU ○")

        # Display startup diagnostics once
        if not hasattr(self, "_diagnostics_shown"):
            self._diagnostics_shown = True

            fast_model = "●" if info.get("model_fast_available") else "○"
            main_model = "●" if info.get("model_main_available") else "○"
            vision_model = "●" if info.get("model_vision_available") else "○"
            ollama_status = "●" if ollama.get("available") else "○"
            voice_status = "●" if JASPER_VOICE_ENABLED else "○"

            gpu_desc = f"{gpus[0].get('name')} ({gpus[0].get('vram_total_gb', 0)}GB)" if gpus else "Not detected"
            ram_desc = f"{info.get('ram_total_gb', 0)}GB ({info.get('ram_available_gb', 0)}GB available)"
            python_desc = info.get("python", "Unknown")

            msg = (
                f"<b>System Readiness</b><br><br>"
                f"Ollama API: {ollama_status} | Fast Model: {fast_model} | Main Model: {main_model} | Vision Model: {vision_model}<br>"
                f"Voice Input: {voice_status} | GPU: {gpu_desc} | RAM: {ram_desc} | Python: {python_desc}"
            )
            self.system_readiness_label.setText(msg)
            self.system_readiness_label.show()
            QTimer.singleShot(15000, self.system_readiness_label.hide)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.input.setEnabled(not busy)
        self.attach_button.setEnabled(not busy)
        self.mic_button.setEnabled(not busy and JASPER_VOICE_ENABLED)

        self.send_button.setEnabled(True)
        if busy:
            self.send_button.setText("Stop")
            self.send_button.setStyleSheet("background-color: #8b0000; color: white;")
        else:
            self.send_button.setText("Send")
            self.send_button.setStyleSheet("")

    def _show_thinking(self, label: str) -> None:
        self._thinking_step = 0
        self.thinking_indicator.setText(f"{label}…")
        self.thinking_indicator.show()
        self._thinking_timer.start()

    def _stop_thinking(self) -> None:
        self._thinking_timer.stop()
        self.thinking_indicator.hide()

    def _animate_thinking(self) -> None:
        self._thinking_step = (self._thinking_step + 1) % 4
        base = self.thinking_indicator.text().rstrip(".…")
        self.thinking_indicator.setText(base + "." * (self._thinking_step + 1))

    def _append_message(self, sender: str, content: str) -> None:
        self._messages.append((sender, content))
        self._render_conversation()

    def _render_conversation(self) -> None:
        blocks: list[str] = []
        for sender, content in self._messages:
            html = markdown_to_html(content)
            if sender.startswith("You"):
                blocks.append(f'<div align="right"><b>{escape(sender)}</b><br>{html}</div>')
            else:
                blocks.append(f'<div align="left"><b>{escape(sender)}</b><br>{html}</div>')
        self.conversation.setHtml("<br><br>".join(blocks))
        scrollbar = self.conversation.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:
        if self._tray is not None:
            try:
                self._tray.hide()
            except Exception:
                pass
        if hasattr(self, "_status_timer") and self._status_timer is not None:
            self._status_timer.stop()
        if hasattr(self, "_thinking_timer") and self._thinking_timer is not None:
            self._thinking_timer.stop()

        # Safely dismiss active approval dialog without granting access
        if hasattr(self, "_active_approval_dialog") and self._active_approval_dialog is not None:
            try:
                self._active_approval_dialog.handle_cancelled()
            except Exception:
                pass
            self._active_approval_dialog = None
            self._active_gate_id = None

        # Request cooperative cancellation before attempting thread termination
        if hasattr(self, "worker") and self.worker is not None:
            try:
                self.worker.cancel_request()
            except Exception as exc:
                _LOG.warning("Failed to cancel worker request during closeEvent: %s", exc)

        # Stop worker thread if running
        self._shutdown_clean = True
        if hasattr(self, "thread") and self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            stopped = self.thread.wait(3000)
            if not stopped:
                self._shutdown_clean = False
                _LOG.warning(
                    "Worker thread did not terminate within 3000ms shutdown timeout; unresolved lifecycle state."
                )

        event.accept()

    # ------------------------------------------------------------------
    # Image attachment helpers
    # ------------------------------------------------------------------

    @Slot()
    def _open_attachment(self) -> None:
        """Open a file-picker to select an image to attach to the next message."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach Image",
            "",
            OPEN_IMAGE_FILTER,
        )
        if path:
            self._set_attachment(path)

    def _set_attachment(self, path: str) -> None:
        """Store the image path and show the filename chip."""
        from pathlib import Path as _Path
        self._attached_image_path = path
        self.attachment_label.setText(f"📎 {_Path(path).name}")
        self.attachment_chip.show()

    @Slot()
    def _clear_attachment(self) -> None:
        """Dismiss the attached image and hide the chip."""
        self._attached_image_path = None
        self.attachment_label.setText("")
        self.attachment_chip.hide()

    # ------------------------------------------------------------------
    # Drag-and-drop for the Chat page
    # ------------------------------------------------------------------

    def _extract_valid_image_path(self, mime_data: QMimeData | None) -> str | None:
        """Return the local path of the first valid image URL in mime_data, or None."""
        if not mime_data or not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            local = url.toLocalFile()
            if not local:
                continue
            try:
                from pathlib import Path as _Path
                p = _Path(local).expanduser().resolve()
                if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    return str(p)
            except Exception:
                continue
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept image drops anywhere on the Chat page."""
        if self.page_stack.currentIndex() != 0 or self.busy:
            event.ignore()
            return
        if self._extract_valid_image_path(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._chat_drag_active = False
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """On drop, attach the image and show the chip."""
        self._chat_drag_active = False
        if self.page_stack.currentIndex() != 0 or self.busy:
            event.ignore()
            return
        path = self._extract_valid_image_path(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self._set_attachment(path)
