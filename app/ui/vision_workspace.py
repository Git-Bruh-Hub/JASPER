from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ui.markdown_renderer import markdown_to_html


class VisionWorkspace(QWidget):
    """Desktop image-understanding workspace."""

    analyze_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._selected_path: Path | None = None
        self._busy = False
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
        self.state_label = QLabel("Ready")
        self.state_label.setObjectName("workspaceHint")
        header.addWidget(self.state_label)
        layout.addLayout(header)

        controls = QHBoxLayout()
        self.open_button = QPushButton("Open Image")
        self.open_button.clicked.connect(self.open_image)
        controls.addWidget(self.open_button)
        self.path_label = QLabel("No image selected")
        self.path_label.setObjectName("workspaceHint")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.path_label, 1)
        layout.addLayout(controls)

        body = QHBoxLayout()
        body.setSpacing(12)

        preview_frame = QFrame(objectName="visionPreviewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        self.preview = QLabel("Open an image to preview it here")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 320)
        self.preview.setObjectName("visionPreview")
        preview_layout.addWidget(self.preview, 1)
        body.addWidget(preview_frame, 1)

        result_frame = QFrame(objectName="visionResultFrame")
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(12, 12, 12, 12)
        prompt_label = QLabel("Ask JASPER about the image")
        prompt_label.setObjectName("sidebarTitle")
        result_layout.addWidget(prompt_label)
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("e.g. What text can you read in this image?")
        self.prompt.returnPressed.connect(self.analyze)
        result_layout.addWidget(self.prompt)

        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setObjectName("sendButton")
        self.analyze_button.clicked.connect(self.analyze)
        self.analyze_button.setEnabled(False)
        result_layout.addWidget(self.analyze_button)

        self.result = QTextBrowser()
        self.result.setObjectName("conversation")
        self.result.setOpenExternalLinks(True)
        self.result.setPlaceholderText("Vision results will appear here.")
        result_layout.addWidget(self.result, 1)
        body.addWidget(result_frame, 1)
        layout.addLayout(body, 1)

    def open_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All files (*.*)",
        )
        if not file_path:
            return
        self.set_image(file_path)

    def set_image(self, file_path: str) -> None:
        path = Path(file_path).expanduser().resolve()
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            QMessageBox.warning(self, "Invalid image", "JASPER could not load this image file.")
            return
        self._selected_path = path
        self.path_label.setText(str(path))
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview.setText("")
        self.analyze_button.setEnabled(not self._busy)
        self.state_label.setText("Image ready")

    def analyze(self) -> None:
        if self._busy or self._selected_path is None:
            return
        prompt = self.prompt.text().strip()
        if not prompt:
            prompt = "Describe the image and mention only visually supported details."
        self.set_busy(True)
        self.result.setHtml("<p><i>JASPER is analyzing the image…</i></p>")
        self.analyze_requested.emit(str(self._selected_path), prompt)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.open_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and self._selected_path is not None)
        self.prompt.setEnabled(not busy)
        self.state_label.setText("Analyzing…" if busy else "Ready")

    @Slot(str)
    def show_result(self, answer: str) -> None:
        self.set_busy(False)
        self.result.setHtml(markdown_to_html(answer))
        self.state_label.setText("Analysis complete")

    @Slot(str)
    def show_error(self, message: str) -> None:
        self.set_busy(False)
        self.result.setHtml(markdown_to_html(f"**Vision failed**\n\n{message}"))
        self.state_label.setText("Analysis failed")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._selected_path is None:
            return
        pixmap = QPixmap(str(self._selected_path))
        if pixmap.isNull():
            return
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
