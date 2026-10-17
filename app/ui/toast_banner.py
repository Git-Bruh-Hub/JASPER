"""Toast banner widget for non-intrusive in-app notifications and task alerts."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ToastBanner(QFrame):
    """Floating or inline dark-themed notification banner conforming to JASPER design tokens."""

    dismissed = Signal()

    _THEMES = {
        "success": {
            "border": "#2e7d32",
            "bg": "#142416",
            "icon": "✓",
            "icon_color": "#8ee6a1",
            "title_color": "#a8f0b8",
        },
        "info": {
            "border": "#00838f",
            "bg": "#11262d",
            "icon": "ℹ",
            "icon_color": "#00bcd4",
            "title_color": "#80deea",
        },
        "warning": {
            "border": "#f57c00",
            "bg": "#2d1f11",
            "icon": "⚠",
            "icon_color": "#ffb74d",
            "title_color": "#ffe082",
        },
        "error": {
            "border": "#c62828",
            "bg": "#2b1414",
            "icon": "✕",
            "icon_color": "#ef5350",
            "title_color": "#ffcdd2",
        },
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toastBanner")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        self._init_ui()
        self.hide()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.label_icon = QLabel("✓")
        self.label_icon.setFixedWidth(20)
        self.label_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_icon.setStyleSheet("font-size: 13pt; font-weight: bold;")
        layout.addWidget(self.label_icon)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.label_title = QLabel("Notification")
        self.label_title.setStyleSheet("font-size: 9.5pt; font-weight: 600;")
        text_layout.addWidget(self.label_title)

        self.label_message = QLabel("Message body details")
        self.label_message.setWordWrap(True)
        self.label_message.setStyleSheet("color: #d0d0d0; font-size: 9pt;")
        text_layout.addWidget(self.label_message)

        layout.addLayout(text_layout, 1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet(
            "background: transparent; border: none; color: #888888; font-size: 10pt; font-weight: bold;"
            "QPushButton:hover { color: #ffffff; background: #333333; border-radius: 11px; }"
        )
        self.btn_close.clicked.connect(self.dismiss)
        layout.addWidget(self.btn_close)

    def show_toast(
        self,
        title: str,
        message: str,
        level: str = "info",
        timeout_ms: int = 5000,
    ) -> None:
        """Display toast banner with styled severity levels (info, success, warning, error)."""
        theme = self._THEMES.get(level.lower(), self._THEMES["info"])

        self.setStyleSheet(
            f"QFrame#toastBanner {{ "
            f"background: {theme['bg']}; "
            f"border: 1px solid {theme['border']}; "
            f"border-radius: 6px; "
            f"}}"
        )
        self.label_icon.setText(theme["icon"])
        self.label_icon.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {theme['icon_color']};")
        self.label_title.setText(title)
        self.label_title.setStyleSheet(f"font-size: 9.5pt; font-weight: 600; color: {theme['title_color']};")
        self.label_message.setText(message)

        self.show()
        if timeout_ms > 0:
            self._timer.start(timeout_ms)

    @Slot()
    def dismiss(self) -> None:
        """Hide the toast banner and emit dismissed signal."""
        self._timer.stop()
        self.hide()
        self.dismissed.emit()
