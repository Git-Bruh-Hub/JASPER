from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from app.ui.markdown_renderer import markdown_to_html


class VisionWorkspace(QWidget):
    """Desktop workspace for explicit, read-only image analysis."""

    analyze_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image_path = ""
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
        layout.addWidget(self.result, 1)

    @Slot()
    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*.*)",
        )
        if not path:
            return
        self.set_image(path)

    def set_image(self, image_path: str) -> None:
        path = Path(image_path).expanduser().resolve()
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.show_error("JASPER could not load that image.")
            return
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
