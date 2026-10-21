"""tests/test_delta_watcher.py -- Deterministic tests for DeltaScreenWatcher proactive vision."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from app.vision.delta_watcher import (
    DEFAULT_CHECK_INTERVAL_SECONDS,
    DEFAULT_MAX_DURATION_SECONDS,
    DeltaScreenWatcher,
    compute_pixel_delta,
    grab_screen_thumbnail,
)


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# 1. Pixel Delta Math
# ---------------------------------------------------------------------------

def test_compute_pixel_delta_identical():
    buf = bytes([128] * 1024)
    assert compute_pixel_delta(buf, buf) == 0.0


def test_compute_pixel_delta_maximum_difference():
    black = bytes([0] * 1024)
    white = bytes([255] * 1024)
    assert compute_pixel_delta(black, white) == 1.0


def test_compute_pixel_delta_partial_difference():
    b1 = bytes([100] * 1024)
    b2 = bytes([200] * 1024)
    delta = compute_pixel_delta(b1, b2)
    assert round(delta, 3) == round(100.0 / 255.0, 3)


def test_compute_pixel_delta_empty_or_mismatched():
    assert compute_pixel_delta(b"", b"") == 0.0
    assert compute_pixel_delta(b"abc", b"") == 1.0
    assert compute_pixel_delta(b"abc", b"abcd") == 1.0


# ---------------------------------------------------------------------------
# 2. Thumbnail Grabbing
# ---------------------------------------------------------------------------

def test_grab_screen_thumbnail_offscreen(qapp):
    thumb = grab_screen_thumbnail(size=32)
    # Offscreen display produces 32x32 = 1024 grayscale bytes
    assert isinstance(thumb, bytes)
    assert len(thumb) == 1024


# ---------------------------------------------------------------------------
# 3. Watcher Lifecycle
# ---------------------------------------------------------------------------

def test_delta_watcher_lifecycle(qapp):
    watcher = DeltaScreenWatcher(vision=None)
    assert not watcher.is_watching
    assert watcher.goal == ""

    status_events = []
    watcher.watcher_status_changed.connect(lambda active, msg: status_events.append((active, msg)))

    # Start watching
    watcher.start_watching(goal="Wait for test suite", interval_seconds=3.0, max_duration_seconds=300.0)
    assert watcher.is_watching
    assert watcher.goal == "Wait for test suite"
    assert watcher._interval_seconds == 3.0
    assert watcher._max_duration_seconds == 300.0
    assert watcher._timer.isActive()
    assert len(status_events) == 1
    assert status_events[0][0] is True
    assert "Wait for test suite" in status_events[0][1]

    # Stop watching
    watcher.stop_watching("Task finished")
    assert not watcher.is_watching
    assert not watcher._timer.isActive()
    assert len(status_events) == 2
    assert status_events[1][0] is False
    assert "Task finished" in status_events[1][1]


# ---------------------------------------------------------------------------
# 4. Tick Without Delta
# ---------------------------------------------------------------------------

def test_watcher_tick_no_delta(qapp):
    watcher = DeltaScreenWatcher(vision=None)
    frames_checked = []
    watcher.frame_checked.connect(lambda d, changed: frames_checked.append((d, changed)))

    same_bytes = bytes([50] * 1024)
    with patch("app.vision.delta_watcher.grab_screen_thumbnail", return_value=same_bytes), \
         patch("app.vision.delta_watcher.get_active_desktop_tasks", return_value=["VS Code"]):
        watcher.start_watching()

        # First tick establishes baseline
        watcher._on_tick()

        # Second tick with same thumbnail
        watcher._on_tick()

    assert len(frames_checked) == 2
    delta, changed = frames_checked[0]
    assert delta == 0.0
    assert changed is False
    watcher.stop_watching()


# ---------------------------------------------------------------------------
# 5. Tick With Delta and Vision Verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watcher_tick_delta_triggers_alert(qapp):
    mock_vision = MagicMock()
    mock_result = MagicMock()
    mock_result.answer = "YES: Build succeeded with zero errors."
    mock_vision.analyze = AsyncMock(return_value=mock_result)

    watcher = DeltaScreenWatcher(vision=mock_vision)

    alerts = []
    watcher.alert_ready.connect(lambda title, msg, path: alerts.append((title, msg, path)))

    b1 = bytes([0] * 1024)
    b2 = bytes([255] * 1024)

    dummy_screenshot = Path("fake_screen_alert.png")

    with patch("app.vision.delta_watcher.grab_screen_thumbnail", side_effect=[b1, b2]), \
         patch("app.vision.delta_watcher.get_active_desktop_tasks", return_value=["Terminal"]), \
         patch("app.vision.delta_watcher.capture_active_screen", return_value=dummy_screenshot):
        watcher.start_watching(goal="Notify when build finishes")

        # Establish baseline
        watcher._on_tick()

        # Visual change occurs
        watcher._on_tick()

        # Yield event loop for async vision analysis to complete
        await asyncio.sleep(0.05)

    assert len(alerts) == 1
    title, msg, path = alerts[0]
    assert "Notify when build finishes" in title
    assert "Build succeeded with zero errors" in msg
    assert str(dummy_screenshot) in path
    # Watcher automatically stopped upon verified goal match
    assert not watcher.is_watching


# ---------------------------------------------------------------------------
# 6. Max Duration Cap Enforcement
# ---------------------------------------------------------------------------

def test_watcher_max_duration_cap(qapp):
    watcher = DeltaScreenWatcher(vision=None)
    alerts = []
    watcher.alert_ready.connect(lambda title, msg, path: alerts.append((title, msg, path)))

    watcher.start_watching(max_duration_seconds=10.0)
    # Simulate time passing beyond max duration
    watcher._start_time = datetime.now(timezone.utc) - timedelta(seconds=15)

    watcher._on_tick()

    assert not watcher.is_watching
    assert len(alerts) == 1
    assert "Screen Watcher Concluded" in alerts[0][0]
    assert "time limit" in alerts[0][1]
