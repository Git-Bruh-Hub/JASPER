from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncRequestController:
    """Thread-safe cancellation controller for a worker-owned asyncio request loop."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[Any] | None = None

    def begin(self) -> None:
        """Prepare a new request and clear cancellation from the previous one."""
        with self._lock:
            if self._task is not None and not self._task.done():
                raise RuntimeError("Cannot begin a new request while another request is active.")
            self._cancel_event.clear()
            self._loop = None
            self._task = None

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        """Request cooperative cancellation and cancel the active asyncio task immediately."""
        self._cancel_event.set()
        with self._lock:
            loop = self._loop
            task = self._task

        if loop is not None and task is not None and not task.done():
            loop.call_soon_threadsafe(task.cancel)

    def run(self, awaitable: Awaitable[T]) -> T:
        """Run one request in the current worker thread with cross-thread cancellation."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task = loop.create_task(awaitable)

        with self._lock:
            self._loop = loop
            self._task = task

        if self._cancel_event.is_set():
            task.cancel()

        try:
            return loop.run_until_complete(task)
        finally:
            pending = asyncio.all_tasks(loop)
            for pending_task in pending:
                pending_task.cancel()

            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )

            with self._lock:
                if self._task is task:
                    self._task = None
                if self._loop is loop:
                    self._loop = None

            asyncio.set_event_loop(None)
            loop.close()
