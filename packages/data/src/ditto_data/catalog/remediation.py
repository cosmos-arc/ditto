"""Catalog remediation approval state contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "CatalogRemediationApproval",
    "CatalogRemediationApprovalEvent",
    "CatalogRemediationApprovalEventAction",
    "CatalogRemediationApprovalReader",
    "CatalogRemediationApprovalStatus",
    "CatalogRemediationApprovalWriter",
]

type CatalogRemediationApprovalStatus = Literal[
    "requested",
    "approved",
    "rejected",
    "completed",
    "cancelled",
]
type CatalogRemediationApprovalEventAction = Literal[
    "requested",
    "approved",
    "rejected",
    "completed",
    "cancelled",
    "execution_failed",
]

_APPROVAL_STATUSES: tuple[CatalogRemediationApprovalStatus, ...] = (
    "requested",
    "approved",
    "rejected",
    "completed",
    "cancelled",
)
_APPROVAL_EVENT_ACTIONS: tuple[CatalogRemediationApprovalEventAction, ...] = (
    "requested",
    "approved",
    "rejected",
    "completed",
    "cancelled",
    "execution_failed",
)


@dataclass(frozen=True, slots=True)
class CatalogRemediationApproval:
    """Current approval state for one backend remediation action."""

    approval_id: str
    item_id: str
    action: str
    status: CatalogRemediationApprovalStatus
    requested_by: str
    requested_at: datetime
    intent_type: str
    method: str | None
    path: str | None
    request_payload: dict[str, object]
    notes: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_notes: str | None = None

    def __post_init__(self) -> None:
        """Validate approval identity fields."""
        _validate_text("approval_id", self.approval_id)
        _validate_text("item_id", self.item_id)
        _validate_text("action", self.action)
        _validate_text("requested_by", self.requested_by)
        _validate_text("intent_type", self.intent_type)
        _validate_status(self.status)
        if self.method is not None:
            _validate_text("method", self.method)
        if self.path is not None:
            _validate_text("path", self.path)
        if self.decided_by is not None:
            _validate_text("decided_by", self.decided_by)


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalEvent:
    """Append-only audit event for remediation approval state transitions."""

    approval_id: str
    action: CatalogRemediationApprovalEventAction
    actor: str
    action_at: datetime
    status: CatalogRemediationApprovalStatus
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate event identity fields."""
        _validate_text("approval_id", self.approval_id)
        _validate_event_action(self.action)
        _validate_text("actor", self.actor)
        _validate_status(self.status)


@runtime_checkable
class CatalogRemediationApprovalReader(Protocol):
    """Read access to current remediation approval state and audit events."""

    def get_remediation_approval(
        self,
        approval_id: str,
    ) -> CatalogRemediationApproval | None:
        """Return one remediation approval state by ID."""
        ...

    def list_remediation_approvals(
        self,
        *,
        item_id: str | None = None,
        status: CatalogRemediationApprovalStatus | None = None,
    ) -> tuple[CatalogRemediationApproval, ...]:
        """Return remediation approval states filtered by item or status."""
        ...

    def list_remediation_approval_events(
        self,
        approval_id: str,
    ) -> tuple[CatalogRemediationApprovalEvent, ...]:
        """Return append-only events for one remediation approval."""
        ...


@runtime_checkable
class CatalogRemediationApprovalWriter(Protocol):
    """Write access to remediation approval state and audit events."""

    def upsert_remediation_approval(
        self,
        approval: CatalogRemediationApproval,
    ) -> None:
        """Insert or replace current remediation approval state."""
        ...

    def append_remediation_approval_event(
        self,
        event: CatalogRemediationApprovalEvent,
    ) -> None:
        """Append a remediation approval state transition event."""
        ...


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        msg = f"Invalid {field}: {value!r}"
        raise ValueError(msg)


def _validate_status(value: str) -> None:
    if value not in _APPROVAL_STATUSES:
        msg = f"Invalid remediation approval status: {value!r}"
        raise ValueError(msg)


def _validate_event_action(value: str) -> None:
    if value not in _APPROVAL_EVENT_ACTIONS:
        msg = f"Invalid remediation approval event action: {value!r}"
        raise ValueError(msg)
