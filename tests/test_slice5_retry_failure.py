"""tests/test_slice5_retry_failure.py - Slice 5: Retry and Failure Handling.

Covers all required test scenarios for Slice 5:

1.  READ/model failure retries within the configured limit.
2.  READ/model retry uses bounded backoff.
3.  WRITE failure is NOT automatically retried.
4.  EXECUTE failure is NOT automatically retried.
5.  Side-effecting UNKNOWN remains UNKNOWN.
6.  UNKNOWN is not converted to SUCCESS without verification.
7.  DisagreementResolver unit tests (standalone primitive -- Coordinator
    integration is intentionally deferred to the Planner/Executor slice).
8.  Disagreement resolver cannot loop indefinitely (bounded by max_rounds).
9.  Verification failure has bounded recovery.
10. Verification failure eventually reaches a safe terminal state.
11. Malformed tool result is contained.
12. Malformed agent result is contained.
13. Budgets are consumed across retries/recovery.
14. Cancellation during backoff works.
15. Cancellation during recovery works.
16. Retry/failure events are auditable.
17. Existing v0.6 behavior remains unaffected.

Note on items 7 & 8:
    DisagreementResolver is a reusable primitive that lives in
    app/agents/retry.py.  It is tested here as a standalone unit.
    The Coordinator does NOT yet call DisagreementResolver because
    Planner/Executor role separation does not exist in Slice 5.
    These tests verify the resolver's own logic only.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    ProposedAction,
    VerificationResult,
)
from app.agents.coordinator import (
    BudgetExhaustedError,
    Coordinator,
    CoordinatorBudget,
    CoordinatorState,
)
from app.agents.retry import (
    RetryPolicy,
    RetryableOperationError,
    DisagreementError,
    DisagreementResolver,
    OperationType,
)
from app.core.audit import AuditEvent
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry


# We apply autouse=True here because every single test in test_slice5_retry_failure.py
# that involves execution is specifically testing RetryPolicy, DisagreementResolver,
# and tool execution behaviors (such as backoff and execution failure containment)
# AFTER an action has been successfully approved. No tests in this file expect
# the approval gate to intentionally deny execution.
@pytest.fixture(autouse=True)
def mock_request_approval():
    from unittest.mock import AsyncMock, patch
    with patch("app.agents.coordinator.Coordinator._request_approval", new_callable=AsyncMock, return_value=True):
        yield

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

WORKSPACE = Path("C:/workspace").resolve()


def _make_registry_items(*tools) -> ToolRegistry:
    """Build a ToolRegistry. Each item is (name, risk) or (name, risk, handler)."""
    reg = ToolRegistry()
    for item in tools:
        if len(item) == 2:
            name, risk = item
            handler = lambda **_kw: {"ok": True}
        else:
            name, risk, handler = item
        reg.register(Tool(
            name=name,
            description="test",
            risk=risk,
            handler=handler,
            path_argument="path"
        ))
    return reg


def _make_permissions(allowed_risks=None) -> ScopedPermissionManager:
    return ScopedPermissionManager(
        workspace_root=WORKSPACE,
        allowed_risks=allowed_risks or frozenset({Risk.READ}),
    )


def _read_action(tool_name: str = "read_file") -> ProposedAction:
    scope = PermissionScope(
        risk="read",
        resource_scope=str(WORKSPACE / "report.txt"),
        operation="file.read",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    return ProposedAction(
        tool_name=tool_name,
        arguments={"path": str(WORKSPACE / "report.txt")},
        scope=scope,
        rationale="Read for analysis",
    )


def _write_action(tool_name: str = "write_file") -> ProposedAction:
    scope = PermissionScope(
        risk="write",
        resource_scope=str(WORKSPACE / "out.txt"),
        operation="file.write",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    return ProposedAction(
        tool_name=tool_name,
        arguments={"path": str(WORKSPACE / "out.txt"), "content": "data"},
        scope=scope,
        rationale="Write result",
    )


def _execute_action(tool_name: str = "run_script") -> ProposedAction:
    scope = PermissionScope(
        risk="execute",
        resource_scope=str(WORKSPACE / "script.py"),
        operation="file.execute",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    return ProposedAction(
        tool_name=tool_name,
        arguments={"path": str(WORKSPACE / "script.py")},
        scope=scope,
        rationale="Run analysis script",
    )


def _capture_audit_records(caplog) -> list:
    """Parse all JSON-formatted audit records from caplog."""
    records = []
    for rec in caplog.records:
        if rec.name == "jasper.audit":
            try:
                records.append(json.loads(rec.getMessage()))
            except json.JSONDecodeError:
                pass
    return records


# ===========================================================================
# 1 & 2. RetryPolicy unit tests: READ retries, bounded backoff, WRITE/EXECUTE never
# ===========================================================================

class TestRetryPolicy:
    """Unit tests for RetryPolicy logic -- no Coordinator involved."""

    def test_read_op_allows_retry(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(OperationType.READ, attempt=0) is True
        assert policy.should_retry(OperationType.READ, attempt=2) is True

    def test_read_op_stops_at_max_retries(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(OperationType.READ, attempt=3) is False

    def test_model_op_allows_retry(self):
        policy = RetryPolicy(max_retries=2)
        assert policy.should_retry(OperationType.MODEL, attempt=1) is True
        assert policy.should_retry(OperationType.MODEL, attempt=2) is False

    # 3. WRITE failure is NOT automatically retried
    def test_write_op_never_retried(self):
        policy = RetryPolicy(max_retries=10)
        assert policy.should_retry(OperationType.WRITE, attempt=0) is False
        assert policy.should_retry(OperationType.WRITE, attempt=5) is False

    # 4. EXECUTE failure is NOT automatically retried
    def test_execute_op_never_retried(self):
        policy = RetryPolicy(max_retries=10)
        assert policy.should_retry(OperationType.EXECUTE, attempt=0) is False

    def test_destructive_op_never_retried(self):
        policy = RetryPolicy(max_retries=10)
        assert policy.should_retry(OperationType.DESTRUCTIVE, attempt=0) is False

    # 2. READ/model retry uses bounded backoff
    def test_backoff_increases_with_attempt(self):
        policy = RetryPolicy(max_retries=3, base_backoff=0.1, max_backoff=2.0)
        b0 = policy.backoff_seconds(attempt=0)
        b1 = policy.backoff_seconds(attempt=1)
        b2 = policy.backoff_seconds(attempt=2)
        assert b0 < b1 <= b2

    def test_backoff_capped_at_max(self):
        policy = RetryPolicy(max_retries=10, base_backoff=1.0, max_backoff=5.0)
        for attempt in range(10):
            assert policy.backoff_seconds(attempt) <= 5.0

    def test_backoff_is_zero_for_non_retriable_ops(self):
        policy = RetryPolicy(max_retries=3, base_backoff=1.0)
        assert policy.backoff_seconds(attempt=0, op=OperationType.WRITE) == 0.0


# ===========================================================================
# 1 (integration). Coordinator: READ retries on failure
# ===========================================================================

@pytest.mark.asyncio
async def test_read_retries_on_transient_failure():
    """READ tool is retried up to max_retries on transient exception."""
    call_count = 0

    def _flaky_read(**kw):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OSError("transient IO error")
        return {"content": "hello"}

    reg = _make_registry_items(("read_file", Risk.READ, _flaky_read))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=10),
        retry_policy=RetryPolicy(max_retries=3, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    answer = await coord.run(_agent, "test")
    assert call_count == 3  # failed twice, succeeded on third
    assert answer  # some result returned


@pytest.mark.asyncio
async def test_read_fails_after_exhausting_retries():
    """READ tool that always fails produces FAILED after all retries exhausted."""
    call_count = 0

    def _always_fail(**kw):
        nonlocal call_count
        call_count += 1
        raise FileNotFoundError("missing")

    reg = _make_registry_items(("read_file", Risk.READ, _always_fail))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=10),
        retry_policy=RetryPolicy(max_retries=2, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    answer = await coord.run(_agent, "test")
    assert call_count == 3  # 1 initial + 2 retries
    assert "failed" in answer.lower() or "FAILED" in answer


# ===========================================================================
# 3. WRITE failure is NOT automatically retried
# ===========================================================================

@pytest.mark.asyncio
async def test_write_failure_not_retried():
    """WRITE tool exception must NOT trigger any retry -- called exactly once."""
    call_count = 0

    def _write_fail(**kw):
        nonlocal call_count
        call_count += 1
        raise OSError("disk full")

    reg = _make_registry_items(("write_file", Risk.WRITE, _write_fail))
    pm = _make_permissions(frozenset({Risk.READ, Risk.WRITE}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=10),
        retry_policy=RetryPolicy(max_retries=5, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="executor", proposed_actions=[_write_action()])

    answer = await coord.run(_agent, "test")
    assert call_count == 1  # exactly once -- never retried
    assert "UNKNOWN" in answer or "unknown" in answer.lower()


# ===========================================================================
# 4. EXECUTE failure is NOT automatically retried
# ===========================================================================

@pytest.mark.asyncio
async def test_execute_failure_not_retried():
    """EXECUTE tool exception must NOT trigger any retry -- called exactly once."""
    call_count = 0

    def _exec_fail(**kw):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("script crashed")

    reg = _make_registry_items(("run_script", Risk.EXECUTE, _exec_fail))
    pm = _make_permissions(frozenset({Risk.READ, Risk.EXECUTE}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=10),
        retry_policy=RetryPolicy(max_retries=5, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="executor", proposed_actions=[_execute_action()])

    answer = await coord.run(_agent, "test")
    assert call_count == 1
    assert "UNKNOWN" in answer or "unknown" in answer.lower()


# ===========================================================================
# 5. Side-effecting UNKNOWN remains UNKNOWN
# ===========================================================================

@pytest.mark.asyncio
async def test_write_unknown_not_converted_to_failed():
    """WRITE exception must produce UNKNOWN status, not FAILED."""

    def _write_fail(**kw):
        raise OSError("network timeout mid-write")

    reg = _make_registry_items(("write_file", Risk.WRITE, _write_fail))
    pm = _make_permissions(frozenset({Risk.READ, Risk.WRITE}))
    coord = Coordinator(reg, pm, retry_policy=RetryPolicy(max_retries=3, base_backoff=0.0))

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="executor", proposed_actions=[_write_action()])

    answer = await coord.run(_agent, "test")
    assert "UNKNOWN" in answer or "unknown" in answer.lower()
    assert "FAILED" not in answer and "failed" not in answer.lower()


# ===========================================================================
# 6. UNKNOWN is not converted to SUCCESS without verification
# ===========================================================================

@pytest.mark.asyncio
async def test_unknown_outcome_not_treated_as_success():
    """WRITE failure with UNKNOWN outcome is surfaced to caller, not hidden as success."""

    def _write_maybe(**kw):
        raise OSError("connection reset")

    reg = _make_registry_items(("write_file", Risk.WRITE, _write_maybe))
    pm = _make_permissions(frozenset({Risk.READ, Risk.WRITE}))
    coord = Coordinator(reg, pm, retry_policy=RetryPolicy(max_retries=0, base_backoff=0.0))

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="executor", proposed_actions=[_write_action()])

    answer = await coord.run(_agent, "test")
    assert "UNKNOWN" in answer or "unknown" in answer.lower()
    assert "success" not in answer.lower()


# ===========================================================================
# 7 & 8. DisagreementResolver unit tests (standalone primitive)
#
# These tests verify the resolver's own logic -- bounds, detection, and error
# raising.  The Coordinator does NOT call DisagreementResolver in Slice 5;
# integration is deferred until the Planner/Executor delegation layer exists
# in a later v0.7 slice.
# ===========================================================================

class TestDisagreementResolver:
    def test_resolver_detects_disagreement(self):
        resolver = DisagreementResolver(max_rounds=3)
        planner_actions = [_read_action("read_file")]
        executor_actions = [_write_action("write_file")]
        assert resolver.is_disagreement(planner_actions, executor_actions) is True

    def test_resolver_no_disagreement_when_same_tool_names(self):
        resolver = DisagreementResolver(max_rounds=3)
        actions = [_read_action("read_file")]
        assert resolver.is_disagreement(actions, actions) is False

    def test_resolver_no_disagreement_when_executor_empty(self):
        """Executor proposing no actions is not a disagreement."""
        resolver = DisagreementResolver(max_rounds=3)
        planned = [_read_action("read_file")]
        assert resolver.is_disagreement(planned, []) is False

    # 8. Disagreement cannot loop indefinitely
    def test_resolver_limit_reached_after_max_rounds(self):
        resolver = DisagreementResolver(max_rounds=2)
        resolver.record_round()
        resolver.record_round()
        assert resolver.is_limit_reached() is True

    def test_resolver_raises_error_when_limit_reached(self):
        resolver = DisagreementResolver(max_rounds=1)
        resolver.record_round()
        with pytest.raises(DisagreementError, match="limit"):
            resolver.assert_not_limit_reached()

    def test_resolver_not_reached_before_limit(self):
        resolver = DisagreementResolver(max_rounds=3)
        resolver.record_round()
        assert resolver.is_limit_reached() is False


# ===========================================================================
# 9. Verification failure has bounded recovery
# ===========================================================================

@pytest.mark.asyncio
async def test_verification_failure_bounded_recovery():
    """Coordinator halts after max_verification_failures -- no infinite loop."""
    reg = _make_registry_items()
    pm = _make_permissions()
    coord = Coordinator(reg, pm)
    # Set limit to 1: a single verification failure must halt the run.
    coord._max_verification_failures = 1

    call_count = 0

    async def _agent(user_text: str) -> AgentResult:
        nonlocal call_count
        call_count += 1
        return AgentResult(
            agent_id="critic",
            verification=VerificationResult(
                passed=False,
                feedback="Verification always fails",
                retry_recommended=True,
            ),
        )

    with pytest.raises(RuntimeError, match="Verification failed"):
        await coord.run(_agent, "test")

    # The agent was called exactly once -- no infinite loop.
    assert call_count == 1


# ===========================================================================
# 10. Verification failure eventually reaches a safe terminal state
# ===========================================================================

@pytest.mark.asyncio
async def test_verification_failure_terminal_state():
    """After bounded verification failures, Coordinator must be in ERROR state."""
    reg = _make_registry_items()
    pm = _make_permissions()
    coord = Coordinator(reg, pm)
    coord._max_verification_failures = 1

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(
            agent_id="critic",
            verification=VerificationResult(passed=False, feedback="Bad output"),
        )

    with pytest.raises(RuntimeError):
        await coord.run(_agent, "test")

    assert coord.state == CoordinatorState.ERROR


# ===========================================================================
# 11. Malformed tool result is contained
# ===========================================================================

@pytest.mark.asyncio
async def test_malformed_tool_result_contained():
    """A tool returning an un-serialisable object must not crash the Coordinator."""

    class _Unserializable:
        def __repr__(self):
            return "<Unserializable>"

    def _bad_tool(**kw):
        return _Unserializable()

    reg = _make_registry_items(("read_file", Risk.READ, _bad_tool))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(
        reg, pm,
        retry_policy=RetryPolicy(max_retries=0, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    # Must not raise; malformed result must be contained
    answer = await coord.run(_agent, "test")
    assert isinstance(answer, str)


@pytest.mark.asyncio
async def test_tool_result_non_serialisable_falls_back_gracefully():
    """If JSON serialisation of result falls back to str(), the run completes."""

    def _odd_return(**kw):
        class _Circ:
            pass
        return _Circ()  # not natively JSON-serialisable, but default=str handles it

    reg = _make_registry_items(("read_file", Risk.READ, _odd_return))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(reg, pm, retry_policy=RetryPolicy(max_retries=0, base_backoff=0.0))

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    answer = await coord.run(_agent, "test")
    assert isinstance(answer, str)


# ===========================================================================
# 12. Malformed agent result is contained
# ===========================================================================

@pytest.mark.asyncio
async def test_malformed_agent_raises_is_surfaced_safely():
    """Agent callable that raises must surface error; Coordinator stays safe."""
    reg = _make_registry_items()
    pm = _make_permissions()
    coord = Coordinator(reg, pm)

    async def _bad_agent(user_text: str) -> AgentResult:
        raise ValueError("agent internal error")

    with pytest.raises((RuntimeError, ValueError)):
        await coord.run(_bad_agent, "test")

    assert coord.state in (CoordinatorState.ERROR, CoordinatorState.IDLE)


@pytest.mark.asyncio
async def test_agent_returning_wrong_type_is_contained():
    """Agent callable returning non-AgentResult is contained as a controlled failure."""
    reg = _make_registry_items()
    pm = _make_permissions()
    coord = Coordinator(reg, pm)

    async def _wrong_type_agent(user_text: str):
        return "I am not an AgentResult"

    with pytest.raises((TypeError, AttributeError, RuntimeError)):
        await coord.run(_wrong_type_agent, "test")

    assert coord.state in (CoordinatorState.ERROR, CoordinatorState.IDLE)


# ===========================================================================
# 13. Budgets are consumed across retries/recovery
# ===========================================================================

@pytest.mark.asyncio
async def test_budget_consumed_across_retries():
    """Retries consume the tool call budget -- recovery cannot reset the budget."""
    call_count = 0

    def _flaky_read(**kw):
        nonlocal call_count
        call_count += 1
        raise IOError("transient")

    reg = _make_registry_items(("read_file", Risk.READ, _flaky_read))
    pm = _make_permissions(frozenset({Risk.READ}))

    # Budget allows only 2 tool calls total
    budget = CoordinatorBudget(max_tool_calls=2)
    coord = Coordinator(
        reg, pm,
        budget=budget,
        retry_policy=RetryPolicy(max_retries=5, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    with pytest.raises(BudgetExhaustedError, match="Tool call limit"):
        await coord.run(_agent, "test")

    assert call_count <= 3  # budget kicks in before exhausting retry policy


@pytest.mark.asyncio
async def test_budget_not_reset_during_recovery():
    """Budget counters do NOT reset between successive run() calls.

    Each call to run() resets the budget (by design -- budgets are per-run).
    However, within a single run, budget is not reset during verification.
    This test verifies the budget limit is hit when the agent round limit is low.
    """
    reg = _make_registry_items()
    pm = _make_permissions()
    # max_agent_rounds=1: the first call to charge_agent_round succeeds, the
    # second (if any retry loop existed) would fail. Since there's no retry loop
    # at the agent level, this just confirms the budget is enforced.
    budget = CoordinatorBudget(max_agent_rounds=1)
    coord = Coordinator(reg, pm, budget=budget)
    # With max=1, the first (and only) verification failure raises immediately.
    coord._max_verification_failures = 1

    round_count = 0

    async def _agent(user_text: str) -> AgentResult:
        nonlocal round_count
        round_count += 1
        return AgentResult(
            agent_id="critic",
            verification=VerificationResult(passed=False, feedback="bad"),
        )

    with pytest.raises(RuntimeError):
        await coord.run(_agent, "test")

    # Budget must have been respected -- only 1 agent round was used
    assert round_count == 1


# ===========================================================================
# 14. Cancellation during backoff works
# ===========================================================================

@pytest.mark.asyncio
async def test_cancellation_during_retry_backoff():
    """CancelledError during backoff sleep must propagate correctly."""
    call_count = 0

    def _always_fail(**kw):
        nonlocal call_count
        call_count += 1
        raise IOError("fail")

    reg = _make_registry_items(("read_file", Risk.READ, _always_fail))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=10),
        retry_policy=RetryPolicy(max_retries=10, base_backoff=5.0),  # long backoff
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    task = asyncio.create_task(coord.run(_agent, "test"))
    await asyncio.sleep(0.05)  # let it start and enter backoff
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert coord.state == CoordinatorState.IDLE  # cleaned up after cancel


@pytest.mark.asyncio
async def test_cancellation_via_callback_during_retry():
    """cancel_callback returning True during retry backoff halts execution."""
    call_count = 0
    should_cancel = False

    def _flaky(**kw):
        nonlocal call_count, should_cancel
        call_count += 1
        should_cancel = True  # signal cancel after first failure
        raise IOError("fail")

    reg = _make_registry_items(("read_file", Risk.READ, _flaky))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=10),
        retry_policy=RetryPolicy(max_retries=5, base_backoff=0.01),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="test", proposed_actions=[_read_action()])

    with pytest.raises(asyncio.CancelledError):
        await coord.run(_agent, "test", cancel_callback=lambda: should_cancel)

    assert call_count == 1  # only ran once before cancel was detected


# ===========================================================================
# 15. Cancellation during recovery works
# ===========================================================================

@pytest.mark.asyncio
async def test_cancellation_during_verification_recovery():
    """CancelledError during verification recovery propagates correctly."""
    reg = _make_registry_items()
    pm = _make_permissions()
    coord = Coordinator(reg, pm)
    coord._max_verification_failures = 10

    async def _slow_agent(user_text: str) -> AgentResult:
        await asyncio.sleep(10)
        return AgentResult(
            agent_id="critic",
            verification=VerificationResult(passed=False, feedback="bad"),
        )

    task = asyncio.create_task(coord.run(_slow_agent, "test"))
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert coord.state == CoordinatorState.IDLE


# ===========================================================================
# 16. Retry/failure events are auditable
# ===========================================================================

@pytest.mark.asyncio
async def test_retry_events_are_audited(caplog):
    """Retry attempts produce structured audit events with required fields."""
    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        call_count = 0

        def _flaky_read(**kw):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise IOError("transient")
            return {"content": "ok"}

        reg = _make_registry_items(("read_file", Risk.READ, _flaky_read))
        pm = _make_permissions(frozenset({Risk.READ}))
        coord = Coordinator(
            reg, pm,
            budget=CoordinatorBudget(max_tool_calls=10),
            retry_policy=RetryPolicy(max_retries=3, base_backoff=0.0),
        )

        async def _agent(user_text: str) -> AgentResult:
            return AgentResult(agent_id="test", proposed_actions=[_read_action()])

        await coord.run(_agent, "test")

    audit_records = _capture_audit_records(caplog)
    retry_events = [r for r in audit_records if "retry" in r.get("event", "").lower()]

    assert len(retry_events) >= 1, (
        f"Expected retry events, got events: {[r['event'] for r in audit_records]}"
    )
    for evt in retry_events:
        assert "event" in evt
        assert "status" in evt


@pytest.mark.asyncio
async def test_write_unknown_outcome_is_audited(caplog):
    """WRITE failure producing UNKNOWN outcome must be audited with action_id."""
    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        def _write_fail(**kw):
            raise OSError("disk full")

        reg = _make_registry_items(("write_file", Risk.WRITE, _write_fail))
        pm = _make_permissions(frozenset({Risk.READ, Risk.WRITE}))
        coord = Coordinator(reg, pm, retry_policy=RetryPolicy(max_retries=0, base_backoff=0.0))

        action = _write_action()

        async def _agent(user_text: str) -> AgentResult:
            return AgentResult(agent_id="executor", proposed_actions=[action])

        await coord.run(_agent, "test")

    audit_records = _capture_audit_records(caplog)
    unknown_events = [r for r in audit_records if r.get("status") == "UNKNOWN"]
    assert len(unknown_events) >= 1

    evt = unknown_events[0]
    assert evt.get("tool_name") == "write_file"
    assert evt.get("action_id") != ""


@pytest.mark.asyncio
async def test_audit_records_have_required_fields(caplog):
    """All audit records from retry/failure paths have the mandatory fields."""
    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        def _always_fail(**kw):
            raise IOError("transient")

        reg = _make_registry_items(("read_file", Risk.READ, _always_fail))
        pm = _make_permissions(frozenset({Risk.READ}))
        coord = Coordinator(
            reg, pm,
            budget=CoordinatorBudget(max_tool_calls=5),
            retry_policy=RetryPolicy(max_retries=2, base_backoff=0.0),
        )

        async def _agent(user_text: str) -> AgentResult:
            return AgentResult(agent_id="test", proposed_actions=[_read_action()])

        await coord.run(_agent, "test")

    audit_records = _capture_audit_records(caplog)
    assert len(audit_records) > 0

    required_fields = {"timestamp", "event", "actor", "status"}
    for rec in audit_records:
        missing = required_fields - set(rec.keys())
        assert not missing, f"Audit record missing fields {missing}: {rec}"


# ===========================================================================
# 17. Existing v0.6 behavior remains unaffected
# ===========================================================================

class TestV06Unaffected:
    """Verify that v0.6 CognitiveEngine is completely untouched."""

    def test_cognitive_engine_importable(self):
        from app.agents.engine import CognitiveEngine
        assert CognitiveEngine is not None

    def test_cognitive_engine_has_no_coordinator_dependency(self):
        """CognitiveEngine must not depend on Coordinator or v0.7 components."""
        import inspect
        from app.agents import engine
        source = inspect.getsource(engine)
        assert "Coordinator" not in source
        assert "ProposedAction" not in source
        assert "AgentResult" not in source

    def test_cognitive_engine_router_importable(self):
        from app.agents.router import CognitiveMode
        assert CognitiveMode is not None

    @pytest.mark.asyncio
    async def test_coordinator_with_default_retry_policy_works(self):
        """Coordinator with default RetryPolicy behaves correctly for simple cases."""
        reg = _make_registry_items(("read_file", Risk.READ))
        pm = _make_permissions(frozenset({Risk.READ}))
        coord = Coordinator(reg, pm)  # default retry policy

        async def _agent(user_text: str) -> AgentResult:
            return AgentResult(
                agent_id="test",
                observations=["done"],
            )

        answer = await coord.run(_agent, "hello")
        assert "done" in answer


# ===========================================================================
# Integration: End-to-end scenarios
# ===========================================================================

@pytest.mark.asyncio
async def test_end_to_end_retry_with_eventual_success():
    """Full integration: READ fails twice, succeeds on third attempt."""
    call_count = 0

    def _read_flaky(**kw):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise IOError("disk busy")
        return {"content": "final result"}

    reg = _make_registry_items(("read_file", Risk.READ, _read_flaky))
    pm = _make_permissions(frozenset({Risk.READ}))
    coord = Coordinator(
        reg, pm,
        budget=CoordinatorBudget(max_tool_calls=5),
        retry_policy=RetryPolicy(max_retries=3, base_backoff=0.0),
    )

    async def _agent(user_text: str) -> AgentResult:
        return AgentResult(agent_id="analyst", proposed_actions=[_read_action()])

    answer = await coord.run(_agent, "analyse")
    assert call_count == 3
    assert answer  # non-empty answer


@pytest.mark.asyncio
async def test_end_to_end_write_unknown_no_retry(caplog):
    """Full integration: WRITE fails -> UNKNOWN -> no retry -> audited."""
    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        call_count = 0

        def _write_fail(**kw):
            nonlocal call_count
            call_count += 1
            raise OSError("network reset")

        reg = _make_registry_items(("write_file", Risk.WRITE, _write_fail))
        pm = _make_permissions(frozenset({Risk.READ, Risk.WRITE}))
        coord = Coordinator(
            reg, pm,
            retry_policy=RetryPolicy(max_retries=5, base_backoff=0.0),
        )

        async def _agent(user_text: str) -> AgentResult:
            return AgentResult(agent_id="executor", proposed_actions=[_write_action()])

        answer = await coord.run(_agent, "write data")

    assert call_count == 1  # no retry
    assert "UNKNOWN" in answer or "unknown" in answer.lower()

    audit_records = _capture_audit_records(caplog)
    unknown_audit = [r for r in audit_records if r.get("status") == "UNKNOWN"]
    assert unknown_audit
