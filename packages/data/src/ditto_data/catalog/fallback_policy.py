"""Catalog source fallback policy state contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "CatalogSourceFallbackPolicy",
    "CatalogSourceFallbackPolicyEvent",
    "CatalogSourceFallbackPolicyEventAction",
    "CatalogSourceFallbackPolicyReader",
    "CatalogSourceFallbackPolicyStatus",
    "CatalogSourceFallbackPolicyWriter",
]

type CatalogSourceFallbackPolicyStatus = Literal[
    "draft",
    "approved",
    "active",
    "retired",
]
type CatalogSourceFallbackPolicyEventAction = Literal[
    "drafted",
    "approved",
    "activated",
    "retired",
]

_POLICY_STATUSES: tuple[CatalogSourceFallbackPolicyStatus, ...] = (
    "draft",
    "approved",
    "active",
    "retired",
)
_POLICY_EVENT_ACTIONS: tuple[CatalogSourceFallbackPolicyEventAction, ...] = (
    "drafted",
    "approved",
    "activated",
    "retired",
)


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicy:
    """Current durable source fallback policy state for one dataset/date."""

    policy_id: str
    dataset_id: str
    namespace: str
    trade_date: str
    default_source: str
    selected_source: str
    recommended_source: str | None
    status: CatalogSourceFallbackPolicyStatus
    created_by: str
    created_at: datetime
    recommended_actions: tuple[str, ...]
    reason_codes: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    unsupported_sources: tuple[str, ...]
    source_selection_status: str
    source_selection_blockers: tuple[str, ...]
    approval_required: bool
    execution_allowed: bool
    notes: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_notes: str | None = None

    def __post_init__(self) -> None:
        """Validate stable policy identity and lifecycle fields."""
        _validate_text("policy_id", self.policy_id)
        _validate_text("dataset_id", self.dataset_id)
        _validate_text("namespace", self.namespace)
        _validate_text("trade_date", self.trade_date)
        _validate_text("default_source", self.default_source)
        _validate_text("selected_source", self.selected_source)
        if self.recommended_source is not None:
            _validate_text("recommended_source", self.recommended_source)
        _validate_status(self.status)
        _validate_text("created_by", self.created_by)
        _validate_items("recommended_actions", self.recommended_actions)
        _validate_items("reason_codes", self.reason_codes)
        _validate_items("fallback_sources", self.fallback_sources)
        _validate_items("unsupported_sources", self.unsupported_sources)
        _validate_text("source_selection_status", self.source_selection_status)
        _validate_items("source_selection_blockers", self.source_selection_blockers)
        if self.decided_by is not None:
            _validate_text("decided_by", self.decided_by)


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicyEvent:
    """Append-only audit event for source fallback policy transitions."""

    policy_id: str
    action: CatalogSourceFallbackPolicyEventAction
    actor: str
    action_at: datetime
    status: CatalogSourceFallbackPolicyStatus
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate event identity fields."""
        _validate_text("policy_id", self.policy_id)
        _validate_event_action(self.action)
        _validate_text("actor", self.actor)
        _validate_status(self.status)


@runtime_checkable
class CatalogSourceFallbackPolicyReader(Protocol):
    """Read access to fallback policy current state and audit events."""

    def get_source_fallback_policy(
        self,
        policy_id: str,
    ) -> CatalogSourceFallbackPolicy | None:
        """Return one source fallback policy state by ID."""
        ...

    def list_source_fallback_policies(
        self,
        *,
        dataset_id: str | None = None,
        status: CatalogSourceFallbackPolicyStatus | None = None,
    ) -> tuple[CatalogSourceFallbackPolicy, ...]:
        """Return source fallback policies filtered by dataset or status."""
        ...

    def list_source_fallback_policy_events(
        self,
        policy_id: str,
    ) -> tuple[CatalogSourceFallbackPolicyEvent, ...]:
        """Return append-only events for one source fallback policy."""
        ...


@runtime_checkable
class CatalogSourceFallbackPolicyWriter(Protocol):
    """Write access to fallback policy current state and audit events."""

    def upsert_source_fallback_policy(
        self,
        policy: CatalogSourceFallbackPolicy,
    ) -> None:
        """Insert or replace current source fallback policy state."""
        ...

    def append_source_fallback_policy_event(
        self,
        event: CatalogSourceFallbackPolicyEvent,
    ) -> None:
        """Append a source fallback policy state transition event."""
        ...


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        msg = f"Invalid {field}: {value!r}"
        raise ValueError(msg)


def _validate_items(field: str, values: tuple[str, ...]) -> None:
    for value in values:
        _validate_text(field, value)


def _validate_status(value: str) -> None:
    if value not in _POLICY_STATUSES:
        msg = f"Invalid source fallback policy status: {value!r}"
        raise ValueError(msg)


def _validate_event_action(value: str) -> None:
    if value not in _POLICY_EVENT_ACTIONS:
        msg = f"Invalid source fallback policy event action: {value!r}"
        raise ValueError(msg)
