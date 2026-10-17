from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
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
        # Truncate title if long
        display_title = self.raw_title
        if len(display_title) > 26:
            display_title = display_title[:24].rstrip() + "…"
        prefix = "📌 " if self.is_pinned else "💬 "
        self.setText(f"{prefix}{display_title}")
        self.setToolTip(self.raw_title)

        border_left = "3px solid #8ee6a1" if self.is_active else "3px solid transparent"
        bg_color = "#2a2a2a" if self.is_active else "transparent"
        text_color = "#ffffff" if self.is_active else "#cccccc"

        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                background-color: {bg_color};
                border: none;
                border-left: {border_left};
                border-radius: 4px;
                color: {text_color};
                padding: 7px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: #242424;
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
        self._items: dict[str, SessionItemWidget] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedWidth(240)
        self.setStyleSheet(
            """
            QFrame#sessionDrawer {
                background-color: #191919;
                border-right: 1px solid #2b2b2b;
            }
            """
        )
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Header bar with + New Chat and Collapse Toggle
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(6)

        self.new_chat_btn = QPushButton("+ New Chat")
        self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #222222;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                padding: 7px 12px;
                text-align: center;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
                border-color: #8ee6a1;
                color: #8ee6a1;
            }
            """
        )
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        self.header_layout.addWidget(self.new_chat_btn, 1)

        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setToolTip("Collapse Chat History")
        self.toggle_btn.setFixedSize(28, 28)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #888888;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #242424;
                color: #ffffff;
            }
            """
        )
        self.toggle_btn.clicked.connect(self.toggle_collapse)
        self.header_layout.addWidget(self.toggle_btn)
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
                background: #191919;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #333333;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 4, 0, 0)
        self.content_layout.setSpacing(4)

        # Section labels
        self.pinned_section_label = QLabel("PINNED")
        self.pinned_section_label.setStyleSheet("color: #777777; font-size: 8pt; font-weight: 700; padding: 4px 6px 2px 6px; letter-spacing: 1px;")
        self.content_layout.addWidget(self.pinned_section_label)
        self.pinned_container = QVBoxLayout()
        self.pinned_container.setSpacing(2)
        self.content_layout.addLayout(self.pinned_container)

        self.recent_section_label = QLabel("RECENT CHATS")
        self.recent_section_label.setStyleSheet("color: #777777; font-size: 8pt; font-weight: 700; padding: 8px 6px 2px 6px; letter-spacing: 1px;")
        self.content_layout.addWidget(self.recent_section_label)
        self.recent_container = QVBoxLayout()
        self.recent_container.setSpacing(2)
        self.content_layout.addLayout(self.recent_container)

        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

    def toggle_collapse(self) -> None:
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            self.setFixedWidth(44)
            self.new_chat_btn.hide()
            self.scroll_area.hide()
            self.toggle_btn.setText("▶")
            self.toggle_btn.setToolTip("Expand Chat History")
        else:
            self.setFixedWidth(240)
            self.new_chat_btn.show()
            self.scroll_area.show()
            self.toggle_btn.setText("◀")
            self.toggle_btn.setToolTip("Collapse Chat History")

    def set_sessions(self, sessions: list[dict], active_session_id: str | None = None) -> None:
        self.active_session_id = active_session_id
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

        has_pinned = False
        has_recent = False

        for session in sessions:
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
