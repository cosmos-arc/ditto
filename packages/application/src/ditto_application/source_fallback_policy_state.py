"""Application-owned source fallback policy DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy as DataCatalogSourceFallbackPolicy,
)
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyEvent as DataCatalogSourceFallbackPolicyEvent,
)

__all__ = [
    "CatalogSourceFallbackPolicy",
    "CatalogSourceFallbackPolicyEvent",
    "CatalogSourceFallbackPolicyEventAction",
    "CatalogSourceFallbackPolicyStatus",
    "to_catalog_source_fallback_policy",
    "to_catalog_source_fallback_policy_event",
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


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicy:
    """Application DTO for current source fallback policy state."""

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


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicyEvent:
    """Application DTO for source fallback policy audit events."""

    policy_id: str
    action: CatalogSourceFallbackPolicyEventAction
    actor: str
    action_at: datetime
    status: CatalogSourceFallbackPolicyStatus
    notes: str | None = None


def to_catalog_source_fallback_policy(
    policy: DataCatalogSourceFallbackPolicy,
) -> CatalogSourceFallbackPolicy:
    """Map data-layer source fallback policy state to application DTO."""
    return CatalogSourceFallbackPolicy(
        policy_id=policy.policy_id,
        dataset_id=policy.dataset_id,
        namespace=policy.namespace,
        trade_date=policy.trade_date,
        default_source=policy.default_source,
        selected_source=policy.selected_source,
        recommended_source=policy.recommended_source,
        status=policy.status,
        created_by=policy.created_by,
        created_at=policy.created_at,
        recommended_actions=policy.recommended_actions,
        reason_codes=policy.reason_codes,
        fallback_sources=policy.fallback_sources,
        unsupported_sources=policy.unsupported_sources,
        source_selection_status=policy.source_selection_status,
        source_selection_blockers=policy.source_selection_blockers,
        approval_required=policy.approval_required,
        execution_allowed=policy.execution_allowed,
        notes=policy.notes,
        decided_by=policy.decided_by,
        decided_at=policy.decided_at,
        decision_notes=policy.decision_notes,
    )


def to_catalog_source_fallback_policy_event(
    event: DataCatalogSourceFallbackPolicyEvent,
) -> CatalogSourceFallbackPolicyEvent:
    """Map data-layer source fallback policy event to application DTO."""
    return CatalogSourceFallbackPolicyEvent(
        policy_id=event.policy_id,
        action=event.action,
        actor=event.actor,
        action_at=event.action_at,
        status=event.status,
        notes=event.notes,
    )
