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


def desktop_take_screenshot() -> dict[str, Any]:
    """Autonomous tool handler to capture the desktop screen."""
    path = capture_primary_screen()
    return {
        "status": "success",
        "action": "desktop_take_screenshot",
        "path": str(path),
        "filename": path.name,
    }
