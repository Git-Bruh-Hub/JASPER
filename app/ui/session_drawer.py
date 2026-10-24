from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SessionItemWidget(QPushButton):
    """Clickable session item with right-click context menu for rename, pin, and delete."""

    rename_requested = Signal(str, str)  # session_id, new_title
    pin_requested = Signal(str, bool)  # session_id, is_pinned
    delete_requested = Signal(str)  # session_id

    def __init__(
        self,
        session_id: str,
        title: str,
        is_pinned: bool = False,
        is_active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_id = session_id
        self.raw_title = title
        self.is_pinned = is_pinned
        self.is_active = is_active
        self.setCheckable(True)
        self.setChecked(is_active)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._apply_styling()

    def _apply_styling(self) -> None:
        # Truncate title if long to fit sidebar width comfortably
        display_title = self.raw_title
        if len(display_title) > 22:
            display_title = display_title[:20].rstrip() + "…"
        prefix = "📌 " if self.is_pinned else "💬 "
        self.setText(f"{prefix}{display_title}")
        self.setToolTip(self.raw_title)

        border_left = "3px solid #8ee6a1" if self.is_active else "3px solid transparent"
        bg_color = "#282828" if self.is_active else "transparent"
        text_color = "#ffffff" if self.is_active else "#b5b5b5"

        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                background-color: {bg_color};
                border: none;
                border-left: {border_left};
                border-radius: 4px;
                color: {text_color};
                padding: 6px 8px;
                font-size: 8.5pt;
            }}
            QPushButton:hover {{
                background-color: #222222;
                color: #ffffff;
            }}
            """
        )

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self.setChecked(active)
        self._apply_styling()

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #202020;
                color: #f1f1f1;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c2c;
                color: #8ee6a1;
            }
            """
        )
        action_rename = menu.addAction("✏️ Rename Chat")
        pin_label = "📌 Unpin from Top" if self.is_pinned else "📌 Pin to Top"
        action_pin = menu.addAction(pin_label)
        menu.addSeparator()
        action_delete = menu.addAction("🗑️ Delete Chat")

        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == action_rename:
            new_title, ok = QInputDialog.getText(
                self,
                "Rename Chat",
                "Enter new chat title:",
                text=self.raw_title,
            )
            if ok and new_title.strip():
                self.rename_requested.emit(self.session_id, new_title.strip())
        elif chosen == action_pin:
            self.pin_requested.emit(self.session_id, not self.is_pinned)
        elif chosen == action_delete:
            confirm = QMessageBox.question(
                self,
                "Delete Chat",
                f"Are you sure you want to delete '{self.raw_title}'?\nThis will remove this conversation permanently.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(self.session_id)


class SessionDrawer(QFrame):
    """Collapsible session sidebar drawer inside the Chat workspace."""

    session_selected = Signal(str)  # session_id
    new_chat_requested = Signal()
    session_renamed = Signal(str, str)  # session_id, new_title
    session_pinned = Signal(str, bool)  # session_id, is_pinned
    delete_session_requested = Signal(str)  # session_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionDrawer")
        self.is_collapsed = False
        self.active_session_id: str | None = None
        self._raw_sessions: list[dict] = []
        self._sort_mode = "recent"
        self._filter_mode = "all"
        self._items: dict[str, SessionItemWidget] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        if self.parentWidget() is None:
            self.setFixedWidth(240)
        self.setStyleSheet(
            """
            QFrame#sessionDrawer {
                background-color: transparent;
                border: none;
            }
            """
        )
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # Header bar matching user's screenshot: "Chat History ▾" ... ≡ ✏
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(2, 2, 2, 2)
        self.header_layout.setSpacing(2)

        self.dropdown_btn = QPushButton("Chat History ▾")
        self.dropdown_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dropdown_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-size: 8.5pt;
                font-weight: 700;
                text-align: left;
                padding: 4px 2px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                color: #8ee6a1;
            }
            """
        )
        self.dropdown_btn.clicked.connect(self.toggle_collapse)
        self.header_layout.addWidget(self.dropdown_btn, 1)

        self.btn_more = QPushButton("···")
        self.btn_more.setToolTip("Chat History Options")
        self.btn_more.setFixedSize(22, 22)
        self.btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_more.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #777777;
                font-size: 10pt;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #282828;
            }
            """
        )
        self.btn_more.clicked.connect(self._show_options_menu)
        self.header_layout.addWidget(self.btn_more)

        self.btn_filter = QPushButton("≡")
        self.btn_filter.setToolTip("Filter & Sort Chats")
        self.btn_filter.setFixedSize(22, 22)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #777777;
                font-size: 11pt;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #282828;
            }
            """
        )
        self.btn_filter.clicked.connect(self._show_filter_menu)
        self.header_layout.addWidget(self.btn_filter)

        self.new_chat_btn = QPushButton("✏")
        self.new_chat_btn.setToolTip("New Chat")
        self.new_chat_btn.setFixedSize(22, 22)
        self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #8ee6a1;
                font-size: 9.5pt;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #253828;
            }
            """
        )
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        self.header_layout.addWidget(self.new_chat_btn)

        # Retain toggle_btn attribute for backwards compatibility with tests
        self.toggle_btn = self.dropdown_btn
        main_layout.addLayout(self.header_layout)

        # Scrollable container for sessions
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #333333;
                min-height: 20px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a4a4a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 2, 0, 0)
        self.content_layout.setSpacing(2)

        # Section labels
        self.pinned_section_label = QLabel("PINNED")
        self.pinned_section_label.setStyleSheet("color: #666666; font-size: 7.5pt; font-weight: 700; padding: 4px 4px 1px 4px; letter-spacing: 0.8px;")
        self.content_layout.addWidget(self.pinned_section_label)
        self.pinned_container = QVBoxLayout()
        self.pinned_container.setSpacing(2)
        self.content_layout.addLayout(self.pinned_container)

        self.recent_section_label = QLabel("RECENT CHATS")
        self.recent_section_label.setStyleSheet("color: #666666; font-size: 7.5pt; font-weight: 700; padding: 6px 4px 1px 4px; letter-spacing: 0.8px;")
        self.content_layout.addWidget(self.recent_section_label)
        self.recent_container = QVBoxLayout()
        self.recent_container.setSpacing(2)
        self.content_layout.addLayout(self.recent_container)

        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

        # Empty spacer to keep header pinned at the exact top when scroll_area is collapsed
        self.empty_spacer = QWidget()
        self.empty_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.empty_spacer.setStyleSheet("background: transparent;")
        main_layout.addWidget(self.empty_spacer, 1)
        self.empty_spacer.hide()

    def _show_options_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #202020;
                color: #f1f1f1;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2b4532;
                color: #8ee6a1;
            }
            """
        )
        new_act = menu.addAction("✏  New Chat")
        new_act.triggered.connect(self.new_chat_requested.emit)
        menu.addSeparator()
        collapse_act = menu.addAction("▾  Collapse All" if not self.is_collapsed else "▸  Expand All")
        collapse_act.triggered.connect(self.toggle_collapse)
        menu.exec(self.btn_more.mapToGlobal(QPoint(0, self.btn_more.height())))

    def _show_filter_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #202020;
                color: #f1f1f1;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2b4532;
                color: #8ee6a1;
            }
            """
        )
        act_recent = menu.addAction("🕒  Sort by Most Recent")
        act_alpha = menu.addAction("🔤  Sort Alphabetically")
        menu.addSeparator()
        act_all = menu.addAction("💬  Show All Chats")
        act_pinned = menu.addAction("📌  Show Pinned Only")

        chosen = menu.exec(self.btn_filter.mapToGlobal(QPoint(0, self.btn_filter.height())))
        if chosen == act_recent:
            self._sort_mode = "recent"
            self._refresh_display()
        elif chosen == act_alpha:
            self._sort_mode = "alpha"
            self._refresh_display()
        elif chosen == act_all:
            self._filter_mode = "all"
            self._refresh_display()
        elif chosen == act_pinned:
            self._filter_mode = "pinned"
            self._refresh_display()

    def toggle_collapse(self) -> None:
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            if self.parentWidget() is None:
                self.setFixedWidth(44)
            self.scroll_area.hide()
            self.empty_spacer.show()
            self.dropdown_btn.setText("Chat History ▸")
            self.dropdown_btn.setToolTip("Expand Chat History")
        else:
            if self.parentWidget() is None:
                self.setFixedWidth(240)
            self.empty_spacer.hide()
            self.scroll_area.show()
            self.dropdown_btn.setText("Chat History ▾")
            self.dropdown_btn.setToolTip("Collapse Chat History")

    def set_sessions(self, sessions: list[dict], active_session_id: str | None = None) -> None:
        self.active_session_id = active_session_id
        self._raw_sessions = list(sessions)
        self._refresh_display()

    def _refresh_display(self) -> None:
        self._items.clear()

        # Clear existing layout items
        while self.pinned_container.count():
            item = self.pinned_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self.recent_container.count():
            item = self.recent_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Apply filtering
        display_sessions = list(self._raw_sessions)
        if self._filter_mode == "pinned":
            display_sessions = [s for s in display_sessions if bool(s.get("is_pinned", 0))]

        # Apply sorting
        if self._sort_mode == "alpha":
            display_sessions.sort(key=lambda s: s.get("title", "").lower())
        else:
            # Sort by updated_at descending
            display_sessions.sort(key=lambda s: str(s.get("updated_at", "")), reverse=True)

        has_pinned = False
        has_recent = False

        for session in display_sessions:
            sid = session["id"]
            title = session.get("title", "Untitled Chat")
            is_pinned = bool(session.get("is_pinned", 0))
            is_active = (sid == self.active_session_id)

            widget = SessionItemWidget(
                session_id=sid,
                title=title,
                is_pinned=is_pinned,
                is_active=is_active,
                parent=self.content_widget,
            )
            widget.clicked.connect(lambda checked=False, s=sid: self._on_item_clicked(s))
            widget.rename_requested.connect(self.session_renamed.emit)
            widget.pin_requested.connect(self.session_pinned.emit)
            widget.delete_requested.connect(self.delete_session_requested.emit)
            self._items[sid] = widget

            if is_pinned:
                self.pinned_container.addWidget(widget)
                has_pinned = True
            else:
                self.recent_container.addWidget(widget)
                has_recent = True

        self.pinned_section_label.setVisible(has_pinned)
        self.recent_section_label.setVisible(has_recent)

    def _on_item_clicked(self, session_id: str) -> None:
        self.set_active_session(session_id)
        self.session_selected.emit(session_id)

    def set_active_session(self, session_id: str) -> None:
        self.active_session_id = session_id
        for sid, widget in self._items.items():
            widget.set_active(sid == session_id)
