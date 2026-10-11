"""app/core/audit.py — Structured audit logging for JASPER v0.7.

Every permission-sensitive action produces a structured audit event.
Events are written to the Python logging system under the
``jasper.audit`` logger at INFO level.

The audit log satisfies invariant 14: every permission-sensitive
execution is auditable and contains sufficient fields for post-hoc
investigation.

Fields logged for every event
------------------------------
- timestamp    : ISO-8601 UTC
- event        : event type string (see AuditEvent)
- actor        : who requested the action (e.g. "coordinator", "planner")
- tool_name    : name of the tool involved (or empty string)
- operation    : scope.operation (e.g. "file.read")
- risk         : scope.risk category
- resource     : scope.resource_scope
- action_id    : ProposedAction.action_id, or empty string
- status       : "SUCCESS", "DENIED", "FAILED", "CANCELLED", "UNKNOWN"
- user_approved: True/False/None (None = not required)
- detail       : optional human-readable extra context
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

_LOG = logging.getLogger("jasper.audit")


class AuditEvent(str, Enum):
    """Enumeration of auditable event types."""
    PERMISSION_CHECK        = "permission_check"        # PermissionManager.check() called
    APPROVAL_REQUESTED      = "approval_requested"      # ApprovalGate created
    APPROVAL_GRANTED        = "approval_granted"        # User clicked Continue
    APPROVAL_DENIED         = "approval_denied"         # User clicked Cancel
    APPROVAL_EXPIRED        = "approval_expired"        # Gate timed out
    APPROVAL_CANCELLED      = "approval_cancelled"      # Cancelled by AsyncRequestController
    TOOL_EXECUTION          = "tool_execution"          # Tool handler called
    TOOL_SUCCESS            = "tool_success"            # Tool returned without error
    TOOL_FAILED             = "tool_failed"             # Tool raised an exception
    TOOL_UNKNOWN            = "tool_unknown"            # Outcome indeterminate (invariant 10)
    SCOPE_DENIED            = "scope_denied"            # Resource outside allowed scope
    BUDGET_EXCEEDED         = "budget_exceeded"         # Autonomy budget limit hit
    # Slice 5: Retry and failure handling
    TOOL_RETRY              = "tool_retry"              # Retriable op being retried (attempt N)
    TOOL_RETRY_EXHAUSTED    = "tool_retry_exhausted"    # All retries consumed; op failed
    VERIFICATION_RECOVERY   = "verification_recovery"   # Bounded recovery after verify fail
    # Slice 6: Agent Logic — Planner/Executor delegation (DisagreementResolver now live)
    PLANNER_INVOKED         = "planner_invoked"         # Planner agent called
    EXECUTOR_INVOKED        = "executor_invoked"        # Executor agent called
    DISAGREEMENT_DETECTED   = "disagreement_detected"   # Executor proposed unexpected tools
    DISAGREEMENT_HALTED     = "disagreement_halted"     # Resolution limit reached; safe halt


def record(
    event: AuditEvent | str,
    *,
    actor: str,
    tool_name: str = "",
    operation: str = "",
    risk: str = "",
    resource: str = "",
    action_id: str = "",
    status: str = "SUCCESS",
    user_approved: bool | None = None,
    detail: str = "",
    attempt: int | None = None,
    task_id: str = "",
) -> None:
    """Emit one structured audit record to the ``jasper.audit`` logger.

    All callers MUST provide at minimum ``event`` and ``actor``.  All
    other fields should be populated to the extent the call site has
    access to them — partial records are acceptable, missing records
    are not.
    """
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event.value if isinstance(event, AuditEvent) else str(event),
        "actor": actor,
        "tool_name": tool_name,
        "operation": operation,
        "risk": risk,
        "resource": resource,
        "action_id": action_id,
        "status": status,
        "user_approved": user_approved,
        "detail": detail,
    }
    if attempt is not None:
        payload["attempt"] = attempt
    if task_id:
        payload["task_id"] = task_id
    _LOG.info(json.dumps(payload, ensure_ascii=False))
