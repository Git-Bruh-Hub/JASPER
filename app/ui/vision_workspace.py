from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ui.markdown_renderer import markdown_to_html
from app.vision.image import SUPPORTED_IMAGE_EXTENSIONS

OPEN_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp);;All Files (*.*)"
FEEDBACK_VALID_STYLE = "border: 2px dashed #8ee6a1; color: #8ee6a1; background: #1c261e;"
FEEDBACK_INVALID_STYLE = "border: 2px dashed #e06c75; color: #e06c75; background: #261c1c;"


class VisionWorkspace(QWidget):
    """Desktop workspace for explicit, read-only image analysis."""

    OPEN_IMAGE_FILTER = OPEN_IMAGE_FILTER
    analyze_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image_path = ""
        self._busy = False
        self._drag_state: str | None = None
        self._saved_status: str | None = None
        self._current_pixmap: QPixmap | None = None
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.setInterval(1500)
        self._feedback_timer.timeout.connect(self._reset_drag_feedback)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Vision")
        title.setObjectName("workspaceTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.status = QLabel("Ready")
        self.status.setObjectName("workspaceHint")
        header.addWidget(self.status)
        layout.addLayout(header)

        self.preview = QLabel("Open an image to begin")
        self.preview.setObjectName("visionPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview.setScaledContents(False)
        layout.addWidget(self.preview, 1)

        controls = QHBoxLayout()
        self.open_button = QPushButton("Open Image")
        self.open_button.clicked.connect(self._open_image)
        controls.addWidget(self.open_button)

        self.path_label = QLabel("No image selected")
        self.path_label.setObjectName("workspaceHint")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.path_label, 1)
        layout.addLayout(controls)

        prompt_row = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Ask JASPER about the image...")
        self.prompt.returnPressed.connect(self._request_analysis)
        self.prompt.setAcceptDrops(False)
        prompt_row.addWidget(self.prompt, 1)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self._request_analysis)
        prompt_row.addWidget(self.analyze_button)
        layout.addLayout(prompt_row)

        self.result = QTextBrowser()
        self.result.setObjectName("conversation")
        self.result.setOpenExternalLinks(True)
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("Vision results will appear here.")
        self.result.setAcceptDrops(False)
        layout.addWidget(self.result, 1)

    def _extract_valid_image_path(self, mime_data: QMimeData | None) -> Path | None:
        """Extract the first valid local image file matching supported formats."""
        if not mime_data or not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            local_file = url.toLocalFile()
            if not local_file:
                continue
            try:
                path = Path(local_file).expanduser().resolve()
                if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    return path
            except Exception:
                continue
        return None

    def _set_drag_feedback(self, *, valid: bool) -> None:
        self._feedback_timer.stop()
        new_state = "valid" if valid else "invalid"
        if self._drag_state is None:
            self._saved_status = self.status.text()
        self._drag_state = new_state

        if valid:
            self.preview.setText("Release to load image")
            self.preview.setStyleSheet(FEEDBACK_VALID_STYLE)
            self.status.setText("Release to load image")
        else:
            self.preview.setText("Unsupported file")
            self.preview.setStyleSheet(FEEDBACK_INVALID_STYLE)
            self.status.setText("Unsupported file")
            self._feedback_timer.start()

    def _reset_drag_feedback(self) -> None:
        self._feedback_timer.stop()
        if self._drag_state is None:
            return
        self._drag_state = None
        self.preview.setStyleSheet("")
        if self._current_pixmap and not self._current_pixmap.isNull():
            self._show_preview(self._current_pixmap)
        else:
            self.preview.clear()
            self.preview.setText("Open an image to begin")

        if self._saved_status is not None:
            self.status.setText(self._saved_status)
            self._saved_status = None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._busy:
            event.ignore()
            return

        mime = event.mimeData()
        if not mime or not mime.hasUrls():
            event.ignore()
            return

        path = self._extract_valid_image_path(mime)
        if path is not None:
            self._set_drag_feedback(valid=True)
            event.acceptProposedAction()
        else:
            self._set_drag_feedback(valid=False)
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._busy:
            event.ignore()
            return

        path = self._extract_valid_image_path(event.mimeData())
        if path is not None:
            self._set_drag_feedback(valid=True)
            event.acceptProposedAction()
        else:
            if event.mimeData() and event.mimeData().hasUrls():
                self._set_drag_feedback(valid=False)
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._reset_drag_feedback()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._reset_drag_feedback()
        if self._busy:
            event.ignore()
            return

        path = self._extract_valid_image_path(event.mimeData())
        if path is None:
            event.ignore()
            return

        event.acceptProposedAction()
        self.set_image(str(path))

    @Slot()
    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            OPEN_IMAGE_FILTER,
        )
        if not path:
            return
        self.set_image(path)

    def set_image(self, image_path: str) -> None:
        path = Path(image_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            self.show_error("JASPER only supports PNG, JPG, JPEG, and WebP images.")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.show_error("JASPER could not load that image.")
            return
        self._current_pixmap = pixmap
        self._image_path = str(path)
        self.path_label.setText(path.name)
        self.path_label.setToolTip(str(path))
        self._show_preview(pixmap)
        self.analyze_button.setEnabled(True)
        self.status.setText("Image ready")
        self.result.clear()

    def _show_preview(self, pixmap: QPixmap) -> None:
        available = self.preview.size()
        if available.width() <= 0 or available.height() <= 0:
            self.preview.setPixmap(pixmap)
            return
        scaled = pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)

    @Slot()
    def _request_analysis(self) -> None:
        if self._busy or not self._image_path:
            return
        prompt = self.prompt.text().strip()
        if not prompt:
            prompt = "Analyze this image. Describe what is clearly visible and do not guess uncertain details."
        self._busy = True
        self.open_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.prompt.setEnabled(False)
        self.status.setText("Analyzing image...")
        self.result.setHtml("<p><i>JASPER is analyzing the image...</i></p>")
        self.analyze_requested.emit(self._image_path, prompt)

    @Slot(str)
    def show_result(self, answer: str) -> None:
        self._busy = False
        self.open_button.setEnabled(True)
        self.analyze_button.setEnabled(bool(self._image_path))
        self.prompt.setEnabled(True)
        self.status.setText("Analysis complete")
        self.result.setHtml(markdown_to_html(answer))

    @Slot(str)
    def show_error(self, message: str) -> None:
        self._busy = False
        self.open_button.setEnabled(True)
        self.analyze_button.setEnabled(bool(self._image_path))
        self.prompt.setEnabled(True)
        self.status.setText("Vision error")
        self.result.setHtml(markdown_to_html(f"**Vision error**\n\n{message}"))
