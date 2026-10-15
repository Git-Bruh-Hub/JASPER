"""app/agents/multi_agent_coordinator.py -- JASPER v0.7 Slice 6: Planner/Executor delegation.

MultiAgentCoordinator extends the existing Coordinator with a multi-agent
orchestration layer.  It does NOT modify the base Coordinator in any way;
all inherited state-machine transitions, permission checks, approval gates,
retry policy, budget enforcement, and cancellation handling are preserved.

Architecture (Slice 6)
----------------------
    run_multi_agent(planner_callable, executor_callable, user_text)
         |
         +-- budget.reset()
         |
         +-- PLANNING state
         |
         +-- PlannerAgent.invoke(planner_callable, PlannerTask)
         |       -> AgentResult  [budget: charge_agent_round x1]
         |
         +-- Build PlannerResult  [typed, task_id correlated]
         |
         +-- DisagreementResolver(max_rounds=max_disagreement_rounds)
         |
         +-- ACTING state
         |
         +-- [EXECUTOR LOOP -- bounded by DisagreementResolver]
         |    ExecutorAgent.invoke(executor_callable, PlannerResult, feedback)
         |         -> AgentResult  [budget: charge_agent_round x1 per attempt]
         |    |
         |    +-- DisagreementResolver.is_disagreement(planner_actions, executor_actions)?
         |    |       YES:
         |    |         record(DISAGREEMENT_DETECTED, ...)
         |    |         resolver.record_round()
         |    |         resolver.assert_not_limit_reached()
         |    |              -> raises DisagreementError if limit reached
         |    |         Build DisagreementFeedback(round, unexpected_tools, planner_tools)
         |    |         continue EXECUTOR LOOP with this feedback
         |    |       NO:
         |    |         break -- proceed to tool execution
         |    |
         +-- For each ProposedAction in executor_result.proposed_actions:
         |       _execute_action(action, cancel_callback)  [inherited]
         |       [ScopedPermissionManager -> ApprovalGate -> tool.handler -> audit]
         |
         +-- OBSERVING -> VERIFYING  [inherited state machine]
         |
         +-- IDLE -> return answer

    On DisagreementError:
         record(DISAGREEMENT_HALTED, ...)
         _state = ERROR
         raise DisagreementError

Security invariants (all inherited from Coordinator)
-----------------------------------------------------
1.  Neither Planner nor Executor may call tools directly.
2.  ProposedActions from the Executor are validated before execution.
3.  ScopedPermissionManager is the sole authority.
4.  Permission authorisation happens immediately before execution.
5.  Resource paths are canonicalised before authorisation.
6.  Approval is asynchronous.
7.  Approval requests have unique IDs and expiry.
8.  Cancellation can interrupt every state.
9.  Side-effecting actions are never blindly retried.
10. UNKNOWN tool outcomes are not treated as failures.
11. Critic verification never grants authorisation.
12. External content can never grant authority.
13. CognitiveEngine (v0.6) is completely untouched.
14. Every permission-sensitive execution is audited.
15. Disagreement detection never resolves by choosing the more permissive action.
16. Disagreement retry is strictly bounded by DisagreementResolver.max_rounds.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine

from app.agents.contracts import (
    AgentResult,
    DisagreementFeedback,
    PlannerResult,
    PlannerTask,
)
from app.agents.coordinator import (
    ApprovalNotifier,
    BudgetExhaustedError,
    Coordinator,
    CoordinatorBudget,
    CoordinatorState,
)
from app.agents.executor import ExecutorAgent
from app.agents.planner import PlannerAgent
from app.agents.retry import DisagreementError, DisagreementResolver, RetryPolicy
from app.core.audit import AuditEvent, record
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import ToolRegistry

_LOG = logging.getLogger("jasper.multi_agent_coordinator")


class MultiAgentCoordinator(Coordinator):
    """Planner/Executor orchestrator that extends the base Coordinator.

    Inherits the entire Coordinator state machine, budget, permissions,
    approval gate, retry policy, audit, and cancellation machinery.
    Adds only the multi-agent delegation layer.

    Parameters
    ----------
    registry, permissions, budget, approval_notifier, workspace_root,
    retry_policy:
        Passed directly to the base Coordinator constructor.
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
        super().__init__(
            registry=registry,
            permissions=permissions,
            budget=budget,
            approval_notifier=approval_notifier,
            workspace_root=workspace_root,
            retry_policy=retry_policy,
        )
        self._planner = PlannerAgent()
        self._executor = ExecutorAgent()

    # ------------------------------------------------------------------
    # Multi-agent entry point
    # ------------------------------------------------------------------

    async def run_multi_agent(
        self,
        planner_callable: Callable[[PlannerTask], Coroutine[Any, Any, AgentResult]],
        executor_callable: Callable[
            [PlannerResult, "DisagreementFeedback | None"],
            Coroutine[Any, Any, AgentResult],
        ],
        user_text: str,
        cancel_callback: Callable[[], bool] | None = None,
        max_disagreement_rounds: int = 3,
        max_turns: int = 1,
    ) -> str:
        """Run a complete Planner -> Executor -> tool pipeline.

        Parameters
        ----------
        planner_callable:
            Async callable ``(PlannerTask) -> AgentResult``.
            Must be side-effect-free.
        executor_callable:
            Async callable ``(PlannerResult, DisagreementFeedback | None) -> AgentResult``.
            Receives typed context only; no authority objects.
        user_text:
            The original user request.
        cancel_callback:
            Optional; if it returns True, asyncio.CancelledError is raised.
        max_disagreement_rounds:
            Maximum Executor retry attempts after disagreement is detected.
            After this limit, DisagreementError is raised and the run halts.

        Returns
        -------
        str
            Synthesised answer from the Executor approved tool outputs.

        Raises
        ------
        asyncio.CancelledError
        BudgetExhaustedError
        DisagreementError
        RuntimeError
        """
        if self._state != CoordinatorState.IDLE:
            raise RuntimeError(
                "MultiAgentCoordinator is not in IDLE state; cannot start a new run."
            )
        self._budget.reset()
        self._verification_failures = 0
        self._active_approval_gate = None

        try:
            return await asyncio.wait_for(
                self._run_multi_agent_cycle(
                    planner_callable,
                    executor_callable,
                    user_text,
                    cancel_callback,
                    max_disagreement_rounds,
                    max_turns,
                ),
                timeout=self._budget.timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._state = CoordinatorState.ERROR
            record(AuditEvent.BUDGET_EXCEEDED, actor="coordinator",
                   detail="wall-clock timeout (multi-agent)")
            raise BudgetExhaustedError("MultiAgentCoordinator wall-clock timeout exceeded.")
        except asyncio.CancelledError:
            _LOG.info("multi-agent coordinator cancelled state=%s", self._state.value)
            self._state = CoordinatorState.IDLE
            raise
        except BudgetExhaustedError:
            self._state = CoordinatorState.ERROR
            raise
        except DisagreementError:
            # State already set to ERROR inside _run_multi_agent_cycle
            raise
        except Exception:
            if self._state not in (CoordinatorState.IDLE, CoordinatorState.ERROR):
                self._state = CoordinatorState.ERROR
            raise
        finally:
            self._active_approval_gate = None
            if self._state not in (CoordinatorState.IDLE, CoordinatorState.ERROR):
                self._state = CoordinatorState.IDLE

    # ------------------------------------------------------------------
    # Pre-execution validation gate
    # ------------------------------------------------------------------

    def _validate_planner_result(self, planner_result: AgentResult, task_id: str) -> None:
        """Validate Planner output before invoking the Executor.

        Ensures that:
        1. Planner did not fail with errors.
        2. All proposed actions reference registered tools in the ToolRegistry.
        3. All action arguments are valid mappings and can be JSON-serialized.
        4. Filesystem tool path arguments are present and resolvable.

        Emits a structured terminal AuditEvent (PLANNER_INVOKED, status="FAILED")
        on validation failure without leaking raw argument payloads.

        Raises
        ------
        ValueError
            If planner output is invalid, malformed, or uncanonicalizable.
        """
        def _reject(err_msg: str, safe_detail: str, exc: Exception | None = None) -> None:
            record(
                AuditEvent.PLANNER_INVOKED,
                actor="coordinator",
                task_id=task_id,
                status="FAILED",
                detail=safe_detail,
            )
            _LOG.warning("planner output rejected task_id=%s reason=%s", task_id, err_msg)
            if exc:
                raise ValueError(err_msg) from exc
            raise ValueError(err_msg)

        if planner_result.errors:
            err_msg = f"Planner failed with errors: {'; '.join(planner_result.errors)}"
            _reject(err_msg, f"planner_errors:{len(planner_result.errors)}")

        for action in planner_result.proposed_actions:
            if not action.tool_name:
                err_msg = "Planner proposed an action with empty tool_name"
                _reject(err_msg, "empty_tool_name")

            try:
                tool = self._registry.get(action.tool_name)
            except KeyError as exc:
                err_msg = f"Planner proposed unregistered tool: '{action.tool_name}'"
                _reject(err_msg, f"unregistered_tool:{action.tool_name}", exc=exc)

            if not isinstance(action.arguments, dict):
                err_msg = (
                    f"Planner proposed an uncanonicalizable action: arguments must be a dict, "
                    f"got {type(action.arguments).__name__}"
                )
                _reject(err_msg, f"arguments_not_dict:{action.tool_name}")

            try:
                json.dumps(action.arguments, sort_keys=True)
            except (TypeError, ValueError) as exc:
                err_msg = f"Planner proposed an uncanonicalizable action: {exc}"
                _reject(err_msg, f"unserializable_arguments:{action.tool_name}", exc=exc)

            if tool.requires_filesystem:
                if not tool.path_argument or tool.path_argument not in action.arguments:
                    err_msg = (
                        f"Planner proposed an uncanonicalizable action: tool '{tool.name}' "
                        f"requires filesystem path argument '{tool.path_argument}'"
                    )
                    _reject(err_msg, f"missing_path_argument:{tool.name}")

                raw_path = str(action.arguments[tool.path_argument])
                try:
                    Path(raw_path).expanduser().resolve()
                except Exception as exc:
                    err_msg = f"Planner proposed an uncanonicalizable action: invalid path '{raw_path}': {exc}"
                    _reject(err_msg, f"invalid_path_argument:{tool.name}", exc=exc)

    # ------------------------------------------------------------------
    # Internal multi-agent cycle
    # ------------------------------------------------------------------

    @staticmethod
    def _format_turn_observations(tool_outputs: list[dict[str, Any]]) -> str:
        """Format outputs from a turn's executed tools as observation feedback for the next turn."""
        parts: list[str] = []
        for out in tool_outputs:
            tool_name = out.get("tool", "unknown_tool")
            status = out.get("status", "unknown")
            if status == "success":
                raw_res = out.get("result", "")
                try:
                    data = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
                except Exception:
                    data = raw_res

                if isinstance(data, dict):
                    if "snapshot" in data or "url" in data:
                        title = data.get("title", "")
                        url = data.get("url", "")
                        snapshot = data.get("snapshot", "")
                        parts.append(
                            f"[Tool {tool_name}]: Successfully navigated to {url} (Title: '{title}').\n"
                            f"Page Title: {title}\nCurrent URL: {url}\n{snapshot}"
                        )
                    elif "text" in data:
                        title = data.get("title", "")
                        text = data.get("text", "")
                        parts.append(f"[Tool {tool_name}]: Page Content ({title}):\n{text}")
                    elif "target" in data:
                        target = data.get("target", "")
                        parts.append(f"[Tool {tool_name}]: Target: {target}, Status: {data.get('status', 'success')}")
                    elif "path" in data:
                        parts.append(f"[Tool {tool_name}]: Wrote {data.get('path')} ({data.get('bytes_written', 0)} bytes).")
                    elif "_raw" in data:
                        parts.append(f"[Tool {tool_name}]: {data['_raw']}")
                    else:
                        parts.append(f"[Tool {tool_name}]: {json.dumps(data)}")
                else:
                    parts.append(f"[Tool {tool_name}]: {data}")
            else:
                err = out.get("error", "Unknown error")
                parts.append(f"[Tool {tool_name} ERROR]: {err}")

        return "\n\n".join(parts)

    async def _run_multi_agent_cycle(
        self,
        planner_callable: Callable[[PlannerTask], Coroutine[Any, Any, AgentResult]],
        executor_callable: Callable[
            [PlannerResult, "DisagreementFeedback | None"],
            Coroutine[Any, Any, AgentResult],
        ],
        user_text: str,
        cancel_callback: Callable[[], bool] | None,
        max_disagreement_rounds: int,
        max_turns: int = 1,
    ) -> str:
        current_context = user_text
        all_tool_outputs: list[dict[str, Any]] = []
        last_result: AgentResult | None = None

        for turn_idx in range(max_turns):
            self._check_cancelled(cancel_callback)

            # ----------------------------------------------------------------
            # Phase 1: Planner
            # ----------------------------------------------------------------
            self._transition(CoordinatorState.PLANNING)
            self._check_cancelled(cancel_callback)

            task = PlannerTask(user_text=current_context)

            planner_result_raw = await self._planner.invoke(
                callable_=planner_callable,
                task=task,
                budget=self._budget,
                cancel_callback=cancel_callback,
                emit_terminal=False,
            )

            # Pre-execution validation gate (invariant: invalid plan never reaches Executor)
            self._validate_planner_result(planner_result_raw, task.task_id)

            # Emit planner terminal SUCCESS only after validation passes
            record(
                AuditEvent.PLANNER_INVOKED,
                actor="planner",
                task_id=task.task_id,
                status="SUCCESS",
                detail=f"proposed_actions={len(planner_result_raw.proposed_actions)}",
            )

            # Build the typed handoff (wraps validated raw AgentResult).
            planner_handoff = PlannerResult(
                task_id=task.task_id,
                user_text=current_context,
                planner_result=planner_result_raw,
            )

            # ----------------------------------------------------------------
            # Phase 2: Executor loop (bounded by DisagreementResolver)
            # ----------------------------------------------------------------
            self._transition(CoordinatorState.ACTING)
            self._check_cancelled(cancel_callback)

            resolver = DisagreementResolver(max_rounds=max_disagreement_rounds)
            feedback: DisagreementFeedback | None = None
            executor_result: AgentResult | None = None

            while True:
                self._check_cancelled(cancel_callback)

                executor_result = await self._executor.invoke(
                    callable_=executor_callable,
                    handoff=planner_handoff,
                    budget=self._budget,
                    feedback=feedback,
                    cancel_callback=cancel_callback,
                )

                # Check for Planner/Executor disagreement.
                planner_actions = planner_handoff.planner_result.proposed_actions
                executor_actions = executor_result.proposed_actions

                if resolver.is_disagreement(planner_actions, executor_actions):
                    excess_actions = resolver.get_excess_actions(planner_actions, executor_actions)
                    planner_actions_tuple = tuple(planner_actions)

                    unexpected_summary = [f"{e.tool_name}(excess={e.excess_count})" for e in excess_actions]

                    record(
                        AuditEvent.DISAGREEMENT_DETECTED,
                        actor="coordinator",
                        task_id=task.task_id,
                        status="DETECTED",
                        detail=(
                            f"excess_actions={unexpected_summary!r} "
                            f"round={resolver._rounds + 1}/{max_disagreement_rounds}"
                        ),
                    )
                    _LOG.warning(
                        "planner/executor disagreement task_id=%s excess_actions=%s round=%d/%d",
                        task.task_id, unexpected_summary,
                        resolver._rounds + 1, max_disagreement_rounds,
                    )

                    resolver.record_round()

                    try:
                        resolver.assert_not_limit_reached()
                    except DisagreementError as exc:
                        record(
                            AuditEvent.DISAGREEMENT_HALTED,
                            actor="coordinator",
                            task_id=task.task_id,
                            status="HALTED",
                            detail=str(exc),
                        )
                        _LOG.error(
                            "disagreement resolution limit reached; halting task_id=%s",
                            task.task_id,
                        )
                        self._state = CoordinatorState.ERROR
                        raise

                    # Build typed feedback for the next Executor attempt.
                    feedback = DisagreementFeedback(
                        round_number=resolver._rounds,
                        max_rounds=max_disagreement_rounds,
                        excess_actions=excess_actions,
                        planner_actions=planner_actions_tuple,
                    )
                    # Retry the Executor with explicit disagreement context.
                    continue

                # No disagreement -- proceed to tool execution.
                break

            assert executor_result is not None
            last_result = executor_result

            # ----------------------------------------------------------------
            # Phase 3: Execute Executor ProposedActions
            # (inherited _execute_action: permission -> approval -> tool -> audit)
            # ----------------------------------------------------------------
            turn_tool_outputs: list[dict[str, Any]] = []
            for action in executor_result.proposed_actions:
                self._check_cancelled(cancel_callback)
                output = await self._execute_action(action, cancel_callback)
                turn_tool_outputs.append(output)
                all_tool_outputs.append(output)

            # ----------------------------------------------------------------
            # Phase 4: Observe
            # ----------------------------------------------------------------
            self._transition(CoordinatorState.OBSERVING)
            self._check_cancelled(cancel_callback)

            # ----------------------------------------------------------------
            # Phase 5: Verify (if a verification result is present)
            # ----------------------------------------------------------------
            self._transition(CoordinatorState.VERIFYING)
            self._check_cancelled(cancel_callback)

            if executor_result.verification is not None:
                self._handle_verification(executor_result.verification)

            # Check if finished: if planner proposed 0 actions, task is complete!
            if not planner_result_raw.proposed_actions:
                _LOG.info(
                    "Planner proposed 0 actions at turn %d/%d; concluding multi-turn loop.",
                    turn_idx + 1, max_turns,
                )
                break

            # If more turns remain, prepare feedback context for next turn
            if turn_idx < max_turns - 1:
                obs_text = self._format_turn_observations(turn_tool_outputs)
                current_context = f"{current_context}\n\n## Action Results (Turn {turn_idx + 1}):\n{obs_text}"

        self._transition(CoordinatorState.IDLE)
        assert last_result is not None
        return self._synthesise_answer(last_result, all_tool_outputs)