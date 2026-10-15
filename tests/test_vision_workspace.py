"""Tests for VisionWorkspace drag-and-drop and image UX (v0.5.1)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from app.ui.vision_workspace import OPEN_IMAGE_FILTER, VisionWorkspace

# Minimal valid 1x1 PNG, JPEG, and WebP bytes for testing
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
    "BwYIDAoMCwsKCwsNCxAQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQME"
    "BAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
    "FBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/"
    "EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAA"
    "AAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AKwA//9k="
)
WEBP_BYTES = base64.b64decode(
    "UklGRjwAAABXRUJQVlA4IDAAAAAQAgCdASoKAAoAAgA0JaACdLoB+AH4AAPIAP7mad/7WgODVf5n//vvhRHbr/MUAAA="
)


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def workspace(qapp):
    widget = VisionWorkspace()
    return widget


def _make_drag_enter_event(urls: list[QUrl]) -> QDragEnterEvent:
    mime = QMimeData()
    mime.setUrls(urls)
    event = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # PySide6 garbage collects QMimeData if not retained by a Python reference
    event._mime_ref = mime
    return event


def _make_drag_move_event(urls: list[QUrl]) -> QDragMoveEvent:
    mime = QMimeData()
    mime.setUrls(urls)
    event = QDragMoveEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    event._mime_ref = mime
    return event


def _make_drop_event(urls: list[QUrl]) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls(urls)
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    event._mime_ref = mime
    return event


# ---------------------------------------------------------------------------
# Filter and Open Image tests
# ---------------------------------------------------------------------------


def test_open_image_filter_matches_supported_extensions(workspace: VisionWorkspace) -> None:
    assert "*.png" in OPEN_IMAGE_FILTER
    assert "*.jpg" in OPEN_IMAGE_FILTER
    assert "*.jpeg" in OPEN_IMAGE_FILTER
    assert "*.webp" in OPEN_IMAGE_FILTER
    assert "*.bmp" not in OPEN_IMAGE_FILTER
    assert "*.gif" not in OPEN_IMAGE_FILTER
    assert workspace.OPEN_IMAGE_FILTER == OPEN_IMAGE_FILTER


def test_open_image_behavior_loads_image(
    workspace: VisionWorkspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "valid.png"
    image.write_bytes(PNG_BYTES)

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(image), OPEN_IMAGE_FILTER),
    )

    workspace._open_image()

    assert workspace._image_path == str(image.resolve())
    assert workspace.path_label.text() == "valid.png"
    assert workspace.analyze_button.isEnabled() is True
    assert workspace.status.text() == "Image ready"


# ---------------------------------------------------------------------------
# Drag Enter tests (visual feedback & acceptance)
# ---------------------------------------------------------------------------


def test_drag_enter_valid_png(workspace: VisionWorkspace, tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    image.write_bytes(PNG_BYTES)

    event = _make_drag_enter_event([QUrl.fromLocalFile(str(image))])
    workspace.dragEnterEvent(event)

    assert event.isAccepted() is True
    assert workspace.preview.text() == "Release to load image"
    assert workspace.status.text() == "Release to load image"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("photo.jpg", JPEG_BYTES),
        ("photo.jpeg", JPEG_BYTES),
        ("photo.webp", WEBP_BYTES),
    ],
)
def test_drag_enter_supported_formats(
    workspace: VisionWorkspace, tmp_path: Path, filename: str, content: bytes
) -> None:
    image = tmp_path / filename
    image.write_bytes(content)

    event = _make_drag_enter_event([QUrl.fromLocalFile(str(image))])
    workspace.dragEnterEvent(event)

    assert event.isAccepted() is True
    assert workspace.preview.text() == "Release to load image"
    assert workspace.status.text() == "Release to load image"


@pytest.mark.parametrize(
    "unsupported_name",
    ["notes.txt", "doc.pdf", "animation.gif", "bitmap.bmp", "script.py"],
)
def test_drag_enter_unsupported_extension_rejected(
    workspace: VisionWorkspace, tmp_path: Path, unsupported_name: str
) -> None:
    file = tmp_path / unsupported_name
    file.write_text("content", encoding="utf-8")

    event = _make_drag_enter_event([QUrl.fromLocalFile(str(file))])
    workspace.dragEnterEvent(event)

    assert event.isAccepted() is False
    assert workspace.preview.text() == "Unsupported file"
    assert workspace.status.text() == "Unsupported file"


def test_drag_enter_non_local_url_rejected(workspace: VisionWorkspace) -> None:
    remote_url = QUrl("https://example.com/image.png")

    event = _make_drag_enter_event([remote_url])
    workspace.dragEnterEvent(event)

    assert event.isAccepted() is False
    assert workspace.preview.text() == "Unsupported file"
    assert workspace.status.text() == "Unsupported file"


def test_drag_enter_directory_rejected(workspace: VisionWorkspace, tmp_path: Path) -> None:
    folder = tmp_path / "images_folder"
    folder.mkdir()

    event = _make_drag_enter_event([QUrl.fromLocalFile(str(folder))])
    workspace.dragEnterEvent(event)

    assert event.isAccepted() is False
    assert workspace.preview.text() == "Unsupported file"
    assert workspace.status.text() == "Unsupported file"


# ---------------------------------------------------------------------------
# Drag Move and Drag Leave tests
# ---------------------------------------------------------------------------


def test_drag_move_maintains_valid_feedback(workspace: VisionWorkspace, tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)

    enter_event = _make_drag_enter_event([QUrl.fromLocalFile(str(image))])
    workspace.dragEnterEvent(enter_event)

    move_event = _make_drag_move_event([QUrl.fromLocalFile(str(image))])
    workspace.dragMoveEvent(move_event)

    assert move_event.isAccepted() is True
    assert workspace.preview.text() == "Release to load image"


def test_drag_leave_restores_initial_ui(workspace: VisionWorkspace, tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)

    enter_event = _make_drag_enter_event([QUrl.fromLocalFile(str(image))])
    workspace.dragEnterEvent(enter_event)
    assert workspace.status.text() == "Release to load image"

    leave_event = QDragLeaveEvent()
    workspace.dragLeaveEvent(leave_event)

    assert workspace.preview.text() == "Open an image to begin"
    assert workspace.status.text() == "Ready"


def test_drag_leave_restores_previously_loaded_image(workspace: VisionWorkspace, tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)
    workspace.set_image(str(image))
    assert workspace.status.text() == "Image ready"

    # Start dragging an unsupported file
    unsupported = tmp_path / "bad.txt"
    unsupported.write_text("invalid", encoding="utf-8")
    enter_event = _make_drag_enter_event([QUrl.fromLocalFile(str(unsupported))])
    workspace.dragEnterEvent(enter_event)
    assert workspace.status.text() == "Unsupported file"

    # Leave drag area
    leave_event = QDragLeaveEvent()
    workspace.dragLeaveEvent(leave_event)

    # Should restore previous status and preview
    assert workspace.status.text() == "Image ready"
    assert workspace.path_label.text() == "test.png"


# ---------------------------------------------------------------------------
# Drop Event tests (pipeline reuse & validation)
# ---------------------------------------------------------------------------


def test_drop_valid_png_loads_image_without_auto_analyze(
    workspace: VisionWorkspace, tmp_path: Path
) -> None:
    image = tmp_path / "dropped.png"
    image.write_bytes(PNG_BYTES)

    spy = MagicMock()
    workspace.analyze_requested.connect(spy)

    drop_event = _make_drop_event([QUrl.fromLocalFile(str(image))])
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is True
    assert workspace._image_path == str(image.resolve())
    assert workspace.path_label.text() == "dropped.png"
    assert workspace.analyze_button.isEnabled() is True
    assert workspace.status.text() == "Image ready"
    assert workspace.result.toPlainText() == ""
    # Crucial: Must NOT send image to model automatically on drop
    spy.assert_not_called()
    assert workspace._busy is False


def test_drop_valid_webp_loads_image(workspace: VisionWorkspace, tmp_path: Path) -> None:
    image = tmp_path / "dropped.webp"
    image.write_bytes(WEBP_BYTES)

    drop_event = _make_drop_event([QUrl.fromLocalFile(str(image))])
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is True
    assert workspace._image_path == str(image.resolve())
    assert workspace.path_label.text() == "dropped.webp"
    assert workspace.analyze_button.isEnabled() is True


def test_drop_unsupported_file_rejected(workspace: VisionWorkspace, tmp_path: Path) -> None:
    doc = tmp_path / "document.pdf"
    doc.write_bytes(b"%PDF-1.4...")

    drop_event = _make_drop_event([QUrl.fromLocalFile(str(doc))])
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is False
    assert workspace._image_path == ""
    assert workspace.analyze_button.isEnabled() is False


def test_drop_non_local_url_rejected(workspace: VisionWorkspace) -> None:
    remote_url = QUrl("https://example.com/picture.jpg")

    drop_event = _make_drop_event([remote_url])
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is False
    assert workspace._image_path == ""


def test_drop_directory_rejected(workspace: VisionWorkspace, tmp_path: Path) -> None:
    folder = tmp_path / "folder.png"
    folder.mkdir()

    drop_event = _make_drop_event([QUrl.fromLocalFile(str(folder))])
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is False
    assert workspace._image_path == ""


def test_drop_multiple_files_uses_first_valid_image(workspace: VisionWorkspace, tmp_path: Path) -> None:
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("hello", encoding="utf-8")

    img1 = tmp_path / "first_valid.png"
    img1.write_bytes(PNG_BYTES)

    img2 = tmp_path / "second_valid.jpg"
    img2.write_bytes(JPEG_BYTES)

    urls = [
        QUrl.fromLocalFile(str(txt_file)),
        QUrl.fromLocalFile(str(img1)),
        QUrl.fromLocalFile(str(img2)),
    ]

    drop_event = _make_drop_event(urls)
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is True
    assert workspace._image_path == str(img1.resolve())
    assert workspace.path_label.text() == "first_valid.png"
    assert workspace.analyze_button.isEnabled() is True


def test_drop_multiple_files_with_no_valid_image_rejected(
    workspace: VisionWorkspace, tmp_path: Path
) -> None:
    f1 = tmp_path / "readme.txt"
    f1.write_text("1", encoding="utf-8")
    f2 = tmp_path / "notes.pdf"
    f2.write_bytes(b"pdf")

    urls = [QUrl.fromLocalFile(str(f1)), QUrl.fromLocalFile(str(f2))]
    drop_event = _make_drop_event(urls)
    workspace.dropEvent(drop_event)

    assert drop_event.isAccepted() is False
    assert workspace._image_path == ""


def test_set_image_rejects_unsupported_file_extension(workspace: VisionWorkspace, tmp_path: Path) -> None:
    bad_file = tmp_path / "picture.bmp"
    bad_file.write_bytes(b"BM...")

    workspace.set_image(str(bad_file))

    assert workspace._image_path == ""
    assert workspace.analyze_button.isEnabled() is False
    assert workspace.status.text() == "Vision error"
    assert "only supports PNG, JPG, JPEG, and WebP" in workspace.result.toPlainText()


def test_drag_and_drop_ignored_when_busy(workspace: VisionWorkspace, tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    image.write_bytes(PNG_BYTES)

    workspace._busy = True

    enter_event = _make_drag_enter_event([QUrl.fromLocalFile(str(image))])
    workspace.dragEnterEvent(enter_event)
    assert enter_event.isAccepted() is False

    drop_event = _make_drop_event([QUrl.fromLocalFile(str(image))])
    workspace.dropEvent(drop_event)
    assert drop_event.isAccepted() is False
    assert workspace._image_path == ""
