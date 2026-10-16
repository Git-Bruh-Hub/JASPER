"""Screen capture utilities for JASPER desktop vision."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap

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
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    if not screens or primary is None:
        raise RuntimeError("No display screen detected for capture.")

    vgeo = primary.virtualGeometry()
    if len(screens) == 1:
        pixmap = primary.grabWindow(0)
    else:
        # Multi-monitor stitching: draw each display into a unified virtual desktop canvas
        canvas = QPixmap(vgeo.width(), vgeo.height())
        canvas.fill(Qt.GlobalColor.black)
        painter = QPainter(canvas)
        for s in screens:
            spix = s.grabWindow(0)
            if not spix.isNull():
                sg = s.geometry()
                painter.drawPixmap(sg.x() - vgeo.x(), sg.y() - vgeo.y(), spix)
        painter.end()
        pixmap = canvas

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


def get_active_desktop_tasks() -> list[str]:
    """Return a curated list of active user applications and open windows."""
    tasks: list[str] = []

    # 1. Try Windows EnumWindows for visible application titles
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        def enum_callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title and title not in ("Program Manager", "Settings", "Windows Input Experience"):
                        if title not in tasks:
                            tasks.append(title)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    except Exception:
        pass

    # 2. Add high-interest active user processes via psutil
    try:
        import psutil
        IGNORE_PROCS = {
            "system idle process", "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
            "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe", "memory compression",
            "spoolsv.exe", "taskhostw.exe", "explorer.exe", "shellexperiencehost.exe", "searchindexer.exe",
            "startmenuexperiencehost.exe", "runtimebroker.exe", "ctfmon.exe", "searchhost.exe",
            "securityhealthservice.exe", "securityhealthsystray.exe", "mpcmdrun.exe", "msmpeng.exe",
            "conhost.exe", "audiodg.exe", "wlanext.exe", "dashost.exe", "sihost.exe", "smartscreen.exe",
            "lockapp.exe", "wmiapsrv.exe", "wmiprvse.exe", "dllhost.exe", "textinputhost.exe", "bash.exe",
        }
        for proc in psutil.process_iter(["name"]):
            try:
                pname = proc.info.get("name")
                if pname and pname.lower() not in IGNORE_PROCS:
                    clean_name = pname[:-4] if pname.lower().endswith(".exe") else pname
                    if clean_name not in tasks and not any(clean_name.lower() in t.lower() for t in tasks):
                        tasks.append(clean_name)
            except Exception:
                pass
    except Exception:
        pass

    return tasks[:25]


def desktop_take_screenshot() -> dict[str, Any]:
    """Autonomous tool handler to capture the desktop screen."""
    path = capture_active_screen()
    return {
        "status": "success",
        "action": "desktop_take_screenshot",
        "path": str(path),
        "filename": path.name,
    }

