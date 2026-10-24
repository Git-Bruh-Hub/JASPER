"""Interactive screen snipping overlay supporting dual and multi-monitor setups."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from app.core.config import DATA_DIR

_LOG = logging.getLogger("jasper.ui.snipper")


class ScreenSnipper(QWidget):
    """Fullscreen semi-transparent overlay allowing click-and-drag screen snipping across all monitors."""

    snipped = Signal(str)      # Emits saved image path
    cancelled = Signal()       # Emits when user cancels with Esc or clicks away

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_selecting = False
        self._desktop_pixmap: QPixmap = QPixmap()
        self._virtual_rect: QRect = QRect()

    def start_snip(self) -> None:
        """Capture the current virtual desktop and show the snipping overlay."""
        primary = QGuiApplication.primaryScreen()
        if not primary:
            self.cancelled.emit()
            return

        self._virtual_rect = primary.virtualGeometry()
        self.setGeometry(self._virtual_rect)

        # Grab the full virtual desktop (spanning all monitors)
        self._desktop_pixmap = primary.grabWindow(
            0,
            self._virtual_rect.x(),
            self._virtual_rect.y(),
            self._virtual_rect.width(),
            self._virtual_rect.height(),
        )

        self._start_pos = None
        self._current_pos = None
        self._is_selecting = False

        self.show()
        self.activateWindow()
        self.raise_()
        try:
            self.grabMouse()
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._release_mouse()
        super().closeEvent(event)

    def _release_mouse(self) -> None:
        try:
            self.releaseMouse()
        except Exception:
            pass

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._desktop_pixmap.isNull():
            return

        painter = QPainter(self)

        # 1. Draw the frozen desktop background
        painter.drawPixmap(0, 0, self._desktop_pixmap)

        # 2. Draw dim dark overlay (rgba 0, 0, 0, 110)
        overlay_color = QColor(0, 0, 0, 110)
        painter.fillRect(self.rect(), overlay_color)

        # 3. If selecting, cut out the selected rectangle and draw border + HUD
        if self._is_selecting and self._start_pos and self._current_pos:
            selection_rect = self._get_selection_rect()
            if not selection_rect.isEmpty():
                # Redraw selected area from desktop_pixmap without dim overlay
                painter.drawPixmap(selection_rect, self._desktop_pixmap, selection_rect)

                # Bright glowing green border (#8ee6a1)
                border_pen = QPen(QColor("#8ee6a1"), 2)
                painter.setPen(border_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(selection_rect)

                # Small size badge
                size_text = f"{selection_rect.width()} \u00d7 {selection_rect.height()} px"
                painter.setPen(QColor("#ffffff"))
                painter.setFont(self.font())
                badge_rect = QRect(selection_rect.left(), max(10, selection_rect.top() - 24), 110, 20)
                painter.fillRect(badge_rect, QColor(25, 25, 25, 220))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, size_text)

        # 4. Top guidance banner
        banner_rect = QRect(self.rect().width() // 2 - 260, 20, 520, 36)
        painter.fillRect(banner_rect, QColor(18, 18, 18, 230))
        painter.setPen(QPen(QColor("#454545"), 1))
        painter.drawRect(banner_rect)
        painter.setPen(QColor("#e0e0e0"))
        painter.drawText(
            banner_rect,
            Qt.AlignmentFlag.AlignCenter,
            "\U0001f4f8 Drag to snip region  |  Double-click to capture monitor  |  Esc to cancel",
        )

    def _get_selection_rect(self) -> QRect:
        if not self._start_pos or not self._current_pos:
            return QRect()
        max_w = self._desktop_pixmap.width() if not self._desktop_pixmap.isNull() else self.width()
        max_h = self._desktop_pixmap.height() if not self._desktop_pixmap.isNull() else self.height()
        x1 = max(0, min(self._start_pos.x(), self._current_pos.x()))
        y1 = max(0, min(self._start_pos.y(), self._current_pos.y()))
        x2 = min(max_w, max(self._start_pos.x(), self._current_pos.x()))
        y2 = min(max_h, max(self._start_pos.y(), self._current_pos.y()))
        return QRect(x1, y1, max(0, x2 - x1), max(0, y2 - y1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()
            self._current_pos = self._start_pos
            self._is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._release_mouse()
            self.close()
            self.cancelled.emit()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_selecting:
            self._current_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self._current_pos = event.position().toPoint()
            rect = self._get_selection_rect()

            self._release_mouse()
            if rect.width() >= 12 and rect.height() >= 12:
                self._save_and_emit(rect)
            else:
                self.close()
                self.cancelled.emit()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double click captures the entire monitor under the cursor."""
        self._release_mouse()
        global_pos = event.globalPosition().toPoint()
        screen = QGuiApplication.screenAt(global_pos)
        if screen:
            screen_geo = screen.geometry()
            # Map screen_geo from global coordinates to widget coordinates
            widget_top_left = screen_geo.topLeft() - self._virtual_rect.topLeft()
            rect = QRect(widget_top_left, screen_geo.size())
            self._save_and_emit(rect)
        else:
            self.close()
            self.cancelled.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._release_mouse()
            self.close()
            self.cancelled.emit()

    def _save_and_emit(self, rect: QRect) -> None:
        self._release_mouse()
        cropped = self._desktop_pixmap.copy(rect)
        self.close()

        target_dir = DATA_DIR / "captures"
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_path = target_dir / f"snip_{timestamp}.png"

        if cropped.save(str(file_path), "PNG"):
            _LOG.info("Snip saved: %s (%dx%d)", file_path, cropped.width(), cropped.height())
            self.snipped.emit(str(file_path))
        else:
            _LOG.error("Failed to save cropped snip to %s", file_path)
            self.cancelled.emit()
