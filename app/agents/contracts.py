"""app/agents/contracts.py — Typed contracts for JASPER v0.7 multi-agent system.

All types here are pure data containers.  They carry no behaviour and import
nothing from the rest of the application, making them safe to import from
anywhere without creating circular dependencies.

Invariants enforced here
------------------------
* ``ProposedAction`` is a *declaration of intent*, not an instruction to
  execute.  Only the Coordinator may decide to execute a proposed action,
  and only after authorisation is confirmed immediately before execution
  (invariant 4).
* ``AgentResult.proposed_actions`` must be independently validated before
  any execution path is taken (invariant 2).
* ``ExternalContent`` wraps all untrusted data and carries an explicit flag
  that it must never grant authority or permissions (invariant 12).
* ``PermissionScope`` captures the full capability description required by
  invariant 5 (paths/scopes canonicalised before authorisation).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Permission scope
# ---------------------------------------------------------------------------

class ApprovalRequirement(Enum):
    """How much human approval is needed before executing a tool action."""
    NEVER = "never"          # READ-only, always safe — no approval needed
    ONCE_PER_SESSION = "once_per_session"  # Approved once, cached for the session
    ALWAYS = "always"        # Every individual execution requires explicit approval


@dataclass(frozen=True)
class PermissionScope:
    """Fine-grained capability description for a single tool action.

    All path-like resource_scope values MUST be canonicalised (absolute,
    resolved) by the caller before constructing this object (invariant 5).

    Attributes
    ----------
    risk:
        The risk category string matching ``Risk`` enum values in
        ``app/tools/registry.py`` (READ, WRITE, EXECUTE, NETWORK,
        DESTRUCTIVE, ADMIN).
    resource_scope:
        The exact resource the action is scoped to.  For filesystem tools
        this is a canonicalised absolute path; for network tools a domain or
        URL prefix; for memory tools a memory-store identifier.
    operation:
        Verb-noun description of the exact action (e.g. ``"file.read"``,
        ``"file.write"``, ``"memory.store"``).
    approval_requirement:
        Whether human approval is required and how often.
    lifetime_seconds:
        Optional expiry for a cached approval.  ``None`` means the approval
        expires at the end of the current turn.
    """
    risk: str
    resource_scope: str
    operation: str
    approval_requirement: ApprovalRequirement
    lifetime_seconds: int | None = None


# ---------------------------------------------------------------------------
# External / untrusted content
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExternalContent:
    """Typed wrapper for any data retrieved from outside JASPER's trust boundary.

    External content (web pages, file contents, tool output from external
    services) MUST be wrapped in this type before being passed to any agent.
    Agents and the Coordinator MUST treat the ``text`` field as *untrusted
    string data only* — it can never grant authority, permissions, or
    instructions (invariants 4, 12).

    Attributes
    ----------
    source:
        A human-readable description of where the content came from
        (e.g. ``"file:read(C:/report.txt)"``).
    text:
        The raw untrusted text payload.  Never interpolated directly into
        a system prompt; always rendered inside a clearly-labelled block.
    retrieved_at:
        UTC timestamp of retrieval.  Defaults to now.
    """
    source: str
    text: str
    retrieved_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def as_labelled_block(self) -> str:
        """Render a clearly-labelled, instruction-inert block for LLM context.

        The XML tags are the outermost boundary but are not the sole
        protection — Coordinator prompts must also instruct the model to
        treat the enclosed text as untrusted data, not as instructions.
        """
        return (
            f"<external_data source=\"{self.source}\">\n"
            f"{self.text}\n"
            f"</external_data>"
        )


# ---------------------------------------------------------------------------
# Proposed actions — declarations of intent, never executable directly
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProposedAction:
    """A typed, independently-validatable declaration of intent from an agent.

    An agent that wants to call a tool MUST express it as a ``ProposedAction``
    inside its ``AgentResult``.  The Coordinator is the *only* entity that may
    decide whether to execute a proposed action, and only after:

    1. Validating the ``ProposedAction`` schema (invariant 2).
    2. Confirming authorisation immediately before execution (invariant 4).
    3. Canonicalising all resource paths in ``scope`` (invariant 5).

    Agents must never execute tools directly (invariant 1).
    Critic verification must never grant authorisation (invariant 11).

    Attributes
    ----------
    action_id:
        Unique identifier for this proposal.  Generated automatically.
    tool_name:
        Name of the registered tool to call.
    arguments:
        Keyword arguments for the tool.  Must be JSON-serialisable.
    scope:
        The capability scope required.  All path values must be
        canonicalised by the Coordinator before authorisation.
    rationale:
        Agent's stated reason for requesting this action.  Stored in the
        audit log; never used to grant additional permission.
    """
    tool_name: str
    arguments: dict[str, Any]
    scope: PermissionScope
    rationale: str
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.tool_name or not self.tool_name.strip():
            raise ValueError("ProposedAction.tool_name must not be empty.")
        if not isinstance(self.arguments, dict):
            raise TypeError("ProposedAction.arguments must be a dict.")
        if not isinstance(self.scope, PermissionScope):
            raise TypeError("ProposedAction.scope must be a PermissionScope.")


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationResult:
    """The Critic's verdict on whether an action or plan succeeded.

    A ``VerificationResult`` is advisory only.  It cannot grant permissions,
    trigger execution, or override the Coordinator's authorisation checks
    (invariant 11).

    Attributes
    ----------
    passed:
        True if the Critic considers the outcome satisfactory.
    feedback:
        Human-readable explanation.  Stored in audit trail.
    retry_recommended:
        True if the Critic believes a retry is warranted.  The Coordinator
        is not obligated to retry; it considers budget and action type first.
    """
    passed: bool
    feedback: str
    retry_recommended: bool = False


# ---------------------------------------------------------------------------
# AgentResult — the complete typed output of one agent invocation
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Complete typed output of a single agent invocation.

    An ``AgentResult`` is the *only* channel through which an agent may
    communicate.  Every field is independently interpretable by the
    Coordinator.

    Invariants
    ----------
    * ``proposed_actions`` carries *intent*, never executable instructions.
      The Coordinator validates each ``ProposedAction`` independently before
      any execution (invariant 2).
    * Agents never execute tools directly; they request execution via
      ``proposed_actions`` (invariant 1).
    * A ``VerificationResult`` inside this result cannot grant authorisation
      for anything (invariant 11).

    Attributes
    ----------
    agent_id:
        Identifier of the agent that produced this result (e.g. ``"planner"``).
    observations:
        Facts the agent synthesised from its input context.
    evidence:
        Verbatim quotes or structured pointers from ``ExternalContent``
        that support the observations.
    proposed_actions:
        Zero or more tool-call requests.  Each must be validated and
        authorised before execution.
    tool_results:
        Structured results from tools executed in a *previous* Coordinator
        round that are now part of this agent's input context.
    verification:
        Optional Critic verdict on the current plan/action.
    errors:
        Failure states, malformed-response captures, or timeout records.
    metadata:
        Arbitrary key-value store for tracing (e.g. token counts, latency).
    """
    agent_id: str
    observations: list[str] = field(default_factory=list)
    evidence: list[ExternalContent] = field(default_factory=list)
    proposed_actions: list[ProposedAction] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    verification: VerificationResult | None = None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    @property
    def is_error(self) -> bool:
        """True when the agent reported at least one error."""
        return bool(self.errors)

    @property
    def has_proposed_actions(self) -> bool:
        """True when the agent is requesting tool execution."""
        return bool(self.proposed_actions)

    @property
    def verified_passed(self) -> bool:
        """True when a Critic verdict is present and passed."""
        return self.verification is not None and self.verification.passed


# ---------------------------------------------------------------------------
# Slice 6: Planner/Executor typed handoff contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlannerTask:
    """Bounded input context passed to the Planner callable.

    Who creates it: MultiAgentCoordinator
    Who consumes it: PlannerAgent (passed verbatim to planner_callable)
    Trusted: YES — created by Coordinator from validated user input
    Grants authority: NEVER

    Attributes
    ----------
    user_text:
        The original user request the Planner should reason about.
    task_id:
        Unique identifier for this planning round.  Used for audit
        correlation across Planner, Executor, and disagreement events.
    """
    user_text: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class PlannerResult:
    """Typed handoff from Planner to Executor.

    Who creates it: MultiAgentCoordinator (wraps PlannerAgent output)
    Who consumes it: MultiAgentCoordinator → validates → passes to ExecutorAgent
    Trusted: NO — wraps agent output; independently validated before use
    Grants authority: NEVER

    The Coordinator validates this object before passing it to the
    Executor callable.  The Executor callable receives only the fields
    in this dataclass — it has no access to the registry, permission
    manager, approval gate, or budget.

    Attributes
    ----------
    task_id:
        Matches ``PlannerTask.task_id`` — used for audit correlation.
    user_text:
        Original user request.  Executor treats this as read-only context.
    planner_result:
        The ``AgentResult`` produced by the Planner invocation.
    created_at:
        UTC timestamp of handoff creation.
    """
    task_id: str
    user_text: str
    planner_result: AgentResult
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def proposed_tool_names(self) -> frozenset[str]:
        """Return the set of tool names the Planner proposed."""
        return frozenset(a.tool_name for a in self.planner_result.proposed_actions)


@dataclass(frozen=True)
class DisagreementFeedback:
    """Explicit typed feedback passed to the Executor on disagreement retry.

    Who creates it: MultiAgentCoordinator (on disagreement detection)
    Who consumes it: ExecutorAgent (passed to executor_callable alongside PlannerResult)
    Trusted: YES — created by Coordinator from validated disagreement detection
    Grants authority: NEVER — carries no permission-granting fields

    Provides the Executor with explicit context about *why* its previous
    output was rejected, so it can revise its ``AgentResult`` to stay
    within the Planner's proposed tool set.

    Attributes
    ----------
    round_number:
        Which disagreement round this is (1-indexed).
    max_rounds:
        Total allowed rounds before ``DISAGREEMENT_HALTED``.
    unexpected_tools:
        Tools the Executor proposed that the Planner did not include.
    planner_tools:
        The full authorised tool set from the Planner.
    """
    round_number: int
    max_rounds: int
    unexpected_tools: frozenset[str]
    planner_tools: frozenset[str]
