"""Application-owned catalog remediation approval DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog.remediation import (
    CatalogRemediationApproval as DataCatalogRemediationApproval,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalEvent as DataCatalogRemediationApprovalEvent,
)

__all__ = [
    "CatalogRemediationActionExecution",
    "CatalogRemediationActionExecutionStatus",
    "CatalogRemediationApproval",
    "CatalogRemediationApprovalDecision",
    "CatalogRemediationApprovalEvent",
    "CatalogRemediationApprovalEventAction",
    "CatalogRemediationApprovalStatus",
    "to_catalog_remediation_approval",
    "to_catalog_remediation_approval_event",
]

type CatalogRemediationApprovalStatus = Literal[
    "requested",
    "approved",
    "rejected",
    "completed",
    "cancelled",
]
type CatalogRemediationApprovalDecision = Literal["approved", "rejected"]
type CatalogRemediationActionExecutionStatus = Literal["success", "skipped", "failed"]
type CatalogRemediationApprovalEventAction = Literal[
    "requested",
    "approved",
    "rejected",
    "completed",
    "cancelled",
    "execution_failed",
]


@dataclass(frozen=True, slots=True)
class CatalogRemediationActionExecution:
    """Application DTO for one approved remediation action execution."""

    approval_id: str
    action: str
    executed_by: str
    executed_at: datetime
    result_payload: dict[str, object]
    status: CatalogRemediationActionExecutionStatus = "success"
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogRemediationApproval:
    """Application DTO for current remediation approval state."""

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


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalEvent:
    """Application DTO for remediation approval audit events."""

    approval_id: str
    action: CatalogRemediationApprovalEventAction
    actor: str
    action_at: datetime
    status: CatalogRemediationApprovalStatus
    notes: str | None = None


def to_catalog_remediation_approval(
    approval: DataCatalogRemediationApproval,
) -> CatalogRemediationApproval:
    """Map data-layer remediation approval record to application DTO."""
    return CatalogRemediationApproval(
        approval_id=approval.approval_id,
        item_id=approval.item_id,
        action=approval.action,
        status=approval.status,
        requested_by=approval.requested_by,
        requested_at=approval.requested_at,
        intent_type=approval.intent_type,
        method=approval.method,
        path=approval.path,
        request_payload=approval.request_payload,
        notes=approval.notes,
        decided_by=approval.decided_by,
        decided_at=approval.decided_at,
        decision_notes=approval.decision_notes,
    )


def to_catalog_remediation_approval_event(
    event: DataCatalogRemediationApprovalEvent,
) -> CatalogRemediationApprovalEvent:
    """Map data-layer remediation approval event to application DTO."""
    return CatalogRemediationApprovalEvent(
        approval_id=event.approval_id,
        action=event.action,
        actor=event.actor,
        action_at=event.action_at,
        status=event.status,
        notes=event.notes,
    )
