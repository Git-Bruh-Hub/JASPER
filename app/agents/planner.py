"""app/agents/planner.py -- JASPER v0.7 Slice 6: Planner cognitive role.

The Planner is a *cognitive role*, not a tool executor.  Its job is to
reason about a task and propose a typed set of actions via AgentResult.

Invariants enforced here
-------------------------
* Planner NEVER calls tools directly (invariant 1).
* The planner_callable receives only a PlannerTask -- no registry, no
  permission manager, no approval gate, no budget object.
* Output must be AgentResult; any other return type or exception is
  contained and surfaced as AgentResult.errors.
* Budget is charged before invocation so the multi-agent cycle counts
  Planner rounds against the shared CoordinatorBudget.
* Cancellation is checked both before and after invocation.

This module imports nothing from coordinator.py or multi_agent_coordinator.py
to avoid circular dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from app.agents.contracts import AgentResult, PlannerTask
from app.agents.coordinator import CoordinatorBudget
from app.core.audit import AuditEvent, record

_LOG = logging.getLogger("jasper.planner")


def _check_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback and cancel_callback():
        raise asyncio.CancelledError()


@dataclass
class PlannerAgent:
    """Planner cognitive role for the v0.7 multi-agent Coordinator.

    The Planner reasons about the user task and produces a typed
    AgentResult containing zero or more ProposedAction items.

    It has no access to the tool registry, permission manager, approval
    gate, or any authority-granting object.  The planner_callable it
    wraps receives only a PlannerTask.

    Parameters
    ----------
    agent_id:
        Identifier emitted in audit records.
    """
    agent_id: str = "planner"

    async def invoke(
        self,
        callable_: Callable[[PlannerTask], Coroutine[Any, Any, AgentResult]],
        task: PlannerTask,
        budget: CoordinatorBudget,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> AgentResult:
        """Invoke the planner callable with containment and budget accounting.

        Parameters
        ----------
        callable_:
            Async callable that receives a PlannerTask and must return
            an AgentResult.  Any other return type is contained.
        task:
            The bounded context the Planner receives.
        budget:
            Shared CoordinatorBudget.  charge_agent_round() is called
            before the callable is awaited.
        cancel_callback:
            Optional; if it returns True, asyncio.CancelledError is raised.

        Returns
        -------
        AgentResult
            The planner output, or a contained error result.

        Raises
        ------
        asyncio.CancelledError
            When cancel_callback returns True or the task is cancelled.
        BudgetExhaustedError
            When the agent round limit is exceeded.
        """
        _check_cancelled(cancel_callback)
        budget.charge_agent_round()

        record(
            AuditEvent.PLANNER_INVOKED,
            actor=self.agent_id,
            task_id=task.task_id,
            status="RUNNING",
        )
        _LOG.debug("planner invoked task_id=%s", task.task_id)

        try:
            raw = await callable_(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOG.warning("planner callable raised exc=%s", exc)
            return AgentResult(
                agent_id=self.agent_id,
                errors=[f"Planner invocation failed: {exc}"],
            )

        if not isinstance(raw, AgentResult):
            _LOG.warning(
                "planner callable returned %r instead of AgentResult",
                type(raw).__name__,
            )
            return AgentResult(
                agent_id=self.agent_id,
                errors=[
                    f"Planner returned {type(raw).__name__!r}, not AgentResult. "
                    f"Agents must return AgentResult only."
                ],
            )

        _check_cancelled(cancel_callback)
        record(
            AuditEvent.PLANNER_INVOKED,
            actor=self.agent_id,
            task_id=task.task_id,
            status="SUCCESS",
            detail=f"proposed_actions={len(raw.proposed_actions)}",
        )
        return raw