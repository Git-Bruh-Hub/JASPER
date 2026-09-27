"""app/agents/executor.py -- JASPER v0.7 Slice 6: Executor cognitive role.

The Executor is a *cognitive role*, not a tool executor.  It receives the
Planner handoff and reasons about how the requested actions should be
carried out, producing a revised AgentResult whose proposed_actions will
be submitted to the Coordinator for authorised execution.

Invariants enforced here
-------------------------
* Executor NEVER calls tools directly (invariant 1).
* The executor_callable receives only (PlannerResult, DisagreementFeedback | None).
  It has NO access to the registry, permission manager, approval gate, or budget.
* Output must be AgentResult; any other return type or exception is
  contained and surfaced as AgentResult.errors.
* Budget is charged before invocation.
* Cancellation is checked both before and after invocation.
* When DisagreementFeedback is provided the Executor receives explicit
  typed context about why its previous output was rejected.

This module imports nothing from multi_agent_coordinator.py to avoid
circular dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from app.agents.contracts import AgentResult, DisagreementFeedback, PlannerResult
from app.agents.coordinator import CoordinatorBudget
from app.core.audit import AuditEvent, record

_LOG = logging.getLogger("jasper.executor")


def _check_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback and cancel_callback():
        raise asyncio.CancelledError()


@dataclass
class ExecutorAgent:
    """Executor cognitive role for the v0.7 multi-agent Coordinator.

    The Executor receives the PlannerResult handoff and produces a typed
    AgentResult whose proposed_actions must still pass through the full
    Coordinator permission/approval/tool pipeline.

    The executor_callable signature is::

        async def executor(
            handoff: PlannerResult,
            feedback: DisagreementFeedback | None,
        ) -> AgentResult:

    ``feedback`` is None on the first invocation; on a disagreement retry
    it carries explicit typed information about which tools were unexpected.

    Parameters
    ----------
    agent_id:
        Identifier emitted in audit records.
    """
    agent_id: str = "executor"

    async def invoke(
        self,
        callable_: Callable[
            [PlannerResult, DisagreementFeedback | None],
            Coroutine[Any, Any, AgentResult],
        ],
        handoff: PlannerResult,
        budget: CoordinatorBudget,
        feedback: DisagreementFeedback | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> AgentResult:
        """Invoke the executor callable with containment and budget accounting.

        Parameters
        ----------
        callable_:
            Async callable that receives (PlannerResult, DisagreementFeedback | None)
            and must return an AgentResult.
        handoff:
            The typed Planner handoff.  Executor callable receives this as
            its sole authority-free context.
        budget:
            Shared CoordinatorBudget.  charge_agent_round() is called
            before the callable is awaited.
        feedback:
            None on the first invocation.  On a disagreement retry, this
            carries explicit typed context about the rejection reason.
        cancel_callback:
            Optional; if it returns True, asyncio.CancelledError is raised.

        Returns
        -------
        AgentResult
            The executor output, or a contained error result.

        Raises
        ------
        asyncio.CancelledError
            When cancel_callback returns True or the task is cancelled.
        BudgetExhaustedError
            When the agent round limit is exceeded.
        """
        _check_cancelled(cancel_callback)
        budget.charge_agent_round()

        round_num = feedback.round_number if feedback else 0
        record(
            AuditEvent.EXECUTOR_INVOKED,
            actor=self.agent_id,
            task_id=handoff.task_id,
            status="RUNNING",
            detail=f"disagreement_round={round_num}",
        )
        _LOG.debug(
            "executor invoked task_id=%s disagreement_round=%d",
            handoff.task_id, round_num,
        )

        try:
            raw = await callable_(handoff, feedback)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("executor callable raised exc=%s", exc)
            return AgentResult(
                agent_id=self.agent_id,
                errors=[f"Executor invocation failed: {exc}"],
            )

        if not isinstance(raw, AgentResult):
            _LOG.warning(
                "executor callable returned %r instead of AgentResult",
                type(raw).__name__,
            )
            return AgentResult(
                agent_id=self.agent_id,
                errors=[
                    f"Executor returned {type(raw).__name__!r}, not AgentResult. "
                    f"Agents must return AgentResult only."
                ],
            )

        _check_cancelled(cancel_callback)
        record(
            AuditEvent.EXECUTOR_INVOKED,
            actor=self.agent_id,
            task_id=handoff.task_id,
            status="SUCCESS",
            detail=f"proposed_actions={len(raw.proposed_actions)}",
        )
        return raw