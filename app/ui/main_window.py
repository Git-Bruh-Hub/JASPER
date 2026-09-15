from __future__ import annotations

from html import escape
import re

from PySide6.QtCore import QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.config import JASPER_VOICE_ENABLED
from app.ui.styles import APP_STYLE
from app.ui.worker import JasperWorker


class MainWindow(QMainWindow):
    request_text = Signal(str)
    request_voice = Signal()
    request_refresh_status = Signal()

    NAV_ITEMS = (
        ("💬  Chat", "Chat"),
        ("🧠  Tasks", "Tasks"),
        ("👁  Vision", "Vision"),
        ("🤖  Agents", "Agents"),
        ("📁  Files", "Files"),
        ("🌐  Web", "Web"),
        ("⚙  Settings", "Settings"),
    )

    def __init__(self, worker: JasperWorker, thread: QThread) -> None:
        super().__init__()
        self.worker = worker
        self.thread = thread
        self.busy = False
        self._tray: QSystemTrayIcon | None = None
        self.nav_buttons: list[QPushButton] = []
        self._thinking_step = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(450)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._messages: list[tuple[str, str]] = []
        self._streaming_content = ""
        self._streaming_active = False
        self.setWindowTitle("JASPER")
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
        brand = QLabel("JASPER")
        brand.setObjectName("brand")
        top_layout.addWidget(brand)
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

        self.conversation = QTextBrowser()
        self.conversation.setObjectName("conversation")
        self.conversation.setOpenExternalLinks(True)
        self.conversation.setReadOnly(True)
        self.conversation.document().setDefaultStyleSheet(
            "body{margin:0;padding:0;} "
            "h1{font-size:20pt;margin:12px 0 8px 0;} "
            "h2{font-size:16pt;margin:12px 0 7px 0;} "
            "h3{font-size:13pt;margin:10px 0 6px 0;} "
            "h4,h5,h6{font-size:11pt;margin:9px 0 5px 0;} "
            "p{margin:5px 0;line-height:1.35;} "
            "ul,ol{margin-top:5px;margin-bottom:7px;} "
            "li{margin:2px 0;} "
            "table{border-collapse:collapse;margin:8px 0;} "
            "th,td{border:1px solid #454545;padding:6px 9px;} "
            "th{background:#242424;font-weight:600;} "
            "blockquote{border-left:3px solid #555;padding-left:11px;color:#bdbdbd;margin:8px 0;} "
            "code{background:#242424;padding:2px 4px;} "
            "pre{background:#101010;border:1px solid #282828;padding:10px;margin:8px 0;} "
            "hr{border:0;border-top:1px solid #2b2b2b;margin:12px 0;} "
            "a{color:#8ee6a1;}"
        )
        chat_layout.addWidget(self.conversation, 1)

        self.thinking_indicator = QLabel("JASPER is working…")
        self.thinking_indicator.setObjectName("thinkingIndicator")
        self.thinking_indicator.hide()
        chat_layout.addWidget(self.thinking_indicator)

        composer = QFrame(objectName="composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(8, 6, 8, 6)
        composer_layout.setSpacing(6)
        self.input = QLineEdit()
        self.input.setObjectName("input")
        self.input.setPlaceholderText("Ask JASPER...")
        self.input.returnPressed.connect(self._send_text)
        composer_layout.addWidget(self.input, 1)
        self.mic_button = QPushButton("🎤")
        self.mic_button.setObjectName("micButton")
        self.mic_button.setToolTip("Speak to JASPER")
        self.mic_button.setEnabled(JASPER_VOICE_ENABLED)
        self.mic_button.clicked.connect(self._listen)
        composer_layout.addWidget(self.mic_button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._send_text)
        composer_layout.addWidget(self.send_button)
        chat_layout.addWidget(composer)
        self.page_stack.addWidget(self.chat_page)

        for _, page_name in self.NAV_ITEMS[1:]:
            self.page_stack.addWidget(self._placeholder_page(page_name))

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
            "Vision": "Images and screen understanding will be added in the vision milestone.",
            "Agents": "Adaptive multi-agent work will appear here when the agent layer is enabled.",
            "Files": "Safe file browsing and document workflows will be surfaced here.",
            "Web": "Web research and browsing controls will appear here in a later milestone.",
            "Settings": "Application, model, voice, permissions, and resource settings will live here.",
        }
        return descriptions[name]

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
        memory = QLabel("Memory ●")
        memory.setProperty("class", "statusChip")
        layout.addWidget(memory)
        tools = QLabel("Tools ●")
        tools.setProperty("class", "statusChip")
        layout.addWidget(tools)
        self.gpu_status = QLabel("GPU ○")
        self.gpu_status.setProperty("class", "statusChip")
        layout.addWidget(self.gpu_status)
        layout.addStretch(1)
        return frame

    def _connect_worker(self) -> None:
        self.request_text.connect(self.worker.send_text)
        self.request_voice.connect(self.worker.listen_once)
        self.request_refresh_status.connect(self.worker.refresh_system_status)
        self.worker.response_stream.connect(self._on_stream_chunk)
        self.worker.response_ready.connect(self._on_response)
        self.worker.status_changed.connect(self._set_status)
        self.worker.system_status_ready.connect(self._on_system_status)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_finished)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
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

    def _select_page(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _send_text(self) -> None:
        text = self.input.text().strip()
        if not text or self.busy:
            return
        self._append_message("You", text)
        self.input.clear()
        self._streaming_active = True
        self._streaming_content = ""
        self._show_thinking("JASPER is working")
        self._set_busy(True)
        self.request_text.emit(text)

    def _listen(self) -> None:
        if self.busy or not JASPER_VOICE_ENABLED:
            return
        self._streaming_active = False
        self._streaming_content = ""
        self._set_busy(True)
        self._show_thinking("Listening")
        self.request_voice.emit()

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
        self.workspace_hint.setText({
            "STANDBY": "Ready",
            "ACTIVE": "Working...",
            "LISTENING": "Listening...",
            "SPEAKING": "Speaking...",
        }.get(state, state.title()))
        if state == "ACTIVE" and not self._streaming_content:
            self._show_thinking("JASPER is working")
        elif state == "LISTENING":
            self._show_thinking("Listening")
        elif state == "SPEAKING":
            self._show_thinking("Speaking")

    @Slot()
    def _on_finished(self) -> None:
        self._set_busy(False)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._streaming_active = False
        self._streaming_content = ""
        self._stop_thinking()
        self._append_message("JASPER", f"I couldn't complete that request.\n\n{message}")
        self._set_busy(False)

    @Slot(dict)
    def _on_system_status(self, info: dict) -> None:
        ollama = info.get("ollama") or {}
        self.ollama_status.setText("Ollama ●" if ollama.get("available") else "Ollama ○")
        self.voice_status.setText("Voice ●" if JASPER_VOICE_ENABLED else "Voice ○")
        gpus = info.get("gpu") or []
        if gpus:
            name = gpus[0].get("name") or "GPU"
            self.gpu_status.setText(name)
        else:
            self.gpu_status.setText("GPU ○")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.send_button.setEnabled(not busy)
        self.mic_button.setEnabled(not busy and JASPER_VOICE_ENABLED)
        self.input.setEnabled(not busy)
        if not busy and not self._streaming_active:
            self._stop_thinking()

    def _show_thinking(self, prefix: str) -> None:
        self._thinking_step = 0
        self.thinking_indicator.setText(prefix)
        self.thinking_indicator.show()
        self._thinking_timer.start()

    def _stop_thinking(self) -> None:
        self._thinking_timer.stop()
        self.thinking_indicator.hide()

    def _animate_thinking(self) -> None:
        if not self.busy or self._streaming_content:
            self._thinking_timer.stop()
            return
        base = self.thinking_indicator.text().rstrip(".")
        self._thinking_step = (self._thinking_step + 1) % 4
        self.thinking_indicator.setText(f"{base}{'.' * self._thinking_step}")

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        """Render Markdown as rich text without exposing Markdown markers."""
        normalized = re.sub(r"\\([*_#`~\[\]-])", r"\1", text)
        document = QTextDocument()
        document.setMarkdown(normalized)
        html = document.toHtml()
        match = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else escape(normalized).replace("\n", "<br>")

    def _append_message(self, speaker: str, body: str) -> None:
        self._messages.append((speaker, body))
        self._render_conversation()

    def _render_conversation(self) -> None:
        blocks: list[str] = []
        for speaker, body in self._messages:
            is_user = speaker.startswith("You")
            align = "right" if is_user else "left"
            label_color = "#b7b7b7" if is_user else "#8ee6a1"
            speaker_html = escape(speaker)
            blocks.append(
                f'<div style="margin:10px 2px 16px 2px; text-align:{align};">'
                f'<div style="color:{label_color}; font-size:9pt; font-weight:600; margin-bottom:4px;">{speaker_html}</div>'
                f'<div style="color:#eeeeee; font-size:10pt;">{self._markdown_to_html(body)}</div>'
                "</div>"
            )
        self.conversation.setHtml("".join(blocks))
        cursor = self.conversation.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.conversation.setTextCursor(cursor)
        self.conversation.ensureCursorVisible()

    def closeEvent(self, event) -> None:
        if self.busy:
            answer = QMessageBox.question(
                self,
                "JASPER is working",
                "JASPER is still processing a request. Exit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self._tray is not None:
            self._tray.hide()
        self._stop_thinking()
        self.thread.quit()
        self.thread.wait(3000)
        QApplication.quit()
        event.accept()
