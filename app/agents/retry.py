"""app/agents/retry.py -- JASPER v0.7 Slice 5: Retry and Failure Handling.

This module provides operation-sensitive retry policy, bounded disagreement
resolution, and structured failure types used by the Coordinator.

Key invariants enforced here
-----------------------------
* READ and MODEL operations may use bounded retries with exponential backoff.
* WRITE, EXECUTE, and DESTRUCTIVE operations are NEVER automatically retried.
* Disagreement resolution is strictly bounded (no infinite loop).
* All retry/failure paths produce auditable structured events.

Architecture note — deferred integration
-----------------------------------------
DisagreementResolver and DisagreementError are **foundation primitives** for the
upcoming multi-agent Planner/Executor delegation layer (later v0.7 slices).
They are NOT wired into the Coordinator in Slice 5 because the Coordinator does
not yet expose distinct Planner and Executor roles.

Integration will occur when:
  1. Planner/Executor role separation is introduced.
  2. The Coordinator can observe *both* the Planner's proposed action set and
     the Executor's proposed action set in a single cycle.

Do NOT call DisagreementResolver from Coordinator code until that delegation
layer exists.  Until then this module's Coordinator integration surface is
solely RetryPolicy and operation_type_from_risk.

This module imports nothing from coordinator.py to avoid circular dependencies.
It is imported BY the coordinator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from app.agents.contracts import ProposedAction


# ---------------------------------------------------------------------------
# Operation type taxonomy
# ---------------------------------------------------------------------------

class OperationType(str, Enum):
    """Classification of operations for retry policy decisions.

    Only READ and MODEL operations are eligible for automatic retry.
    WRITE, EXECUTE, and DESTRUCTIVE are never retried automatically --
    their outcome is UNKNOWN after a failure and must be verified.
    """
    READ        = "read"
    MODEL       = "model"      # LLM inference (no side effects)
    WRITE       = "write"
    EXECUTE     = "execute"
    DESTRUCTIVE = "destructive"
    NETWORK     = "network"    # treated as side-effecting by default
    ADMIN       = "admin"

    # Convenience set of operation types that may be automatically retried.
    @classmethod
    def retriable(cls) -> frozenset[OperationType]:
        return frozenset({cls.READ, cls.MODEL})

    # Convenience set of operation types whose failure status is UNKNOWN.
    @classmethod
    def side_effecting(cls) -> frozenset[OperationType]:
        return frozenset({cls.WRITE, cls.EXECUTE, cls.DESTRUCTIVE, cls.NETWORK})


def operation_type_from_risk(risk: str) -> OperationType:
    """Map a tool risk string to an OperationType for retry policy decisions.

    Parameters
    ----------
    risk:
        The ``PermissionScope.risk`` string (e.g. ``"read"``, ``"write"``).

    Returns
    -------
    OperationType
        Matching operation type, defaulting to WRITE (never retried) for
        any unrecognised risk string to be safe.
    """
    mapping = {
        "read":        OperationType.READ,
        "write":       OperationType.WRITE,
        "execute":     OperationType.EXECUTE,
        "destructive": OperationType.DESTRUCTIVE,
        "network":     OperationType.NETWORK,
        "admin":       OperationType.ADMIN,
    }
    return mapping.get(risk.lower(), OperationType.WRITE)


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """Operation-sensitive retry policy for the Coordinator.

    Parameters
    ----------
    max_retries:
        Maximum number of retry attempts for retriable operations.
        Side-effecting operations always get 0 retries regardless of this value.
    base_backoff:
        Base backoff duration in seconds.  The actual backoff for attempt N is
        ``min(base_backoff * 2**N, max_backoff)``.  Set to 0.0 for tests.
    max_backoff:
        Hard cap on backoff duration in seconds.
    """
    max_retries: int = 2
    base_backoff: float = 0.5
    max_backoff: float = 30.0

    def should_retry(
        self,
        op: OperationType,
        attempt: int,
    ) -> bool:
        """Return True if the operation may be retried after this attempt.

        Parameters
        ----------
        op:
            The operation type being attempted.
        attempt:
            Zero-based attempt number (0 = first attempt, 1 = first retry, ...).
            Returns True when ``attempt < max_retries`` for retriable ops.
        """
        if op not in OperationType.retriable():
            # Invariant: side-effecting operations are NEVER automatically retried.
            return False
        return attempt < self.max_retries

    def backoff_seconds(
        self,
        attempt: int,
        op: OperationType | None = None,
    ) -> float:
        """Return the backoff duration in seconds for this attempt.

        Parameters
        ----------
        attempt:
            Zero-based attempt number.
        op:
            Optional operation type.  If provided and non-retriable, returns 0.0.
        """
        if op is not None and op not in OperationType.retriable():
            return 0.0
        if self.base_backoff <= 0.0:
            return 0.0
        raw = self.base_backoff * (2 ** attempt)
        return min(raw, self.max_backoff)


# ---------------------------------------------------------------------------
# Retry-specific exceptions
# ---------------------------------------------------------------------------

class RetryableOperationError(Exception):
    """Raised internally when a retriable operation fails and no more retries remain."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        original_exc: Exception,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.original_exc = original_exc


# ---------------------------------------------------------------------------
# Disagreement resolver
# ---------------------------------------------------------------------------

class DisagreementError(RuntimeError):
    """Raised when Planner/Executor disagreement reaches the resolution limit.

    .. note:: Deferred integration
        This exception is not currently raised by any live Coordinator code.
        It will become active once the Planner/Executor delegation layer is
        introduced in a later v0.7 slice.
    """


@dataclass
class DisagreementResolver:
    """Bounded resolution of Planner/Executor action disagreements.

    A disagreement occurs when the set of tool names proposed by the Executor
    differs from the set proposed by the Planner in a material way (i.e., the
    Executor proposes actions that the Planner did not request).

    Resolution is bounded by ``max_rounds`` to prevent infinite disagreement
    loops (invariant 3 in the Slice 5 requirements).

    .. note:: Deferred Coordinator integration
        This class is a **foundation primitive** for the multi-agent
        Planner/Executor delegation layer.  It is NOT integrated into
        ``Coordinator`` in Slice 5 because the Coordinator does not yet
        expose distinct Planner and Executor roles.  Integration is
        intentionally deferred until the delegation layer is introduced
        in a later v0.7 slice.

    Parameters
    ----------
    max_rounds:
        Maximum number of disagreement resolution rounds before raising
        ``DisagreementError``.  After this limit, the Coordinator must
        halt safely or return to the user/approval boundary.
    """
    max_rounds: int = 3
    _rounds: int = field(default=0, init=False, repr=False)

    def is_disagreement(
        self,
        planner_actions: Sequence[ProposedAction],
        executor_actions: Sequence[ProposedAction],
    ) -> bool:
        """Return True if Executor proposes actions not requested by Planner.

        A disagreement is detected when the Executor proposes at least one
        tool name that is NOT in the Planner's proposed set.  If the Executor
        proposes a subset (or nothing), that is *not* a disagreement -- the
        Executor may legitimately decide fewer actions are needed.

        Parameters
        ----------
        planner_actions:
            Actions proposed by the Planner agent.
        executor_actions:
            Actions proposed by the Executor agent.
        """
        planner_names = {a.tool_name for a in planner_actions}
        executor_names = {a.tool_name for a in executor_actions}
        # Disagreement = Executor wants something not in the Planner's set
        return bool(executor_names - planner_names)

    def record_round(self) -> None:
        """Increment the disagreement round counter."""
        self._rounds += 1

    def is_limit_reached(self) -> bool:
        """Return True if the disagreement resolution limit has been reached."""
        return self._rounds >= self.max_rounds

    def assert_not_limit_reached(self) -> None:
        """Raise DisagreementError if the resolution limit has been reached.

        Raises
        ------
        DisagreementError
            When ``is_limit_reached()`` is True.
        """
        if self.is_limit_reached():
            raise DisagreementError(
                f"Planner/Executor disagreement resolution limit reached "
                f"({self._rounds}/{self.max_rounds} rounds). "
                f"Halting to prevent infinite disagreement loop."
            )
