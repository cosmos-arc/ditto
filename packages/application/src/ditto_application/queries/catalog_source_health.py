"""Source-health DTOs and pure rollup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog.promotion import DatasetMaturityPromotionRevocationReason

from ditto_application.catalog_freshness import CatalogFreshnessStatus
from ditto_application.source_fallback_policy_effect import SourceFallbackPolicyEffect

type CatalogSourceHealthAttentionReason = Literal[
    "selected_source_missing",
    "selected_source_stale",
    "selected_source_not_applicable",
    "default_source_failover",
    "no_fallback_source",
    "unsupported_sources_present",
    "latest_maturity_promotion_revoked",
]

type CatalogSourceHealthAttentionSeverity = Literal["critical", "warning", "info"]
type CatalogSourceSelectionBlocker = Literal["selected_source_unsupported"]
type CatalogSourceSelectionStatus = Literal["ready", "blocked"]


@dataclass(frozen=True)
class CatalogSourceHealth:
    """Per-source catalog freshness evidence for one dataset/date."""

    source: str
    supported: bool
    freshness_status: CatalogFreshnessStatus
    freshness_sla_hours: int | None
    freshness_at: datetime | None = None
    storage_uri: str | None = None
    schema_hash: str | None = None
    row_count: int | None = None


@dataclass(frozen=True)
class CatalogSourceFallbackPolicyEffect:
    """Application-facing active source fallback policy effect evidence."""

    policy_id: str
    policy_status: str
    catalog_selected_source: str
    effective_selected_source: str
    reason_codes: tuple[str, ...]
    recommended_actions: tuple[str, ...]


@dataclass(frozen=True)
class CatalogSourceHealthReport:
    """Application-facing source health report for `source=auto` decisions."""

    dataset_id: str
    namespace: str
    trade_date: str
    default_source: str
    selected_source: str
    selected_freshness_status: CatalogFreshnessStatus
    selected_source_health: CatalogSourceHealth
    source_selection_status: CatalogSourceSelectionStatus
    source_selection_blockers: tuple[CatalogSourceSelectionBlocker, ...]
    attention_reasons: tuple[CatalogSourceHealthAttentionReason, ...]
    sources: tuple[CatalogSourceHealth, ...]
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffect | None = None
    unsupported_sources: tuple[str, ...] = ()
    failover_from_default: bool = False
    fallback_sources: tuple[str, ...] = ()
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None


@dataclass(frozen=True)
class CatalogSourceHealthStatusCount:
    """Aggregated freshness status count across source-health reports."""

    status: CatalogFreshnessStatus
    count: int


@dataclass(frozen=True)
class CatalogSourceSelectionCount:
    """Aggregated selected-source count across source-health reports."""

    source: str
    count: int


@dataclass(frozen=True)
class CatalogSourceSelectionStatusCount:
    """Aggregated source-selection readiness count across reports."""

    status: CatalogSourceSelectionStatus
    count: int


@dataclass(frozen=True)
class CatalogSourceHealthAttentionReasonCount:
    """Aggregated attention reason count across source-health reports."""

    reason: CatalogSourceHealthAttentionReason
    count: int


@dataclass(frozen=True)
class CatalogSourceHealthAttentionSeverityCount:
    """Aggregated attention severity count across source-health reports."""

    severity: CatalogSourceHealthAttentionSeverity
    count: int


@dataclass(frozen=True)
class CatalogSourceHealthAttentionItem:
    """One source-health summary item that needs operator attention."""

    dataset_id: str
    namespace: str
    trade_date: str
    default_source: str
    selected_source: str
    selected_freshness_status: CatalogFreshnessStatus
    selected_source_health: CatalogSourceHealth
    attention_reasons: tuple[CatalogSourceHealthAttentionReason, ...]
    attention_severity: CatalogSourceHealthAttentionSeverity
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffect | None = None
    source_selection_status: CatalogSourceSelectionStatus = "ready"
    source_selection_blockers: tuple[CatalogSourceSelectionBlocker, ...] = ()
    unsupported_sources: tuple[str, ...] = ()
    failover_from_default: bool = False
    fallback_sources: tuple[str, ...] = ()
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None


@dataclass(frozen=True)
class CatalogSourceHealthSummaryReport:
    """Aggregated source-health report for backend diagnostics."""

    dataset_ids: tuple[str, ...]
    trade_dates: tuple[str, ...]
    available_sources: tuple[str, ...]
    total_reports: int
    status_counts: tuple[CatalogSourceHealthStatusCount, ...]
    selected_source_counts: tuple[CatalogSourceSelectionCount, ...]
    attention_required: tuple[CatalogSourceHealthAttentionItem, ...]
    reports: tuple[CatalogSourceHealthReport, ...]
    source_selection_status_counts: tuple[CatalogSourceSelectionStatusCount, ...] = ()
    failover_count: int = 0
    no_fallback_source_count: int = 0
    revoked_promotion_count: int = 0
    fallback_source_counts: tuple[CatalogSourceSelectionCount, ...] = ()
    attention_reason_counts: tuple[CatalogSourceHealthAttentionReasonCount, ...] = ()
    attention_severity_counts: tuple[
        CatalogSourceHealthAttentionSeverityCount, ...
    ] = ()


def to_source_fallback_policy_effect(
    effect: SourceFallbackPolicyEffect | None,
) -> CatalogSourceFallbackPolicyEffect | None:
    """Map a resolved active policy effect to the source-health read model."""
    if effect is None:
        return None
    policy = effect.policy
    return CatalogSourceFallbackPolicyEffect(
        policy_id=policy.policy_id,
        policy_status=policy.status,
        catalog_selected_source=effect.catalog_selected_source,
        effective_selected_source=effect.effective_source,
        reason_codes=policy.reason_codes,
        recommended_actions=policy.recommended_actions,
    )


def source_health_status_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceHealthStatusCount, ...]:
    """Return fixed-order freshness status counts across reports."""
    counts: dict[CatalogFreshnessStatus, int] = {
        "fresh": 0,
        "stale": 0,
        "missing": 0,
        "not_applicable": 0,
    }
    for report in reports:
        for source in report.sources:
            counts[source.freshness_status] += 1
    return tuple(
        CatalogSourceHealthStatusCount(status=status, count=count)
        for status, count in counts.items()
    )


def selected_source_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceSelectionCount, ...]:
    """Return selected-source counts across source-health reports."""
    counts: dict[str, int] = {}
    for report in reports:
        counts[report.selected_source] = counts.get(report.selected_source, 0) + 1
    return tuple(
        CatalogSourceSelectionCount(source=source, count=counts[source])
        for source in sorted(counts)
    )


def source_selection_status_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceSelectionStatusCount, ...]:
    """Return fixed-order selected-source readiness counts."""
    counts: dict[CatalogSourceSelectionStatus, int] = {
        "ready": 0,
        "blocked": 0,
    }
    for report in reports:
        counts[report.source_selection_status] += 1
    return tuple(
        CatalogSourceSelectionStatusCount(status=status, count=counts[status])
        for status in counts
    )


def attention_required(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceHealthAttentionItem, ...]:
    """Return severity-ranked source-health attention items."""
    return tuple(
        CatalogSourceHealthAttentionItem(
            dataset_id=report.dataset_id,
            namespace=report.namespace,
            trade_date=report.trade_date,
            default_source=report.default_source,
            selected_source=report.selected_source,
            selected_freshness_status=status,
            selected_source_health=selected_source_health,
            attention_reasons=report.attention_reasons,
            attention_severity=source_health_attention_severity(
                report.attention_reasons
            ),
            source_fallback_policy_effect=report.source_fallback_policy_effect,
            source_selection_status=report.source_selection_status,
            source_selection_blockers=report.source_selection_blockers,
            unsupported_sources=report.unsupported_sources,
            failover_from_default=report.failover_from_default,
            fallback_sources=report.fallback_sources,
            latest_revocation_reason=report.latest_revocation_reason,
            latest_revoked_by=report.latest_revoked_by,
            latest_revoked_at=report.latest_revoked_at,
        )
        for report in reports
        for selected_source_health in (report.selected_source_health,)
        for status in (selected_source_health.freshness_status,)
        if report.attention_reasons
    )


def failover_count(reports: tuple[CatalogSourceHealthReport, ...]) -> int:
    """Return number of reports where selected source differs from default source."""
    return sum(1 for report in reports if report.failover_from_default)


def no_fallback_source_count(reports: tuple[CatalogSourceHealthReport, ...]) -> int:
    """Return number of reports without non-default fallback candidates."""
    return sum(1 for report in reports if not report.fallback_sources)


def revoked_promotion_count(reports: tuple[CatalogSourceHealthReport, ...]) -> int:
    """Return number of reports carrying latest promotion revocation context."""
    return sum(1 for report in reports if report.latest_revocation_reason is not None)


def fallback_source_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceSelectionCount, ...]:
    """Return counts for non-default fallback candidate sources."""
    counts: dict[str, int] = {}
    for report in reports:
        for source in report.fallback_sources:
            counts[source] = counts.get(source, 0) + 1
    return tuple(
        CatalogSourceSelectionCount(source=source, count=counts[source])
        for source in sorted(counts)
    )


def attention_reason_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceHealthAttentionReasonCount, ...]:
    """Return sorted attention reason counts across reports."""
    counts: dict[CatalogSourceHealthAttentionReason, int] = {}
    for report in reports:
        for reason in report.attention_reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return tuple(
        CatalogSourceHealthAttentionReasonCount(
            reason=reason,
            count=counts[reason],
        )
        for reason in sorted(counts)
    )


def attention_severity_counts(
    attention_items: tuple[CatalogSourceHealthAttentionItem, ...],
) -> tuple[CatalogSourceHealthAttentionSeverityCount, ...]:
    """Return fixed-order attention severity counts."""
    severity_order: tuple[CatalogSourceHealthAttentionSeverity, ...] = (
        "critical",
        "warning",
        "info",
    )
    counts = dict.fromkeys(severity_order, 0)
    for item in attention_items:
        counts[item.attention_severity] += 1
    return tuple(
        CatalogSourceHealthAttentionSeverityCount(
            severity=severity,
            count=counts[severity],
        )
        for severity in severity_order
    )


def source_health_for_source(
    sources: tuple[CatalogSourceHealth, ...],
    selected_source: str,
) -> CatalogSourceHealth:
    """Return selected source evidence, or an unsupported missing placeholder."""
    for source in sources:
        if source.source == selected_source:
            return source
    return CatalogSourceHealth(
        source=selected_source,
        supported=False,
        freshness_status="missing",
        freshness_sla_hours=None,
    )


def source_selection_blockers(
    selected_source_health: CatalogSourceHealth,
) -> tuple[CatalogSourceSelectionBlocker, ...]:
    """Return selected-source readiness blockers."""
    if not selected_source_health.supported:
        return ("selected_source_unsupported",)
    return ()


def source_health_attention_reasons(
    *,
    selected_freshness_status: CatalogFreshnessStatus,
    failover_from_default: bool,
    fallback_sources: tuple[str, ...],
    unsupported_sources: tuple[str, ...],
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None,
) -> tuple[CatalogSourceHealthAttentionReason, ...]:
    """Return stable source-health attention reason codes."""
    reasons: list[CatalogSourceHealthAttentionReason] = []
    if selected_freshness_status == "stale":
        reasons.append("selected_source_stale")
    elif selected_freshness_status == "missing":
        reasons.append("selected_source_missing")
    elif selected_freshness_status == "not_applicable":
        reasons.append("selected_source_not_applicable")

    if failover_from_default:
        reasons.append("default_source_failover")
    if selected_freshness_status != "fresh" and not fallback_sources:
        reasons.append("no_fallback_source")
    if unsupported_sources:
        reasons.append("unsupported_sources_present")
    if latest_revocation_reason is not None:
        reasons.append("latest_maturity_promotion_revoked")
    return tuple(reasons)


def source_health_attention_severity(
    reasons: tuple[CatalogSourceHealthAttentionReason, ...],
) -> CatalogSourceHealthAttentionSeverity:
    """Return the highest source-health attention severity for reason codes."""
    critical_reasons: frozenset[CatalogSourceHealthAttentionReason] = frozenset(
        {
            "selected_source_missing",
            "selected_source_stale",
            "selected_source_not_applicable",
            "latest_maturity_promotion_revoked",
        }
    )
    warning_reasons: frozenset[CatalogSourceHealthAttentionReason] = frozenset(
        {
            "default_source_failover",
            "no_fallback_source",
        }
    )
    if any(reason in critical_reasons for reason in reasons):
        return "critical"
    if any(reason in warning_reasons for reason in reasons):
        return "warning"
    return "info"
