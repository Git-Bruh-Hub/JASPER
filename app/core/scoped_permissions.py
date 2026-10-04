"""app/core/scoped_permissions.py — Expanded permission enforcement for JASPER v0.7.

The v0.6 ``PermissionManager`` in ``app/core/permissions.py`` is intentionally
left completely untouched (invariant 13).  This module introduces a *new*,
separately instantiated ``ScopedPermissionManager`` that the v0.7 Coordinator
uses.

Key behaviours
--------------
* Authorisation always happens immediately before execution (invariant 4).
* Resource paths / scopes are canonicalised before authorisation (invariant 5).
* Agent output can never grant permission — the manager is the sole authority
  (invariant 3).
* Critic verification result is irrelevant here (invariant 11).
* Every permission-sensitive check is audited (invariant 14).

``ScopedPermissionManager`` does *not* replace ``PermissionManager``.
It is used exclusively by the Coordinator for v0.7 multi-agent flows.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.agents.contracts import ApprovalRequirement, PermissionScope, ProposedAction
from app.core.audit import AuditEvent, record
from app.tools.registry import Risk, Tool


# ---------------------------------------------------------------------------
# Workspace root — the maximum allowed filesystem scope for any tool action
# ---------------------------------------------------------------------------

def _default_workspace_root() -> Path:
    """Return the canonicalised absolute workspace root.

    Falls back to the current working directory if ``JASPER_WORKSPACE``
    is not set.  Always returns a real absolute path so that scope
    comparisons are unambiguous (invariant 5).
    """
    raw = os.environ.get("JASPER_WORKSPACE", "")
    base = Path(raw) if raw else Path.cwd()
    return base.resolve()


class ScopedPermissionManager:
    """Permission enforcement for the v0.7 multi-agent Coordinator.

    Responsibilities
    ----------------
    1. Check that a ``Tool`` is permitted by the base risk policy.
    2. Check that a ``ProposedAction``'s scope does not exceed the allowed
       resource scope (scope escalation guard).
    3. Emit an audit record for every check, pass or fail.

    This class intentionally does *not* handle ApprovalGate lifecycle —
    that is the Coordinator's responsibility.  This class only checks
    whether an action is *in principle* permitted by policy before the
    Coordinator decides whether it also needs user approval.

    Parameters
    ----------
    workspace_root:
        All filesystem operations must target paths within (or equal to)
        this directory.  Defaults to the canonicalised ``JASPER_WORKSPACE``
        env var or cwd.
    allowed_risks:
        Set of Risk values this manager permits.  Defaults to READ only,
        matching the v0.6 baseline.
    actor:
        Identifier used in audit records for actions authorised through
        this manager instance (e.g. ``"coordinator"``).
    """

    def __init__(
        self,
        workspace_root: Path | None = None,
        allowed_risks: frozenset[Risk] | None = None,
        actor: str = "coordinator",
    ) -> None:
        self._workspace = (workspace_root or _default_workspace_root()).resolve()
        self._allowed_risks = allowed_risks if allowed_risks is not None else frozenset({Risk.READ})
        self._actor = actor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_tool(self, tool: Tool) -> None:
        """Assert that a Tool is permitted by the base risk policy.

        Raises ``PermissionError`` and emits a SCOPE_DENIED audit record
        if the tool's risk level is not in ``allowed_risks``.
        """
        permitted = tool.risk in self._allowed_risks
        record(
            AuditEvent.PERMISSION_CHECK,
            actor=self._actor,
            tool_name=tool.name,
            risk=tool.risk.value,
            operation="tool_policy_check",
            resource="",
            status="SUCCESS" if permitted else "DENIED",
        )
        if not permitted:
            raise PermissionError(
                f"Tool '{tool.name}' has risk '{tool.risk.value}' which is not "
                f"permitted by the current policy (allowed: "
                f"{sorted(r.value for r in self._allowed_risks)})."
            )

    def check_scope(self, action: ProposedAction) -> None:
        """Assert that a ProposedAction does not escalate beyond its declared scope.

        For filesystem operations, the resource_scope must be an absolute
        path that is a child of (or equal to) the workspace root.
        Canonicalises the path before comparison (invariant 5).

        Raises ``PermissionError`` and emits a SCOPE_DENIED audit record
        on failure.

        Note: this method does NOT check approval requirement — that is
        managed by the ApprovalGate lifecycle.
        """
        scope = action.scope
        denied_reason = self._evaluate_scope(scope)
        audit_event = AuditEvent.SCOPE_DENIED if denied_reason else AuditEvent.PERMISSION_CHECK
        status = "DENIED" if denied_reason else "SUCCESS"

        record(
            audit_event,
            actor=self._actor,
            tool_name=action.tool_name,
            operation=scope.operation,
            risk=scope.risk,
            resource=scope.resource_scope,
            action_id=action.action_id,
            status=status,
            detail=denied_reason or "",
        )

        if denied_reason:
            raise PermissionError(denied_reason)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_scope(self, scope: PermissionScope) -> str:
        """Return a non-empty denial reason string, or empty string if OK."""
        # Filesystem scope check
        if scope.risk in ("write", "execute", "destructive") or scope.operation.startswith("file."):
            return self._check_filesystem_scope(scope.resource_scope)
        # Network operations: deny by default
        if scope.risk == "network":
            return (
                f"Network operations are denied by default policy. "
                f"resource={scope.resource_scope!r}"
            )
        # ADMIN is always denied
        if scope.risk == "admin":
            return "ADMIN risk operations are unconditionally denied."
        return ""

    def _check_filesystem_scope(self, resource_scope: str) -> str:
        """Ensure the resource_scope path is inside the workspace root."""
        if not resource_scope:
            return "resource_scope must not be empty for filesystem operations."
        try:
            target = Path(resource_scope).resolve()
        except Exception as exc:
            return f"Could not canonicalise resource_scope: {exc}"

        # is_relative_to is Python 3.9+; we use resolve() which we require.
        try:
            target.relative_to(self._workspace)
        except ValueError:
            return (
                f"Scope escalation detected: '{target}' is outside the allowed "
                f"workspace root '{self._workspace}'."
            )
        return ""
