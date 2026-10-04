"""app/agents/coordinator.py — JASPER v0.7 Coordinator state machine.

Invariants enforced
-------------------
1.  Agents never execute tools directly — only the Coordinator calls tools.
2.  ProposedActions are validated before any execution.
3.  Agent output can never grant permission — ScopedPermissionManager is
    the sole authority.
4.  Permission authorisation happens immediately before execution.
5.  Resource paths/scopes are canonicalised before authorisation.
6.  Approval is asynchronous; the Qt worker thread is never blocked.
7.  Approval requests have unique IDs and expiry.
8.  Cancellation can interrupt every active Coordinator state.
9.  Side-effecting actions are never blindly retried.
10. UNKNOWN tool outcomes are not treated as failures.
11. Critic verification never grants authorisation.
12. External content can never grant authority.
13. CognitiveEngine is completely untouched.
14. Every permission-sensitive execution is audited.
15. All behaviour is covered by tests before routing real traffic.

State machine
-------------
    IDLE ──► PLANNING ──► ACTING ──► APPROVING ──► OBSERVING ──► VERIFYING
      ▲                                                               │
      └───────────────────────── IDLE (done) ◄────────────────────── ┘
                             or ERROR (terminal)

From ANY active state, asyncio.CancelledError transitions immediately to IDLE.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    ProposedAction,
    VerificationResult,
)
from app.agents.retry import (
    RetryPolicy,
    operation_type_from_risk,
    OperationType,
)
from app.core.approval import ApprovalGate, ApprovalRequest
from app.core.audit import AuditEvent, record
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import ToolRegistry

_LOG = logging.getLogger("jasper.coordinator")


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

class CoordinatorState(Enum):
    IDLE      = "IDLE"
    PLANNING  = "PLANNING"
    ACTING    = "ACTING"
    APPROVING = "APPROVING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    ERROR     = "ERROR"


# Legal state transitions — enforced on every step.
_LEGAL_TRANSITIONS: dict[CoordinatorState, frozenset[CoordinatorState]] = {
    CoordinatorState.IDLE:      frozenset({CoordinatorState.PLANNING}),
    CoordinatorState.PLANNING:  frozenset({CoordinatorState.ACTING, CoordinatorState.IDLE, CoordinatorState.ERROR}),
    CoordinatorState.ACTING:    frozenset({CoordinatorState.APPROVING, CoordinatorState.OBSERVING, CoordinatorState.IDLE, CoordinatorState.ERROR}),
    CoordinatorState.APPROVING: frozenset({CoordinatorState.ACTING, CoordinatorState.OBSERVING, CoordinatorState.IDLE, CoordinatorState.ERROR}),
    CoordinatorState.OBSERVING: frozenset({CoordinatorState.VERIFYING, CoordinatorState.ACTING, CoordinatorState.IDLE, CoordinatorState.ERROR}),
    CoordinatorState.VERIFYING: frozenset({CoordinatorState.IDLE, CoordinatorState.ACTING, CoordinatorState.ERROR}),
    CoordinatorState.ERROR:     frozenset({CoordinatorState.IDLE}),
}


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

@dataclass
class CoordinatorBudget:
    """Hard limits enforced per Coordinator invocation.

    Exceeding any limit raises ``BudgetExhaustedError`` and terminates the
    run.  Limits default to conservative values safe for local hardware.
    """
    max_agent_rounds: int = 6       # total agent invocations
    max_tool_calls: int = 10        # total tool executions
    max_approval_requests: int = 5  # total approval gates opened
    timeout_seconds: float = 120.0  # wall-clock hard limit

    # Runtime counters (reset on each run)
    _agent_rounds: int = field(default=0, init=False, repr=False)
    _tool_calls: int = field(default=0, init=False, repr=False)
    _approval_requests: int = field(default=0, init=False, repr=False)

    def reset(self) -> None:
        self._agent_rounds = 0
        self._tool_calls = 0
        self._approval_requests = 0

    def charge_agent_round(self) -> None:
        self._agent_rounds += 1
        if self._agent_rounds > self.max_agent_rounds:
            raise BudgetExhaustedError(
                f"Agent round limit ({self.max_agent_rounds}) exceeded."
            )

    def charge_tool_call(self) -> None:
        self._tool_calls += 1
        if self._tool_calls > self.max_tool_calls:
            raise BudgetExhaustedError(
                f"Tool call limit ({self.max_tool_calls}) exceeded."
            )

    def charge_approval(self) -> None:
        self._approval_requests += 1
        if self._approval_requests > self.max_approval_requests:
            raise BudgetExhaustedError(
                f"Approval request limit ({self.max_approval_requests}) exceeded."
            )


class BudgetExhaustedError(RuntimeError):
    """Raised when any Coordinator budget limit is exceeded."""


# ---------------------------------------------------------------------------
# Approval callback type
# ---------------------------------------------------------------------------

# The Coordinator calls this with an ApprovalRequest so the UI can present it.
# In production this is wired to a Qt Signal; in tests it's a simple callable.
ApprovalNotifier = Callable[[ApprovalRequest], None]


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class Coordinator:
    """State-machine orchestrator for JASPER v0.7 multi-agent workflows.

    The Coordinator is the *only* entity in the v0.7 stack that may execute
    tools.  Agents produce ``AgentResult`` objects containing
    ``ProposedAction`` items; the Coordinator validates, authorises, and
    executes them.

    Parameters
    ----------
    registry:
        Tool registry.  The Coordinator calls ``registry.get(name)`` then
        ``permissions.check_tool(tool)`` immediately before execution.
    permissions:
        ``ScopedPermissionManager`` instance.  Checked immediately before
        every tool execution (invariant 4).
    budget:
        Per-run resource limits.  Defaults to ``CoordinatorBudget()``.
    approval_notifier:
        Callable invoked with an ``ApprovalRequest`` when user approval is
        needed.  Must be thread-safe (e.g. ``loop.call_soon_threadsafe``
        wrapping a Qt signal emit).
    workspace_root:
        Used to canonicalise paths before scope checks (invariant 5).
    """

    def __init__(
        self,
        registry: ToolRegistry,
        permissions: ScopedPermissionManager,
        budget: CoordinatorBudget | None = None,
        approval_notifier: ApprovalNotifier | None = None,
        workspace_root: Path | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._budget = budget or CoordinatorBudget()
        self._approval_notifier = approval_notifier
        self._workspace = (workspace_root or Path.cwd()).resolve()
        self._retry_policy = retry_policy or RetryPolicy()
        self._state = CoordinatorState.IDLE
        self._verification_failures = 0
        self._max_verification_failures = 3
        self.log = logging.getLogger("jasper.coordinator")

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    @property
    def state(self) -> CoordinatorState:
        return self._state

    def _transition(self, new_state: CoordinatorState) -> None:
        allowed = _LEGAL_TRANSITIONS.get(self._state, frozenset())
        if new_state not in allowed:
            raise RuntimeError(
                f"Illegal state transition {self._state.value} → {new_state.value}."
            )
        self.log.debug("state %s → %s", self._state.value, new_state.value)
        self._state = new_state

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        agent_callable: Callable[..., Coroutine[Any, Any, AgentResult]],
        user_text: str,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> str:
        """Run one complete Coordinator cycle.

        Drives the agent callable through the state machine, executing any
        approved ``ProposedAction`` items and surfacing a final text answer.

        Raises ``asyncio.CancelledError`` if cancelled (invariant 8).
        Raises ``BudgetExhaustedError`` if limits are exceeded.
        Returns the final answer string on success.
        """
        if self._state != CoordinatorState.IDLE:
            raise RuntimeError("Coordinator is not in IDLE state; cannot start a new run.")
        self._budget.reset()
        self._verification_failures = 0

        try:
            return await asyncio.wait_for(
                self._run_cycle(agent_callable, user_text, cancel_callback),
                timeout=self._budget.timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._state = CoordinatorState.ERROR
            record(AuditEvent.BUDGET_EXCEEDED, actor="coordinator", detail="wall-clock timeout")
            raise BudgetExhaustedError("Coordinator wall-clock timeout exceeded.")
        except asyncio.CancelledError:
            self.log.info("coordinator cancelled state=%s", self._state.value)
            self._state = CoordinatorState.IDLE
            raise
        except BudgetExhaustedError:
            self._state = CoordinatorState.ERROR
            raise
        except Exception:
            self._state = CoordinatorState.ERROR
            raise
        finally:
            # Always return to IDLE if not already at ERROR
            if self._state not in (CoordinatorState.IDLE, CoordinatorState.ERROR):
                self._state = CoordinatorState.IDLE

    # ------------------------------------------------------------------
    # Internal cycle
    # ------------------------------------------------------------------

    async def _run_cycle(
        self,
        agent_callable: Callable[..., Coroutine[Any, Any, AgentResult]],
        user_text: str,
        cancel_callback: Callable[[], bool] | None,
    ) -> str:
        self._transition(CoordinatorState.PLANNING)
        self._check_cancelled(cancel_callback)

        # Phase 1: Call the agent (planning / acting phase)
        self._budget.charge_agent_round()
        self._transition(CoordinatorState.ACTING)
        self._check_cancelled(cancel_callback)

        # Containment: agent callable must return an AgentResult.
        # Any other return type or exception is surfaced as a controlled failure.
        raw_result = await agent_callable(user_text)
        if not isinstance(raw_result, AgentResult):
            raise TypeError(
                f"Agent callable returned {type(raw_result).__name__!r} "
                f"instead of AgentResult. Agents must return AgentResult only."
            )
        result: AgentResult = raw_result

        # Phase 2: Execute proposed actions
        tool_outputs: list[dict[str, Any]] = []
        for action in result.proposed_actions:
            self._check_cancelled(cancel_callback)
            output = await self._execute_action(action, cancel_callback)
            tool_outputs.append(output)

        # Phase 3: Observe
        self._transition(CoordinatorState.OBSERVING)
        self._check_cancelled(cancel_callback)

        # Phase 4: Verify (if a verification result is present)
        self._transition(CoordinatorState.VERIFYING)
        self._check_cancelled(cancel_callback)

        if result.verification is not None:
            self._handle_verification(result.verification)

        # Done — collect observations + tool outputs as the final answer.
        self._transition(CoordinatorState.IDLE)
        return self._synthesise_answer(result, tool_outputs)

    # ------------------------------------------------------------------
    # Action execution (invariants 1, 2, 3, 4, 5, 9, 14)
    # ------------------------------------------------------------------

    async def _execute_action(
        self,
        action: ProposedAction,
        cancel_callback: Callable[[], bool] | None,
    ) -> dict[str, Any]:
        """Validate, authorise, and execute one ``ProposedAction``.

        Steps
        -----
        1. Validate the ``ProposedAction`` schema (invariant 2).
        2. Canonicalise resource_scope (invariant 5).
        3. Check scope via ``ScopedPermissionManager`` (invariants 3, 4).
        4. If approval required, open a gate and await user response (invariants 6, 7).
        5. Execute the tool (invariant 1 — only Coordinator executes).
        6. Audit the outcome (invariant 14).
        7. Do NOT retry side-effecting actions on failure (invariant 9).
        8. UNKNOWN outcomes are not treated as failures (invariant 10).
        9. Retry READ/MODEL ops up to RetryPolicy.max_retries (Slice 5).
        10. Retries consume budget; backoff is cancellation-aware (Slice 5).
        """
        # Step 1: Schema validation (invariant 2)
        self._validate_proposed_action(action)

        # Derive effective authorization context from trusted Tool metadata
        tool = self._registry.get(action.tool_name)
        try:
            actual_resource = tool.extract_resource(action.arguments)
        except Exception as e:
            record(
                AuditEvent.SCOPE_DENIED,
                actor="coordinator",
                tool_name=action.tool_name,
                operation=action.tool_name,
                risk=tool.risk.value,
                resource="unknown",
                action_id=action.action_id,
                status="DENIED",
                detail=f"Resource extraction failed: {e}"
            )
            raise PermissionError(f"Failed to extract target resource: {e}")

        authoritative_approval = ApprovalRequirement.NEVER if tool.risk.value == "read" else ApprovalRequirement.ALWAYS
        authoritative_scope = PermissionScope(
            risk=tool.risk.value,
            resource_scope=actual_resource,
            operation=tool.name,
            approval_requirement=authoritative_approval,
            lifetime_seconds=None
        )

        action = ProposedAction(
            tool_name=action.tool_name,
            arguments=action.arguments,
            scope=authoritative_scope,
            rationale=action.rationale,
            action_id=action.action_id
        )

        # Step 2: Canonicalise path (invariant 5)
        action = self._canonicalise_action(action, tool)

        # Step 3: Check tool risk policy + scope (invariants 3, 4)
        self._permissions.check_tool(tool)
        self._permissions.check_scope(action)

        # Step 4: Approval gate if needed (invariants 6, 7, 8)
        if action.scope.approval_requirement != ApprovalRequirement.NEVER:
            approved = await self._request_approval(action, cancel_callback)
            if not approved:
                record(
                    AuditEvent.APPROVAL_DENIED,
                    actor="user",
                    tool_name=action.tool_name,
                    action_id=action.action_id,
                    status="DENIED",
                    user_approved=False,
                )
                raise PermissionError(
                    f"User denied approval for action '{action.tool_name}' "
                    f"(action_id={action.action_id})."
                )

        # Determine operation type for retry policy decisions.
        op_type = operation_type_from_risk(action.scope.risk)
        is_side_effecting = op_type in OperationType.side_effecting()

        # Step 5: Execute (only Coordinator touches tools — invariant 1)
        # For side-effecting operations: exactly ONE attempt, never retried.
        # For retriable operations: up to RetryPolicy.max_retries additional attempts.
        attempt = 0
        last_exc: Exception | None = None

        while True:
            self._check_cancelled(cancel_callback)

            # Charge the budget for this execution attempt (includes retries).
            self._budget.charge_tool_call()

            record(
                AuditEvent.TOOL_EXECUTION,
                actor="coordinator",
                tool_name=action.tool_name,
                operation=action.scope.operation,
                risk=action.scope.risk,
                resource=action.scope.resource_scope,
                action_id=action.action_id,
                status="RUNNING",
                attempt=attempt,
                user_approved=action.scope.approval_requirement != ApprovalRequirement.NEVER,
            )

            try:
                raw = tool.handler(**action.arguments)
                if asyncio.iscoroutine(raw):
                    raw = await raw

                # Contain malformed results: attempt JSON serialisation with
                # fallback to str().  This must never raise uncaught.
                try:
                    result_str = json.dumps(raw, ensure_ascii=False, default=str)
                except Exception as ser_exc:
                    self.log.warning(
                        "tool result serialisation failed tool=%s exc=%s; using str() fallback",
                        action.tool_name, ser_exc,
                    )
                    result_str = json.dumps({"_raw": str(raw)}, ensure_ascii=False)

                record(
                    AuditEvent.TOOL_SUCCESS,
                    actor="coordinator",
                    tool_name=action.tool_name,
                    action_id=action.action_id,
                    status="SUCCESS",
                    attempt=attempt,
                )
                return {
                    "action_id": action.action_id,
                    "tool": action.tool_name,
                    "result": result_str,
                    "status": "success",
                }

            except asyncio.CancelledError:
                # Cancellation during execution must never trigger a retry of
                # a side-effecting operation (invariant 9, Slice 5 invariant 7).
                raise

            except Exception as exc:
                last_exc = exc

                if is_side_effecting:
                    # Invariant 9: side-effecting actions NEVER blindly retried.
                    # Invariant 10: UNKNOWN outcome preserved, not converted to FAILED.
                    event = AuditEvent.TOOL_UNKNOWN
                    status = "UNKNOWN"
                    record(
                        event,
                        actor="coordinator",
                        tool_name=action.tool_name,
                        action_id=action.action_id,
                        status=status,
                        detail=str(exc),
                        attempt=attempt,
                    )
                    return {
                        "action_id": action.action_id,
                        "tool": action.tool_name,
                        "error": str(exc),
                        "status": status,
                    }

                # Retriable operation failed.  Check policy.
                if self._retry_policy.should_retry(op_type, attempt=attempt):
                    backoff = self._retry_policy.backoff_seconds(attempt=attempt, op=op_type)
                    record(
                        AuditEvent.TOOL_RETRY,
                        actor="coordinator",
                        tool_name=action.tool_name,
                        action_id=action.action_id,
                        status="RETRYING",
                        detail=str(exc),
                        attempt=attempt,
                    )
                    self.log.warning(
                        "tool failed; will retry tool=%s attempt=%d backoff=%.2fs exc=%s",
                        action.tool_name, attempt, backoff, exc,
                    )
                    if backoff > 0.0:
                        # Cancellation-aware backoff sleep (Slice 5 invariant 7).
                        try:
                            await asyncio.sleep(backoff)
                        except asyncio.CancelledError:
                            raise
                    self._check_cancelled(cancel_callback)
                    attempt += 1
                    continue

                # All retries exhausted.  Surface as FAILED (not UNKNOWN for reads).
                record(
                    AuditEvent.TOOL_RETRY_EXHAUSTED,
                    actor="coordinator",
                    tool_name=action.tool_name,
                    action_id=action.action_id,
                    status="FAILED",
                    detail=str(exc),
                    attempt=attempt,
                )
                self.log.error(
                    "tool failed after %d attempt(s); retries exhausted tool=%s exc=%s",
                    attempt + 1, action.tool_name, exc,
                )
                return {
                    "action_id": action.action_id,
                    "tool": action.tool_name,
                    "error": str(exc),
                    "status": "FAILED",
                }


    # ------------------------------------------------------------------
    # Approval (invariants 6, 7, 8)
    # ------------------------------------------------------------------

    async def _request_approval(
        self,
        action: ProposedAction,
        cancel_callback: Callable[[], bool] | None,
    ) -> bool:
        self._budget.charge_approval()
        gate = ApprovalGate(action)
        req = gate.make_request()

        if self._approval_notifier:
            self._approval_notifier(req)

        self._transition(CoordinatorState.APPROVING)
        try:
            result = await gate.wait()
        except asyncio.CancelledError:
            record(
                AuditEvent.APPROVAL_CANCELLED,
                actor="coordinator",
                tool_name=action.tool_name,
                action_id=action.action_id,
                status="CANCELLED",
            )
            raise

        return result.granted

    # ------------------------------------------------------------------
    # Verification (invariant 11: Critic never grants auth)
    # ------------------------------------------------------------------

    def _handle_verification(self, vr: VerificationResult) -> None:
        """Record verification outcome.  Never grants permission."""
        if vr.passed:
            self._verification_failures = 0
            return
        self._verification_failures += 1
        self.log.warning(
            "verification failed failures=%d/%d feedback=%s",
            self._verification_failures,
            self._max_verification_failures,
            vr.feedback,
        )
        if self._verification_failures >= self._max_verification_failures:
            raise RuntimeError(
                f"Verification failed {self._verification_failures} consecutive times: "
                f"{vr.feedback}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_proposed_action(action: ProposedAction) -> None:
        """Validate independently (invariant 2)."""
        if not action.tool_name or not action.tool_name.strip():
            raise ValueError(f"ProposedAction has empty tool_name (id={action.action_id}).")
        if not isinstance(action.arguments, dict):
            raise TypeError(f"ProposedAction arguments must be dict (id={action.action_id}).")

    def _canonicalise_action(self, action: ProposedAction, tool: Tool) -> ProposedAction:
        """Return a new ProposedAction with the resource_scope canonicalised (invariant 5).

        Only applies to operations on filesystem tools (those with path_argument).
        """
        scope = action.scope
        if not tool.path_argument or tool.path_argument not in action.arguments:
            return action

        raw_path = str(action.arguments[tool.path_argument])

        try:
            # We strictly enforce the same semantics handlers use to avoid TOCTOU mismatches
            canonical = str(Path(raw_path).expanduser().resolve())
        except Exception:
            return action  # permission check will catch it

        # Crucial security fix: overwrite the argument so the handler CANNOT
        # interpret the path differently than we just authorized.
        new_args = dict(action.arguments)
        new_args[tool.path_argument] = canonical

        from app.agents.contracts import PermissionScope
        new_scope = PermissionScope(
            risk=scope.risk,
            resource_scope=canonical,
            # Ensure the operation is prefixed with "file." so ScopedPermissionManager checks it
            operation=f"file.{scope.operation}" if not scope.operation.startswith("file.") else scope.operation,
            approval_requirement=scope.approval_requirement,
            lifetime_seconds=scope.lifetime_seconds,
        )
        return ProposedAction(
            tool_name=action.tool_name,
            arguments=new_args,
            scope=new_scope,
            rationale=action.rationale,
            action_id=action.action_id,
        )

    @staticmethod
    def _check_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
        if cancel_callback and cancel_callback():
            raise asyncio.CancelledError()

    @staticmethod
    def _synthesise_answer(result: AgentResult, tool_outputs: list[dict[str, Any]]) -> str:
        """Combine agent observations and tool outputs into a final text answer."""
        parts: list[str] = []
        if result.observations:
            parts.extend(result.observations)
        for output in tool_outputs:
            if output.get("status") == "success":
                parts.append(f"[Tool {output['tool']}]: {output['result']}")
            elif output.get("status") == "UNKNOWN":
                parts.append(f"[Tool {output['tool']}]: outcome unknown — {output.get('error', '')}")
            else:
                parts.append(f"[Tool {output['tool']}] failed: {output.get('error', 'unknown error')}")
        return "\n".join(parts) if parts else ""
