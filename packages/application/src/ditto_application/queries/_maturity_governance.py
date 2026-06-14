"""Maturity governance report DTOs and pure assembly helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionRevocationReason,
    DatasetPromotionStatus,
)

from ditto_application.catalog_freshness import CatalogFreshnessStatus
from ditto_application.queries._maturity_types import (
    DatasetMaturitySummary,
    DatasetPromotionCriterionCount,
    DatasetPromotionReadinessItem,
    DatasetPromotionReadinessReport,
    DatasetPromotionStatusCount,
    DatasetStatus,
)

type DatasetMaturityGovernanceAttentionReason = Literal[
    "maturity_warning",
    "catalog_stale",
    "catalog_missing",
    "promotion_ready",
    "promotion_blocked",
    "promotion_revoked",
]

type DatasetMaturityGovernanceAttentionSeverity = Literal["critical", "warning", "info"]


@dataclass(frozen=True, slots=True)
class DatasetMaturityGovernanceAttentionReasonCount:
    """Maturity governance attention reason count across datasets."""

    reason: DatasetMaturityGovernanceAttentionReason
    count: int


@dataclass(frozen=True, slots=True)
class DatasetMaturityGovernanceAttentionSeverityCount:
    """Maturity governance attention severity count across datasets."""

    severity: DatasetMaturityGovernanceAttentionSeverity
    count: int


@dataclass(frozen=True, slots=True)
class DatasetMaturityGovernanceSourceFallbackPolicyEffectCount:
    """Maturity governance count by active source fallback policy effect."""

    policy_id: str
    policy_status: str
    catalog_selected_source: str
    effective_selected_source: str
    count: int


@dataclass(frozen=True, slots=True)
class DatasetMaturityGovernanceItem:
    """Unified dataset maturity governance report item."""

    dataset_id: str
    current_maturity: str | None
    catalog_freshness_status: CatalogFreshnessStatus | None
    promotion_status: DatasetPromotionStatus
    active_maturity_promotion: bool
    has_maturity_warning: bool
    required_criteria: tuple[str, ...]
    satisfied_criteria: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    rejected_criteria: tuple[str, ...]
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatasetMaturityGovernanceAttentionItem:
    """Dataset governance item requiring operator attention."""

    dataset_id: str
    attention_reasons: tuple[DatasetMaturityGovernanceAttentionReason, ...]
    attention_severity: DatasetMaturityGovernanceAttentionSeverity
    dataset: DatasetMaturityGovernanceItem


@dataclass(frozen=True, slots=True)
class DatasetMaturityGovernanceReport:
    """Unified backend maturity governance report."""

    dataset_count: int
    warning_count: int
    promotable_count: int
    active_promotion_count: int
    revoked_promotion_count: int
    maturity_summary: tuple[DatasetMaturitySummary, ...]
    promotion_status_counts: tuple[DatasetPromotionStatusCount, ...]
    missing_criteria_counts: tuple[DatasetPromotionCriterionCount, ...]
    rejected_criteria_counts: tuple[DatasetPromotionCriterionCount, ...]
    datasets: tuple[DatasetMaturityGovernanceItem, ...]
    attention_reason_counts: tuple[
        DatasetMaturityGovernanceAttentionReasonCount, ...
    ] = ()
    attention_severity_counts: tuple[
        DatasetMaturityGovernanceAttentionSeverityCount, ...
    ] = ()
    source_fallback_policy_effect_counts: tuple[
        DatasetMaturityGovernanceSourceFallbackPolicyEffectCount, ...
    ] = ()
    attention_required: tuple[DatasetMaturityGovernanceAttentionItem, ...] = ()


def build_maturity_governance_report(
    *,
    statuses: list[DatasetStatus],
    readiness_report: DatasetPromotionReadinessReport,
    maturity_summary: tuple[DatasetMaturitySummary, ...],
    source_fallback_policy_effect_counts: tuple[
        DatasetMaturityGovernanceSourceFallbackPolicyEffectCount, ...
    ] = (),
) -> DatasetMaturityGovernanceReport:
    """Build the unified maturity governance report from existing read models."""
    readiness_by_dataset: dict[str, DatasetPromotionReadinessItem] = {
        item.dataset_id: item for item in readiness_report.datasets
    }
    items = tuple(
        _maturity_governance_item(
            status,
            readiness_by_dataset.get(status.dataset),
        )
        for status in statuses
    )
    attention_required = _maturity_governance_attention_required(items)
    return DatasetMaturityGovernanceReport(
        dataset_count=len(items),
        warning_count=sum(1 for item in items if item.has_maturity_warning),
        promotable_count=readiness_report.promotable_count,
        active_promotion_count=readiness_report.active_promotion_count,
        revoked_promotion_count=sum(
            1 for item in items if item.latest_revocation_reason is not None
        ),
        maturity_summary=maturity_summary,
        promotion_status_counts=readiness_report.status_counts,
        missing_criteria_counts=readiness_report.missing_criteria_counts,
        rejected_criteria_counts=readiness_report.rejected_criteria_counts,
        datasets=items,
        attention_reason_counts=_maturity_governance_attention_reason_counts(
            attention_required
        ),
        attention_severity_counts=_maturity_governance_attention_severity_counts(
            attention_required
        ),
        source_fallback_policy_effect_counts=source_fallback_policy_effect_counts,
        attention_required=attention_required,
    )


def _maturity_governance_item(
    status: DatasetStatus,
    readiness: DatasetPromotionReadinessItem | None,
) -> DatasetMaturityGovernanceItem:
    return DatasetMaturityGovernanceItem(
        dataset_id=status.dataset,
        current_maturity=readiness.current_maturity
        if readiness is not None
        else status.dataset_maturity,
        catalog_freshness_status=status.catalog_freshness_status,
        promotion_status=readiness.promotion_status
        if readiness is not None
        else "not_applicable",
        active_maturity_promotion=readiness.active_maturity_promotion
        if readiness is not None
        else False,
        has_maturity_warning=status.dataset_maturity_warning is not None,
        latest_revocation_reason=status.latest_revocation_reason,
        latest_revoked_by=status.latest_revoked_by,
        latest_revoked_at=status.latest_revoked_at,
        required_criteria=readiness.required_criteria
        if readiness is not None
        else status.dataset_promotion_criteria,
        satisfied_criteria=readiness.satisfied_criteria
        if readiness is not None
        else status.dataset_promotion_satisfied_criteria,
        missing_criteria=readiness.missing_criteria
        if readiness is not None
        else status.dataset_promotion_missing_criteria,
        rejected_criteria=readiness.rejected_criteria
        if readiness is not None
        else status.dataset_promotion_rejected_criteria,
    )


def _maturity_governance_attention_required(
    items: tuple[DatasetMaturityGovernanceItem, ...],
) -> tuple[DatasetMaturityGovernanceAttentionItem, ...]:
    attention: list[DatasetMaturityGovernanceAttentionItem] = []
    for item in items:
        reasons = _maturity_governance_attention_reasons(item)
        if not reasons:
            continue
        attention.append(
            DatasetMaturityGovernanceAttentionItem(
                dataset_id=item.dataset_id,
                attention_reasons=reasons,
                attention_severity=_maturity_governance_attention_severity(reasons),
                dataset=item,
            )
        )
    return tuple(attention)


def _maturity_governance_attention_reasons(
    item: DatasetMaturityGovernanceItem,
) -> tuple[DatasetMaturityGovernanceAttentionReason, ...]:
    reasons: list[DatasetMaturityGovernanceAttentionReason] = []
    if item.has_maturity_warning:
        reasons.append("maturity_warning")
    if item.catalog_freshness_status == "stale":
        reasons.append("catalog_stale")
    elif item.catalog_freshness_status == "missing":
        reasons.append("catalog_missing")
    if item.promotion_status == "ready" and not item.active_maturity_promotion:
        reasons.append("promotion_ready")
    if item.promotion_status == "blocked":
        reasons.append("promotion_blocked")
    if item.latest_revocation_reason is not None:
        reasons.append("promotion_revoked")
    return tuple(reasons)


def _maturity_governance_attention_reason_counts(
    attention_required: tuple[DatasetMaturityGovernanceAttentionItem, ...],
) -> tuple[DatasetMaturityGovernanceAttentionReasonCount, ...]:
    counts: dict[DatasetMaturityGovernanceAttentionReason, int] = {}
    for item in attention_required:
        for reason in item.attention_reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return tuple(
        DatasetMaturityGovernanceAttentionReasonCount(
            reason=reason,
            count=counts[reason],
        )
        for reason in sorted(counts)
    )


def _maturity_governance_attention_severity_counts(
    attention_required: tuple[DatasetMaturityGovernanceAttentionItem, ...],
) -> tuple[DatasetMaturityGovernanceAttentionSeverityCount, ...]:
    severity_order: tuple[DatasetMaturityGovernanceAttentionSeverity, ...] = (
        "critical",
        "warning",
        "info",
    )
    counts: dict[DatasetMaturityGovernanceAttentionSeverity, int] = dict.fromkeys(
        severity_order,
        0,
    )
    for item in attention_required:
        counts[item.attention_severity] += 1
    return tuple(
        DatasetMaturityGovernanceAttentionSeverityCount(
            severity=severity,
            count=counts[severity],
        )
        for severity in severity_order
    )


def _maturity_governance_attention_severity(
    reasons: tuple[DatasetMaturityGovernanceAttentionReason, ...],
) -> DatasetMaturityGovernanceAttentionSeverity:
    critical_reasons: frozenset[DatasetMaturityGovernanceAttentionReason] = frozenset(
        {
            "catalog_stale",
            "catalog_missing",
            "promotion_blocked",
            "promotion_revoked",
        }
    )
    if any(reason in critical_reasons for reason in reasons):
        return "critical"
    if "maturity_warning" in reasons:
        return "warning"
    return "info"
