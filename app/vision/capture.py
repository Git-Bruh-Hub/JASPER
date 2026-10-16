"""Screen capture utilities for JASPER desktop vision."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from PySide6.QtGui import QGuiApplication

from app.core.config import DATA_DIR

_LOG = logging.getLogger("jasper.vision.capture")


def capture_primary_screen(save_dir: Path | None = None) -> Path:
    """Capture the user's primary desktop display and save it as a PNG image.

    Returns the absolute Path of the saved capture file.
    """
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No primary display screen detected for capture.")

    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        raise RuntimeError("Failed to grab window from primary screen.")

    target_dir = (save_dir or (DATA_DIR / "captures")).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = target_dir / f"screen_{timestamp}.png"

    if not pixmap.save(str(file_path), "PNG"):
        raise RuntimeError(f"Failed to save screen capture image to {file_path}")

    _LOG.info("Screen captured successfully: %s (%dx%d)", file_path, pixmap.width(), pixmap.height())
    return file_path


def capture_active_screen(save_dir: Path | None = None) -> Path:
    """Capture the screen display where the mouse cursor is located, or primary screen."""
    from PySide6.QtGui import QCursor
    pos = QCursor.pos()
    screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No active display screen detected for capture.")

    geo = screen.geometry()
    pixmap = screen.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
    if pixmap.isNull():
        pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        raise RuntimeError("Failed to grab window from active screen.")

    target_dir = (save_dir or (DATA_DIR / "captures")).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = target_dir / f"screen_{timestamp}.png"

    if not pixmap.save(str(file_path), "PNG"):
        raise RuntimeError(f"Failed to save screen capture image to {file_path}")

    _LOG.info("Active screen (%s) captured successfully: %s (%dx%d)", screen.name(), file_path, pixmap.width(), pixmap.height())
    return file_path


def capture_virtual_desktop(save_dir: Path | None = None) -> Path:
    """Capture the full virtual desktop spanning all connected monitors."""
    primary = QGuiApplication.primaryScreen()
    if primary is None:
        raise RuntimeError("No primary display screen detected for capture.")

    vgeo = primary.virtualGeometry()
    pixmap = primary.grabWindow(0, vgeo.x(), vgeo.y(), vgeo.width(), vgeo.height())
    if pixmap.isNull():
        pixmap = primary.grabWindow(0)
    if pixmap.isNull():
        raise RuntimeError("Failed to grab virtual desktop.")

    target_dir = (save_dir or (DATA_DIR / "captures")).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = target_dir / f"desktop_{timestamp}.png"

    if not pixmap.save(str(file_path), "PNG"):
        raise RuntimeError(f"Failed to save virtual desktop capture image to {file_path}")

    _LOG.info("Virtual desktop captured: %s (%dx%d)", file_path, pixmap.width(), pixmap.height())
    return file_path


def desktop_take_screenshot() -> dict[str, Any]:
    """Autonomous tool handler to capture the desktop screen."""
    path = capture_active_screen()
    return {
        "status": "success",
        "action": "desktop_take_screenshot",
        "path": str(path),
        "filename": path.name,
    }

