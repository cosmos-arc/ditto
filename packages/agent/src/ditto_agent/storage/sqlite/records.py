"""Immutable typed projections returned by Agent SQLite adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus


class ApprovalStatus(StrEnum):
    """Durable lifecycle for one exact action hash."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class IdempotencyStatus(StrEnum):
    """Durable completion state for one request identity."""

    PENDING = "pending"
    COMPLETED = "completed"


class IdempotencyDisposition(StrEnum):
    """Whether a reservation was newly created or exactly replayed."""

    CREATED = "created"
    REPLAY = "replay"


@dataclass(frozen=True, slots=True)
class StoredAgentRun:
    """Non-sensitive run metadata; the raw objective is deliberately absent."""

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
class StoredRunEvent:
    """One immutable run event with per-run chain identity."""

    event_id: int
    run_id: str
    run_sequence: int
    event_type: str
    payload_hash: str
    occurred_at: datetime
    prev_hash: str | None
    event_hash: str


@dataclass(frozen=True, slots=True)
class StoredApproval:
    """Durable decision over one immutable canonical action payload."""

    request_id: str
    run_id: str
    action_hash: str
    action_payload: bytes
    status: ApprovalStatus
    requested_at: datetime
    expires_at: datetime
    operator_id: str | None
    reason: str | None
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Request-hash fence and optional committed result identity."""

    scope: str
    idempotency_key: str
    request_hash: str
    status: IdempotencyStatus
    result_identity: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    """Reservation outcome plus its durable record."""

    disposition: IdempotencyDisposition
    record: IdempotencyRecord


@dataclass(frozen=True, slots=True)
class LeaseFence:
    """Exact monotonic ownership proof for one leased resource."""

    resource_kind: str
    resource_id: str
    owner_token: str
    fence: int
    lease_until: datetime
    revision: int


@dataclass(frozen=True, slots=True)
class RetentionMetadata:
    """Typed retention target; Task 7 never executes deletion."""

    target_kind: str
    target_id: str
    retention_class: RetentionClass
    retain_until: datetime | None
    legal_hold: bool
    updated_at: datetime


__all__ = [
    "ApprovalStatus",
    "IdempotencyDisposition",
    "IdempotencyRecord",
    "IdempotencyReservation",
    "IdempotencyStatus",
    "LeaseFence",
    "RetentionMetadata",
    "StoredAgentRun",
    "StoredApproval",
    "StoredRunEvent",
]
