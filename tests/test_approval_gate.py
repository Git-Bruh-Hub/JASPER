"""Tests for Slice 3: app/core/approval.py.

Covers:
- Gate creates unique IDs (invariant 7)
- User can grant/deny asynchronously without blocking a thread
- Gate expires after timeout (invariant 7)
- Task cancellation interrupts the waiting gate (invariant 8)
- resolve() called before await() is safe (no crash)
- resolve() is idempotent (double-resolve ignored)
- Audit records emitted for grant, deny, expire, cancel
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from app.agents.contracts import ApprovalRequirement, PermissionScope, ProposedAction
from app.core.approval import ApprovalGate, DEFAULT_GATE_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_action(tool_name: str = "write_file") -> ProposedAction:
    scope = PermissionScope(
        risk="write",
        resource_scope="C:/workspace/out.txt",
        operation="file.write",
        approval_requirement=ApprovalRequirement.ALWAYS,
    )
    return ProposedAction(
        tool_name=tool_name,
        arguments={"path": "C:/workspace/out.txt"},
        scope=scope,
        rationale="Need to write result.",
    )


# ---------------------------------------------------------------------------
# Gate identity
# ---------------------------------------------------------------------------

class TestApprovalGateIdentity:
    def test_unique_gate_ids(self):
        a1 = ApprovalGate(_make_action())
        a2 = ApprovalGate(_make_action())
        assert a1.gate_id != a2.gate_id

    def test_make_request_carries_gate_id(self):
        gate = ApprovalGate(_make_action())
        req = gate.make_request()
        assert req.gate_id == gate.gate_id

    def test_make_request_has_expiry(self):
        gate = ApprovalGate(_make_action(), timeout=60)
        req = gate.make_request()
        from datetime import timezone
        assert req.expires_at.tzinfo is not None  # UTC-aware

    def test_default_timeout_is_reasonable(self):
        assert DEFAULT_GATE_TIMEOUT_SECONDS > 0


# ---------------------------------------------------------------------------
# Async approval — granted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_resolves_granted():
    gate = ApprovalGate(_make_action())
    gate.make_request()

    async def _approve_after_tick():
        await asyncio.sleep(0)
        gate.resolve(granted=True)

    asyncio.create_task(_approve_after_tick())
    result = await gate.wait()

    assert result.granted
    assert not result.cancelled
    assert not result.expired


# ---------------------------------------------------------------------------
# Async approval — denied
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_resolves_denied():
    gate = ApprovalGate(_make_action())
    gate.make_request()

    async def _deny_after_tick():
        await asyncio.sleep(0)
        gate.resolve(granted=False)

    asyncio.create_task(_deny_after_tick())
    result = await gate.wait()

    assert not result.granted
    assert not result.expired
    assert not result.cancelled


# ---------------------------------------------------------------------------
# Timeout — gate auto-expires (invariant 7)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_expires_after_timeout():
    gate = ApprovalGate(_make_action(), timeout=0.05)  # 50 ms
    gate.make_request()
    result = await gate.wait()

    assert not result.granted
    assert result.expired


# ---------------------------------------------------------------------------
# Cancellation interrupts waiting gate (invariant 8)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_interrupted_by_task_cancellation():
    gate = ApprovalGate(_make_action(), timeout=10)
    gate.make_request()

    async def _long_wait():
        return await gate.wait()

    task = asyncio.create_task(_long_wait())
    await asyncio.sleep(0)  # let task start
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# resolve() safety edges
# ---------------------------------------------------------------------------

def test_resolve_before_await_does_not_crash():
    """Calling resolve() without ever calling wait() must not raise."""
    gate = ApprovalGate(_make_action())
    gate.make_request()
    gate.resolve(granted=True)  # _future is None — should be safe


@pytest.mark.asyncio
async def test_double_resolve_is_idempotent():
    """Second resolve() after gate is already resolved must not crash."""
    gate = ApprovalGate(_make_action())
    gate.make_request()

    async def _approve():
        await asyncio.sleep(0)
        gate.resolve(granted=True)
        gate.resolve(granted=False)  # second call — must be ignored

    asyncio.create_task(_approve())
    result = await gate.wait()
    assert result.granted  # first resolve wins


# ---------------------------------------------------------------------------
# Audit events emitted (invariant 14)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_granted_emits_audit_event(caplog):
    gate = ApprovalGate(_make_action())
    gate.make_request()

    async def _approve():
        await asyncio.sleep(0)
        gate.resolve(granted=True)

    asyncio.create_task(_approve())
    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        await gate.wait()

    records = [json.loads(r.message) for r in caplog.records]
    events = {r["event"] for r in records}
    assert "approval_granted" in events


@pytest.mark.asyncio
async def test_approval_denied_emits_audit_event(caplog):
    gate = ApprovalGate(_make_action())
    gate.make_request()

    async def _deny():
        await asyncio.sleep(0)
        gate.resolve(granted=False)

    asyncio.create_task(_deny())
    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        await gate.wait()

    records = [json.loads(r.message) for r in caplog.records]
    events = {r["event"] for r in records}
    assert "approval_denied" in events


@pytest.mark.asyncio
async def test_approval_expired_emits_audit_event(caplog):
    gate = ApprovalGate(_make_action(), timeout=0.05)
    gate.make_request()

    with caplog.at_level(logging.INFO, logger="jasper.audit"):
        await gate.wait()

    audit_records = [
        json.loads(r.message)
        for r in caplog.records
        if r.name == "jasper.audit"
    ]
    events = {r["event"] for r in audit_records}
    assert "approval_expired" in events
