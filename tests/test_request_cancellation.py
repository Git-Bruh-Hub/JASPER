import asyncio
import threading

import pytest

from app.ui.cancellation import AsyncRequestController


def test_cancel_interrupts_running_async_request():
    controller = AsyncRequestController()
    controller.begin()

    started = threading.Event()
    finished = threading.Event()
    outcome = []

    async def never_finishes():
        started.set()
        await asyncio.Event().wait()

    def run_request():
        try:
            controller.run(never_finishes())
        except asyncio.CancelledError:
            outcome.append("cancelled")
        finally:
            finished.set()

    thread = threading.Thread(target=run_request)
    thread.start()

    assert started.wait(1.0)
    controller.cancel()

    assert finished.wait(1.0)
    thread.join(timeout=1.0)
    assert outcome == ["cancelled"]


def test_cancel_before_run_stops_request_without_starting_body():
    controller = AsyncRequestController()
    controller.begin()
    controller.cancel()

    ran = False

    async def request():
        nonlocal ran
        ran = True
        return "unexpected"

    with pytest.raises(asyncio.CancelledError):
        controller.run(request())

    assert not ran


def test_new_request_clears_previous_cancellation():
    controller = AsyncRequestController()
    controller.begin()
    controller.cancel()
    controller.begin()

    async def request():
        await asyncio.sleep(0)
        return "ok"

    assert controller.run(request()) == "ok"
    assert not controller.is_cancelled()
