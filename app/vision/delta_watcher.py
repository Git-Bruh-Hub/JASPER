"""app/vision/delta_watcher.py -- Lightweight, low-overhead proactive screen observer for JASPER.

Enforces:
1. Low-overhead perceptual thumbnail diffing (32x32 grayscale <1ms, 0% GPU).
2. Goal-oriented vision analysis: only invokes VisionManager when a meaningful delta occurs.
3. Bounded autonomy: maximum duration cap (default 10 minutes) to prevent accidental infinite monitoring.
4. Privacy invariants: no continuous video recording or streaming; only targeted delta snapshots.
5. Asynchronous, non-blocking Qt execution.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage, QPixmap

from app.vision.capture import capture_active_screen, get_active_desktop_tasks
from app.vision.manager import VisionManager

_LOG = logging.getLogger("jasper.vision.delta_watcher")

# Default constraints
DEFAULT_CHECK_INTERVAL_SECONDS = 4.0
MIN_CHECK_INTERVAL_SECONDS = 2.0
MAX_CHECK_INTERVAL_SECONDS = 30.0
DEFAULT_MAX_DURATION_SECONDS = 600.0  # 10 minutes max
DEFAULT_SENSITIVITY_THRESHOLD = 0.03  # 3% pixel difference on 32x32 thumbnail


def compute_pixel_delta(b1: bytes | None, b2: bytes | None) -> float:
    """Compute normalized mean absolute pixel difference between two byte buffers (0.0 to 1.0)."""
    if not b1 or not b2 or len(b1) != len(b2) or len(b1) == 0:
        return 1.0 if (b1 or b2) else 0.0
    diff = sum(abs(x - y) for x, y in zip(b1, b2))
    return diff / (len(b1) * 255.0)


def grab_screen_thumbnail(size: int = 32) -> bytes:
    """Capture a tiny grayscale thumbnail of the active screen without saving to disk."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return b""
    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        return b""
    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    scaled = qimg.scaled(
        size,
        size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    return bytes(scaled.bits())


class DeltaScreenWatcher(QObject):
    """Proactive screen observation engine for JASPER."""

    alert_ready = Signal(str, str, str)  # title, message, screenshot_path
    watcher_status_changed = Signal(bool, str)  # is_watching, status_message
    frame_checked = Signal(float, bool)  # delta, has_changed

    def __init__(
        self,
        vision: VisionManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.vision = vision
        self._is_watching = False
        self._goal = ""
        self._interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS
        self._max_duration_seconds = DEFAULT_MAX_DURATION_SECONDS
        self._sensitivity = DEFAULT_SENSITIVITY_THRESHOLD
        self._start_time: datetime | None = None
        self._last_thumbnail: bytes | None = None
        self._last_tasks: list[str] = []
        self._in_flight = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

    @property
    def is_watching(self) -> bool:
        return self._is_watching

    @property
    def goal(self) -> str:
        return self._goal

    @Slot(str)
    @Slot(str, float)
    @Slot(str, float, float)
    def start_watching(
        self,
        goal: str = "",
        interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
        sensitivity: float = DEFAULT_SENSITIVITY_THRESHOLD,
    ) -> None:
        """Start the background delta observer."""
        if self._is_watching:
            self.stop_watching("Restarting with updated goal.")

        self._goal = goal.strip()
        self._interval_seconds = max(MIN_CHECK_INTERVAL_SECONDS, min(MAX_CHECK_INTERVAL_SECONDS, interval_seconds))
        self._max_duration_seconds = max_duration_seconds
        self._sensitivity = sensitivity
        self._start_time = datetime.now(timezone.utc)
        self._last_thumbnail = grab_screen_thumbnail()
        self._last_tasks = get_active_desktop_tasks()
        self._in_flight = False
        self._is_watching = True

        self._timer.setInterval(int(self._interval_seconds * 1000))
        self._timer.start()

        msg = f"Watching screen for: '{self._goal}'" if self._goal else "Watching screen for changes and alerts."
        _LOG.info("DeltaScreenWatcher started (interval=%.1fs, max_duration=%.1fs): %s", self._interval_seconds, self._max_duration_seconds, msg)
        self.watcher_status_changed.emit(True, msg)

    @Slot()
    @Slot(str)
    def stop_watching(self, reason: str = "Stopped by user.") -> None:
        """Stop the background delta observer."""
        if not self._is_watching:
            return

        self._is_watching = False
        self._timer.stop()
        self._in_flight = False
        self._start_time = None
        self._last_thumbnail = None
        self._last_tasks = []

        _LOG.info("DeltaScreenWatcher stopped: %s", reason)
        self.watcher_status_changed.emit(False, reason)

    def _on_tick(self) -> None:
        """Periodic timer check callback."""
        if not self._is_watching:
            return

        if self._in_flight:
            _LOG.debug("DeltaScreenWatcher tick skipped: previous verification still in flight.")
            return

        # Check maximum duration cap
        if self._start_time is not None:
            elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            if elapsed >= self._max_duration_seconds:
                self.stop_watching(f"Observation time limit ({self._max_duration_seconds:.0f}s) reached.")
                self.alert_ready.emit(
                    "Screen Watcher Concluded",
                    f"Observation time limit of {int(self._max_duration_seconds // 60)} minutes reached without further alerts.",
                    "",
                )
                return

        # Grab current lightweight thumbnail
        current_thumb = grab_screen_thumbnail()
        if not current_thumb:
            return

        if self._last_thumbnail is None:
            self._last_thumbnail = current_thumb
            self._last_tasks = get_active_desktop_tasks()
            return

        delta = compute_pixel_delta(self._last_thumbnail, current_thumb)
        current_tasks = get_active_desktop_tasks()
        tasks_changed = set(current_tasks) != set(self._last_tasks)

        if delta < self._sensitivity and not tasks_changed:
            self.frame_checked.emit(delta, False)
            return

        # Visual delta or active window delta detected!
        self.frame_checked.emit(delta, True)
        self._last_thumbnail = current_thumb
        self._last_tasks = current_tasks

        # Capture high-res screen for verification
        try:
            captured_path = capture_active_screen()
        except Exception as exc:
            _LOG.warning("Failed to capture active screen on delta: %s", exc)
            return

        # If no vision manager is configured, emit basic activity alert
        if self.vision is None:
            self.alert_ready.emit(
                "Screen Activity Detected",
                f"Visual change observed on your desktop (delta: {delta:.1%}).",
                str(captured_path),
            )
            return

        # Vision verification
        self._in_flight = True
        asyncio.create_task(self._verify_screen_delta(captured_path, delta))

    async def _verify_screen_delta(self, image_path: Path, delta: float) -> None:
        """Analyze the changed screen using VisionManager to determine if alert should fire."""
        try:
            if not self.vision:
                return

            if self._goal:
                prompt = (
                    f"The user asked to monitor their desktop screen with this specific objective: \"{self._goal}\".\n"
                    "Carefully examine this screenshot.\n"
                    "Did the watched event occur (e.g. build completed, download finished, error popup appeared, or requested condition met)?\n"
                    "Start your answer with 'YES: <summary>' if the event occurred, or 'NO: <summary>' if the event has not yet occurred."
                )
            else:
                prompt = (
                    "Examine this desktop screenshot.\n"
                    "Did an error dialog, completion notification, alert banner, or terminal failure just occur?\n"
                    "Start your answer with 'YES: <summary>' if an alert or error is visible, or 'NO: <summary>' if normal ongoing work."
                )

            analysis = await self.vision.analyze(image_path, prompt=prompt)
            answer = analysis.answer.strip()
            _LOG.info("DeltaScreenWatcher vision response: %s", answer[:120])

            # Evaluate decision
            upper_ans = answer.upper()
            is_match = False
            summary = answer

            if upper_ans.startswith("YES"):
                is_match = True
                summary = answer[3:].lstrip(": -").strip()
            elif any(kw in upper_ans for kw in ("COMPLETED", "FINISHED", "ERROR", "FAILED", "SUCCESSFULLY")):
                # Keyword heuristic confirmation
                if not upper_ans.startswith("NO"):
                    is_match = True

            if is_match:
                title = f"JASPER Screen Alert: {self._goal}" if self._goal else "JASPER Screen Alert"
                self.alert_ready.emit(title, summary, str(image_path))
                # Stop watching upon confirmed goal event
                self.stop_watching("Watched condition satisfied.")
            else:
                _LOG.debug("Screen change detected but target goal condition not satisfied yet: %s", summary[:80])

        except Exception as exc:
            _LOG.warning("DeltaScreenWatcher verification failed: %s", exc)
        finally:
            self._in_flight = False
