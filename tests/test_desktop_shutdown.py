"""Tests for Step 13: Desktop Window-Close and Cancellation Hardening.

Covers:
- Closing the window while a request is active requests cancellation.
- Closing while idle is harmless.
- Closing when thread is not running does not wait or quit.
- Worker-thread shutdown timeout is handled and recorded without claiming successful termination.
- Repeated cancellation is harmless.
- Cancellation requested before task registration does not leave a request running.
- Cancellation while awaiting a controlled asyncio event unwinds the task and runs cleanup.
- Real JasperWorker.cancel_request interrupts active task and handles voice.stop errors gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app.ui.cancellation import AsyncRequestController
from app.ui.main_window import MainWindow
from app.ui.worker import JasperWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# 1. Window close while active requests cancellation
# ---------------------------------------------------------------------------

def test_closing_window_while_request_active_requests_cancellation(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    thread.isRunning.return_value = True
    thread.wait.return_value = True

    window = MainWindow(worker, thread)
    window.busy = True

    event = QCloseEvent()
    window.closeEvent(event)

    # Worker cancellation must be called before thread shutdown
    worker.cancel_request.assert_called_once()
    thread.quit.assert_called_once()
    thread.wait.assert_called_once_with(3000)
    assert event.isAccepted() is True
    assert window._shutdown_clean is True


# ---------------------------------------------------------------------------
# 2. Window close while idle is harmless
# ---------------------------------------------------------------------------

def test_closing_window_while_idle_is_harmless(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    thread.isRunning.return_value = True
    thread.wait.return_value = True

    window = MainWindow(worker, thread)
    window.busy = False

    event = QCloseEvent()
    window.closeEvent(event)

    worker.cancel_request.assert_called_once()
    thread.quit.assert_called_once()
    thread.wait.assert_called_once_with(3000)
    assert event.isAccepted() is True
    assert window._shutdown_clean is True


# ---------------------------------------------------------------------------
# 3. Window close when thread is not running
# ---------------------------------------------------------------------------

def test_closing_window_when_thread_not_running_does_not_block(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    thread.isRunning.return_value = False

    window = MainWindow(worker, thread)

    event = QCloseEvent()
    window.closeEvent(event)

    worker.cancel_request.assert_called_once()
    thread.quit.assert_not_called()
    thread.wait.assert_not_called()
    assert event.isAccepted() is True
    assert window._shutdown_clean is True


# ---------------------------------------------------------------------------
# 4. Worker thread shutdown timeout records unclean state and warning
# ---------------------------------------------------------------------------

def test_worker_thread_shutdown_timeout_records_unclean_and_logs(qapp, caplog):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    thread.isRunning.return_value = True
    thread.wait.return_value = False  # Simulates thread wait timeout

    window = MainWindow(worker, thread)

    event = QCloseEvent()
    with caplog.at_level(logging.WARNING, logger="jasper.ui.main_window"):
        window.closeEvent(event)

    assert window._shutdown_clean is False
    assert event.isAccepted() is True
    assert "Worker thread did not terminate within 3000ms shutdown timeout" in caplog.text


# ---------------------------------------------------------------------------
# 5. Repeated cancellation is harmless
# ---------------------------------------------------------------------------

def test_repeated_cancellation_is_harmless():
    controller = AsyncRequestController()
    controller.begin()

    # Repeated calls before run
    controller.cancel()
    controller.cancel()
    controller.cancel()
    assert controller.is_cancelled() is True

    # After run completes
    async def fast():
        return 42

    controller.begin()
    res = controller.run(fast())
    assert res == 42

    # Repeated calls after run completes
    controller.cancel()
    controller.cancel()
    assert controller.is_cancelled() is True


# ---------------------------------------------------------------------------
# 6. Cancellation requested before task registration does not leave request running
# ---------------------------------------------------------------------------

def test_cancellation_before_task_registration_stops_execution():
    controller = AsyncRequestController()
    controller.begin()
    controller.cancel()

    ran = False

    async def coro():
        nonlocal ran
        ran = True
        return "done"

    with pytest.raises(asyncio.CancelledError):
        controller.run(coro())

    assert ran is False
    assert controller.has_active_request() is False


# ---------------------------------------------------------------------------
# 7. Cancellation while awaiting controlled event unwinds and runs cleanup
# ---------------------------------------------------------------------------

def test_cancellation_while_awaiting_controlled_event_unwinds_and_cleans_up():
    controller = AsyncRequestController()
    controller.begin()

    started = threading.Event()
    cleaned_up = threading.Event()
    outcome = []

    async def long_request():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()

    def run_worker():
        try:
            controller.run(long_request())
        except asyncio.CancelledError:
            outcome.append("cancelled")

    t = threading.Thread(target=run_worker)
    t.start()

    assert started.wait(2.0)
    assert controller.has_active_request() is True

    controller.cancel()

    assert cleaned_up.wait(2.0)
    t.join(timeout=2.0)

    assert outcome == ["cancelled"]
    assert controller.has_active_request() is False


# ---------------------------------------------------------------------------
# 8. Real JasperWorker.cancel_request interrupts active task & handles voice errors
# ---------------------------------------------------------------------------

def test_jasper_worker_cancel_request_protects_against_voice_stop_error(qapp):
    worker = JasperWorker()
    mock_voice = MagicMock()
    mock_voice.stop.side_effect = RuntimeError("Audio device busy")
    worker.voice = mock_voice

    started = threading.Event()
    outcome = []

    async def dummy():
        started.set()
        await asyncio.Event().wait()

    def run_worker():
        try:
            worker._request_control.begin()
            worker._request_control.run(dummy())
        except asyncio.CancelledError:
            outcome.append("cancelled")

    t = threading.Thread(target=run_worker)
    t.start()

    assert started.wait(2.0)
    assert worker.has_active_request() is True

    # Real worker.cancel_request() executes controller.cancel() and catches voice.stop error
    worker.cancel_request()

    t.join(timeout=2.0)
    assert outcome == ["cancelled"]
    assert worker.has_active_request() is False
    mock_voice.stop.assert_called_once()
