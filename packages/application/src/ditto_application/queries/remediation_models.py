"""Catalog remediation query DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_application.catalog_freshness import CatalogFreshnessStatus
from ditto_application.queries.catalog import (
    CatalogSourceFallbackPolicyEffect,
    CatalogSourceSelectionBlocker,
    CatalogSourceSelectionStatus,
)
from ditto_application.queries.lineage import DataLineageCatalogStatus

__all__ = [
    "CatalogRemediationApprovalIntent",
    "CatalogRemediationBacklogReport",
    "CatalogRemediationEvidenceRequirement",
    "CatalogRemediationIntentType",
    "CatalogRemediationItem",
    "CatalogRemediationItemDetail",
    "CatalogRemediationReasonCount",
    "CatalogRemediationRequirementStatus",
    "CatalogRemediationSeverity",
    "CatalogRemediationSeverityCount",
    "CatalogRemediationSource",
    "CatalogRemediationSourceCount",
    "CatalogRemediationSourceFallbackPolicyEffectCount",
]

type CatalogRemediationSource = Literal[
    "source_health",
    "maturity_governance",
    "lineage_catalog",
]
type CatalogRemediationSeverity = Literal["critical", "warning", "info"]
type CatalogRemediationIntentType = Literal["read", "write", "manual"]
type CatalogRemediationRequirementStatus = Literal[
    "missing",
    "rejected",
    "attention_required",
]


@dataclass(frozen=True, slots=True)
class CatalogRemediationSeverityCount:
    """Remediation backlog count by severity."""

    severity: CatalogRemediationSeverity
    count: int


@dataclass(frozen=True, slots=True)
class CatalogRemediationSourceCount:
    """Remediation backlog count by source report."""

    source: CatalogRemediationSource
    count: int


@dataclass(frozen=True, slots=True)
class CatalogRemediationReasonCount:
    """Remediation backlog count by source and reason."""

    source: CatalogRemediationSource
    reason: str
    count: int


@dataclass(frozen=True, slots=True)
class CatalogRemediationSourceFallbackPolicyEffectCount:
    """Remediation backlog count by active source fallback policy effect."""

    policy_id: str
    policy_status: str
    catalog_selected_source: str
    effective_selected_source: str
    count: int


@dataclass(frozen=True, slots=True)
class CatalogRemediationEvidenceRequirement:
    """Evidence or operator input required before a remediation can proceed."""

    requirement_id: str
    source: str
    status: CatalogRemediationRequirementStatus
    description: str


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalIntent:
    """Backend-owned next-step intent for an operator-approved remediation action."""

    action: str
    intent_type: CatalogRemediationIntentType
    method: str | None
    path: str | None
    request_template: dict[str, object]
    required_operator_inputs: tuple[str, ...]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogRemediationItem:
    """One backend-owned remediation backlog item."""

    item_id: str
    source: CatalogRemediationSource
    dataset_id: str
    namespace: str
    severity: CatalogRemediationSeverity
    reasons: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    trade_date: str | None = None
    run_id: str | None = None
    side: str | None = None
    partition_keys: tuple[str, ...] = ()
    default_source: str | None = None
    selected_source: str | None = None
    fallback_sources: tuple[str, ...] = ()
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffect | None = None
    source_selection_status: CatalogSourceSelectionStatus | None = None
    source_selection_blockers: tuple[CatalogSourceSelectionBlocker, ...] = ()
    current_maturity: str | None = None
    promotion_status: str | None = None
    catalog_status: DataLineageCatalogStatus | None = None
    freshness_status: CatalogFreshnessStatus | None = None


@dataclass(frozen=True, slots=True)
class CatalogRemediationItemDetail:
    """Detailed backend contract for one remediation backlog item."""

    generated_at: datetime
    item: CatalogRemediationItem
    summary: str
    evidence_requirements: tuple[CatalogRemediationEvidenceRequirement, ...]
    approval_intents: tuple[CatalogRemediationApprovalIntent, ...]


@dataclass(frozen=True, slots=True)
class CatalogRemediationBacklogReport:
    """Action-oriented catalog/source/maturity/lineage remediation backlog."""

    generated_at: datetime
    dataset_ids: tuple[str, ...]
    trade_dates: tuple[str, ...]
    available_sources: tuple[str, ...]
    run_id: str | None
    total_items: int
    severity_counts: tuple[CatalogRemediationSeverityCount, ...]
    source_counts: tuple[CatalogRemediationSourceCount, ...]
    reason_counts: tuple[CatalogRemediationReasonCount, ...]
    items: tuple[CatalogRemediationItem, ...]
    source_fallback_policy_effect_counts: tuple[
        CatalogRemediationSourceFallbackPolicyEffectCount, ...
    ] = ()
