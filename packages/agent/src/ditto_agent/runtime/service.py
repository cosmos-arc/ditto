"""Pure service boundary shared by Agent HTTP and CLI adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.presentation import (
    AgentContextPresentation,
    AgentGuardrailPresentation,
    AgentToolPresentation,
    AgentUsagePresentation,
)


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


class AgentRuntimeState(StrEnum):
    """Stable non-sensitive runtime availability shown to operators."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class AgentApprovalStatus(StrEnum):
    """Operator-facing approval state including computed expiry."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AgentProjectionState(StrEnum):
    """Whether a readable run projection is complete or explicitly partial."""

    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class AgentSessionCreateCommand:
    """Create one local Agent session under a durable request identity."""

    retention_class: RetentionClass
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AgentCapabilityView:
    """Read-only feature and provider availability without credentials."""

    enabled: bool
    runtime_state: AgentRuntimeState
    provider: str | None
    available_profiles: tuple[ModelProfile, ...]
    default_profile: ModelProfile | None
    degradation_reason: str | None
    checked_at: datetime


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
    context: AgentContextPresentation | None = None
    execution_plan: AgentRunExecutionPlan | None = None


@dataclass(frozen=True, slots=True)
class AgentRunExecuteCommand:
    """Execute one queued run under its persisted authority and revision fence."""

    run_id: str
    expected_revision: int


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
class AgentSessionListView:
    """Stable newest-first session page."""

    items: tuple[AgentSessionView, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AgentRunView:
    """Authoritative run state enriched by a sanitized presentation projection."""

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
    objective: str | None = None
    context: AgentContextPresentation | None = None
    output_summary: str | None = None
    tool_records: tuple[AgentToolPresentation, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    guardrail: AgentGuardrailPresentation | None = None
    usage: AgentUsagePresentation | None = None
    failure_code: str | None = None
    event_cursor: int = 0
    projection_state: AgentProjectionState = AgentProjectionState.PARTIAL
    projection_reason: str | None = "agent_presentation_unconfigured"
    projection_version: int | None = None
    projection_updated_at: datetime | None = None
    execution_plan: AgentRunExecutionPlan | None = None


@dataclass(frozen=True, slots=True)
class AgentRunListView:
    """Stable newest-first run page."""

    items: tuple[AgentRunView, ...]
    total: int
    limit: int
    offset: int


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


@dataclass(frozen=True, slots=True)
class AgentApprovalView:
    """Exact immutable approval subject and its current public state."""

    approval_id: str
    run_id: str
    action_type: str
    target_identity: str
    action_payload: Mapping[str, object]
    action_hash: str
    status: AgentApprovalStatus
    requested_at: datetime
    expires_at: datetime
    operator_id: str | None
    reason: str | None
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class AgentApprovalListView:
    """Stable newest-first approval page."""

    items: tuple[AgentApprovalView, ...]
    total: int
    limit: int
    offset: int


class AgentRuntimePort(Protocol):
    """Shared Agent use-case surface; transports never access storage directly."""

    def get_capabilities(self) -> AgentCapabilityView:
        """Return non-sensitive runtime/provider availability in every state."""
        ...

    def list_sessions(self, *, limit: int, offset: int) -> AgentSessionListView:
        """List durable sessions newest first."""
        ...

    def list_runs(
        self,
        *,
        status: RunStatus | None,
        session_id: str | None,
        context_type: str | None,
        context_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentRunListView:
        """List durable runs with bounded equality filters."""
        ...

    def get_approval(self, approval_id: str) -> AgentApprovalView:
        """Return one exact approval subject and decision state."""
        ...

    def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | None,
        run_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentApprovalListView:
        """List approvals with pending/expired/decided filters."""
        ...

    def create_session(self, command: AgentSessionCreateCommand) -> AgentSessionView:
        """Create or exactly replay one session request."""
        ...

    def create_run(self, command: AgentRunCreateCommand) -> AgentRunView:
        """Create or exactly replay one queued run request."""
        ...

    async def execute_run(self, command: AgentRunExecuteCommand) -> AgentRunView:
        """Execute one queued read-only run and persist its governed outcome."""
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
    "AgentApprovalListView",
    "AgentApprovalStatus",
    "AgentApprovalView",
    "AgentCapabilityView",
    "AgentEventView",
    "AgentInvalidRequest",
    "AgentProjectionState",
    "AgentRequestConflict",
    "AgentResourceNotFound",
    "AgentRunCancelCommand",
    "AgentRunCreateCommand",
    "AgentRunExecuteCommand",
    "AgentRunListView",
    "AgentRunView",
    "AgentRuntimeError",
    "AgentRuntimePort",
    "AgentRuntimeState",
    "AgentRuntimeUnavailable",
    "AgentSessionCreateCommand",
    "AgentSessionListView",
    "AgentSessionView",
    "ApprovalDecisionKind",
    "ApprovalDecisionStatus",
]
