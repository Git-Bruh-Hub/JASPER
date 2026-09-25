"""app/core/approval.py — Asynchronous ApprovalGate for JASPER v0.7.

Invariants enforced
-------------------
* Approval is fully asynchronous — the Qt worker thread is never blocked
  (invariant 6).  The gate creates an ``asyncio.Future`` on the event
  loop that the Coordinator ``await``s; the Qt GUI thread resolves the
  Future via ``loop.call_soon_threadsafe``.
* Every gate has a unique ID and an expiry (invariant 7).
* Cancellation from ``AsyncRequestController`` interrupts every active
  gate (invariant 8).
* Critic verification never reaches this module — it has no access
  (invariant 11).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agents.contracts import ProposedAction
from app.core.audit import AuditEvent, record

_LOG = logging.getLogger("jasper.approval")

# Maximum time (seconds) the gate waits for user input before expiring.
DEFAULT_GATE_TIMEOUT_SECONDS = 120


# ---------------------------------------------------------------------------
# ApprovalRequest — what gets surfaced to the UI
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApprovalRequest:
    """Immutable description of an action awaiting user approval.

    This object is emitted to the UI layer (via a Qt Signal) so the user
    can make an informed decision.  It carries no executable code.

    Attributes
    ----------
    gate_id:
        Unique identifier for this approval request.
    action:
        The proposed action requiring approval.
    expires_at:
        UTC timestamp after which the gate automatically expires.
    """
    gate_id: str
    action: ProposedAction
    expires_at: datetime


# ---------------------------------------------------------------------------
# ApprovalResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApprovalResult:
    """Outcome of an ApprovalGate.

    Attributes
    ----------
    gate_id:
        Matches the corresponding ``ApprovalRequest.gate_id``.
    granted:
        True if the user approved, False if denied or cancelled.
    cancelled:
        True when the gate was interrupted by ``AsyncRequestController``.
    expired:
        True when the gate timed out before user input.
    """
    gate_id: str
    granted: bool
    cancelled: bool = False
    expired: bool = False


# ---------------------------------------------------------------------------
# ApprovalGate
# ---------------------------------------------------------------------------

class ApprovalGate:
    """Single-use asynchronous approval gate.

    Lifecycle
    ---------
    1. ``Coordinator`` creates a gate for a ``ProposedAction``.
    2. ``Coordinator`` emits an ``ApprovalRequest`` to the UI (Qt Signal).
    3. ``Coordinator`` calls ``await gate.wait()`` — suspends on the loop,
       *never* blocking the worker OS thread.
    4. Qt GUI thread calls ``gate.resolve(granted=True/False)`` after
       the user clicks Continue or Cancel.
    5. The ``asyncio.Future`` resolves; ``wait()`` returns.
    6. If ``AsyncRequestController.cancel()`` is called, the Coordinator's
       task is cancelled, the ``CancelledError`` propagates through
       ``wait()`` automatically because asyncio task cancellation interrupts
       ``await``.
    7. If the timeout expires, the gate auto-resolves as expired/denied.

    Parameters
    ----------
    action:
        The proposed action requiring approval.
    timeout:
        Seconds before the gate auto-expires.  ``None`` uses
        ``DEFAULT_GATE_TIMEOUT_SECONDS``.
    """

    def __init__(
        self,
        action: ProposedAction,
        timeout: float | None = None,
    ) -> None:
        self.gate_id: str = str(uuid.uuid4())
        self.action = action
        self._timeout = timeout if timeout is not None else DEFAULT_GATE_TIMEOUT_SECONDS
        self._future: asyncio.Future[bool] | None = None
        self._expires_at: datetime | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Public API (called from the Coordinator, running on the event loop)
    # ------------------------------------------------------------------

    def make_request(self) -> ApprovalRequest:
        """Build the ``ApprovalRequest`` to send to the UI."""
        from datetime import timedelta
        expires = datetime.now(timezone.utc) + timedelta(seconds=self._timeout)
        self._expires_at = expires
        record(
            AuditEvent.APPROVAL_REQUESTED,
            actor="coordinator",
            tool_name=self.action.tool_name,
            operation=self.action.scope.operation,
            risk=self.action.scope.risk,
            resource=self.action.scope.resource_scope,
            action_id=self.action.action_id,
            status="PENDING",
        )
        return ApprovalRequest(
            gate_id=self.gate_id,
            action=self.action,
            expires_at=expires,
        )

    async def wait(self) -> ApprovalResult:
        """Await user resolution.

        Returns an ``ApprovalResult`` with the outcome.  Raises
        ``asyncio.CancelledError`` if the enclosing task is cancelled by
        ``AsyncRequestController`` — the caller (Coordinator) must handle
        this and emit an APPROVAL_CANCELLED audit event.

        This coroutine is designed to be awaited inside the same event
        loop that ``AsyncRequestController.run()`` creates.  Task
        cancellation will interrupt the ``asyncio.wait_for`` call
        transparently.
        """
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._future = loop.create_future()

        try:
            granted = await asyncio.wait_for(
                asyncio.shield(self._future),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            _LOG.warning("approval gate timed out gate_id=%s", self.gate_id)
            record(
                AuditEvent.APPROVAL_EXPIRED,
                actor="coordinator",
                tool_name=self.action.tool_name,
                action_id=self.action.action_id,
                status="EXPIRED",
            )
            return ApprovalResult(
                gate_id=self.gate_id,
                granted=False,
                expired=True,
            )
        # CancelledError propagates upward — Coordinator catches and audits it.

        event = AuditEvent.APPROVAL_GRANTED if granted else AuditEvent.APPROVAL_DENIED
        record(
            event,
            actor="user",
            tool_name=self.action.tool_name,
            operation=self.action.scope.operation,
            risk=self.action.scope.risk,
            resource=self.action.scope.resource_scope,
            action_id=self.action.action_id,
            status="SUCCESS" if granted else "DENIED",
            user_approved=granted,
        )
        return ApprovalResult(gate_id=self.gate_id, granted=granted)

    # ------------------------------------------------------------------
    # Public API (called from Qt GUI thread via signal handler)
    # ------------------------------------------------------------------

    def resolve(self, *, granted: bool) -> None:
        """Resolve the gate from any thread (e.g. the Qt GUI thread).

        Thread-safe: uses ``loop.call_soon_threadsafe`` to schedule
        ``Future.set_result`` on the event loop without blocking the
        GUI thread.

        Has no effect if the gate was never awaited, already resolved,
        or the future is done for any other reason.
        """
        if self._loop is None or self._future is None:
            _LOG.warning("resolve() called before gate was awaited gate_id=%s", self.gate_id)
            return
        if self._future.done():
            return
        self._loop.call_soon_threadsafe(self._future.set_result, granted)
