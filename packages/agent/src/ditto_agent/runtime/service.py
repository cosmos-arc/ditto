"""Pure service boundary shared by Agent HTTP and CLI adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus


class AgentRuntimeError(RuntimeError):
    """Base failure exposed by the transport-neutral Agent runtime boundary."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class AgentRuntimeUnavailable(AgentRuntimeError):
    """The Agent feature or one of its required providers is unavailable."""

    def __init__(self, reason_code: str) -> None:
        super().__init__("Agent runtime is unavailable", reason_code=reason_code)


class AgentResourceNotFound(AgentRuntimeError):
    """A requested Agent-owned identity is absent."""


class AgentRequestConflict(AgentRuntimeError):
    """An idempotency, revision, or terminal-state fence rejected a write."""


class AgentInvalidRequest(AgentRuntimeError):
    """A transport-neutral request violates an Agent contract."""


class ApprovalDecisionKind(StrEnum):
    """The only decisions accepted for an exact approval action hash."""

    APPROVE = "approve"
    REJECT = "reject"


class ApprovalDecisionStatus(StrEnum):
    """Terminal approval state returned through the service boundary."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class AgentSessionCreateCommand:
    """Create one local Agent session under a durable request identity."""

    retention_class: RetentionClass
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AgentRunCreateCommand:
    """Create one host-governed, initially queued Agent run."""

    session_id: str
    objective: str
    authority_hash: str
    max_model_tokens: int
    max_model_spend_usd: Decimal
    model_profile: ModelProfile
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AgentRunCancelCommand:
    """Cancel a queued or running run under an optimistic revision fence."""

    run_id: str
    expected_revision: int


@dataclass(frozen=True, slots=True)
class AgentApprovalDecisionCommand:
    """Decide one immutable approval action."""

    approval_id: str
    expected_action_hash: str
    decision: ApprovalDecisionKind
    operator_id: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class AgentSessionView:
    """Transport-neutral session projection."""

    session_id: str
    created_at: datetime
    retention_class: RetentionClass


@dataclass(frozen=True, slots=True)
class AgentRunView:
    """Non-sensitive run projection; the raw objective is never returned."""

    run_id: str
    session_id: str
    status: RunStatus
    objective_hash: str
    authority_hash: str
    max_model_tokens: int
    max_model_spend_usd: Decimal
    model_profile: ModelProfile
    manifest_hash: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    revision: int


@dataclass(frozen=True, slots=True)
class AgentEventView:
    """One persisted event suitable for deterministic SSE replay."""

    event_id: int
    run_id: str
    run_sequence: int
    event_type: str
    payload_hash: str
    occurred_at: datetime
    prev_hash: str | None
    event_hash: str
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class AgentApprovalDecision:
    """Terminal decision receipt bound to the exact action hash."""

    approval_id: str
    run_id: str
    action_hash: str
    status: ApprovalDecisionStatus
    operator_id: str
    reason: str | None
    decided_at: datetime


class AgentRuntimePort(Protocol):
    """Shared Agent use-case surface; transports never access storage directly."""

    def create_session(self, command: AgentSessionCreateCommand) -> AgentSessionView:
        """Create or exactly replay one session request."""
        ...

    def create_run(self, command: AgentRunCreateCommand) -> AgentRunView:
        """Create or exactly replay one queued run request."""
        ...

    def get_run(self, run_id: str) -> AgentRunView:
        """Return one non-sensitive run projection."""
        ...

    def list_run_events(
        self,
        run_id: str,
        *,
        after_event_id: int | None = None,
    ) -> tuple[AgentEventView, ...]:
        """Replay only persisted events after an optional global event ID."""
        ...

    def cancel_run(self, command: AgentRunCancelCommand) -> AgentRunView:
        """Cancel one queued/running run under revision CAS."""
        ...

    def decide_approval(
        self,
        command: AgentApprovalDecisionCommand,
    ) -> AgentApprovalDecision:
        """Commit one terminal approval decision."""
        ...


__all__ = [
    "AgentApprovalDecision",
    "AgentApprovalDecisionCommand",
    "AgentEventView",
    "AgentInvalidRequest",
    "AgentRequestConflict",
    "AgentResourceNotFound",
    "AgentRunCancelCommand",
    "AgentRunCreateCommand",
    "AgentRunView",
    "AgentRuntimeError",
    "AgentRuntimePort",
    "AgentRuntimeUnavailable",
    "AgentSessionCreateCommand",
    "AgentSessionView",
    "ApprovalDecisionKind",
    "ApprovalDecisionStatus",
]
