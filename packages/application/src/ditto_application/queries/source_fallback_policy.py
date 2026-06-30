"""Read-only fallback policy preview for catalog source-health reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ditto_application.queries.catalog_source_health import CatalogSourceHealthReport

type CatalogSourceFallbackPolicyStatus = Literal[
    "ready",
    "review_required",
    "blocked",
]
type CatalogSourceFallbackPolicyAction = Literal[
    "keep_default_source",
    "use_selected_source",
    "repair_catalog_source_coverage",
    "review_source_failover",
    "configure_fallback_source",
    "review_source_request",
    "review_maturity_governance",
]


@dataclass(frozen=True)
class CatalogSourceFallbackPolicyStatusCount:
    """Aggregated fallback-policy preview count by status."""

    status: CatalogSourceFallbackPolicyStatus
    count: int


@dataclass(frozen=True)
class CatalogSourceFallbackPolicyActionCount:
    """Aggregated fallback-policy preview count by recommended action."""

    action: CatalogSourceFallbackPolicyAction
    count: int


@dataclass(frozen=True)
class CatalogSourceFallbackPolicyPreview:
    """Backend-owned dry-run decision for source fallback policy review."""

    dataset_id: str
    namespace: str
    trade_date: str
    default_source: str
    selected_source: str
    recommended_source: str | None
    selected_freshness_status: str
    policy_status: CatalogSourceFallbackPolicyStatus
    recommended_actions: tuple[CatalogSourceFallbackPolicyAction, ...]
    approval_required: bool
    execution_allowed: bool
    reason_codes: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    unsupported_sources: tuple[str, ...]
    source_selection_status: str
    source_selection_blockers: tuple[str, ...]
    latest_revocation_reason: str | None = None


@dataclass(frozen=True)
class CatalogSourceFallbackPolicySummaryReport:
    """Aggregated backend fallback-policy preview across datasets/dates."""

    dataset_ids: tuple[str, ...]
    trade_dates: tuple[str, ...]
    available_sources: tuple[str, ...]
    total_previews: int
    approval_required_count: int
    execution_allowed_count: int
    policy_status_counts: tuple[CatalogSourceFallbackPolicyStatusCount, ...]
    recommended_action_counts: tuple[CatalogSourceFallbackPolicyActionCount, ...]
    previews: tuple[CatalogSourceFallbackPolicyPreview, ...]


def build_source_fallback_policy_preview(
    report: CatalogSourceHealthReport,
) -> CatalogSourceFallbackPolicyPreview:
    """Build a read-only fallback policy decision from source-health evidence."""
    reason_codes = _dedupe(
        (*report.attention_reasons, *report.source_selection_blockers)
    )
    if report.source_selection_status == "blocked":
        return _preview(
            report,
            policy_status="blocked",
            recommended_source=None,
            recommended_actions=("configure_fallback_source", "review_source_request"),
            approval_required=True,
            execution_allowed=False,
            reason_codes=reason_codes,
        )

    recommended_actions = _recommended_actions(report)
    if not recommended_actions:
        recommended_actions = (
            "keep_default_source"
            if report.selected_source == report.default_source
            else "use_selected_source",
        )
        return _preview(
            report,
            policy_status="ready",
            recommended_source=report.selected_source,
            recommended_actions=recommended_actions,
            approval_required=False,
            execution_allowed=True,
            reason_codes=reason_codes,
        )

    return _preview(
        report,
        policy_status="review_required",
        recommended_source=report.selected_source,
        recommended_actions=recommended_actions,
        approval_required=True,
        execution_allowed=True,
        reason_codes=reason_codes,
    )


def build_source_fallback_policy_summary(
    *,
    dataset_ids: tuple[str, ...],
    trade_dates: tuple[str, ...],
    available_sources: tuple[str, ...],
    previews: tuple[CatalogSourceFallbackPolicyPreview, ...],
) -> CatalogSourceFallbackPolicySummaryReport:
    """Aggregate fallback-policy preview decisions for backend consumers."""
    return CatalogSourceFallbackPolicySummaryReport(
        dataset_ids=dataset_ids,
        trade_dates=trade_dates,
        available_sources=available_sources,
        total_previews=len(previews),
        approval_required_count=sum(1 for item in previews if item.approval_required),
        execution_allowed_count=sum(1 for item in previews if item.execution_allowed),
        policy_status_counts=_policy_status_counts(previews),
        recommended_action_counts=_recommended_action_counts(previews),
        previews=previews,
    )


def _recommended_actions(
    report: CatalogSourceHealthReport,
) -> tuple[CatalogSourceFallbackPolicyAction, ...]:
    actions: list[CatalogSourceFallbackPolicyAction] = []
    if report.selected_freshness_status != "fresh":
        actions.append("repair_catalog_source_coverage")
    if report.failover_from_default:
        actions.append("review_source_failover")
    if report.selected_freshness_status != "fresh" and not report.fallback_sources:
        actions.append("configure_fallback_source")
    if report.unsupported_sources:
        actions.append("review_source_request")
    if report.latest_revocation_reason is not None:
        actions.append("review_maturity_governance")
    return _dedupe(tuple(actions))


def _preview(
    report: CatalogSourceHealthReport,
    *,
    policy_status: CatalogSourceFallbackPolicyStatus,
    recommended_source: str | None,
    recommended_actions: tuple[CatalogSourceFallbackPolicyAction, ...],
    approval_required: bool,
    execution_allowed: bool,
    reason_codes: tuple[str, ...],
) -> CatalogSourceFallbackPolicyPreview:
    return CatalogSourceFallbackPolicyPreview(
        dataset_id=report.dataset_id,
        namespace=report.namespace,
        trade_date=report.trade_date,
        default_source=report.default_source,
        selected_source=report.selected_source,
        recommended_source=recommended_source,
        selected_freshness_status=report.selected_freshness_status,
        policy_status=policy_status,
        recommended_actions=recommended_actions,
        approval_required=approval_required,
        execution_allowed=execution_allowed,
        reason_codes=reason_codes,
        fallback_sources=report.fallback_sources,
        unsupported_sources=report.unsupported_sources,
        source_selection_status=report.source_selection_status,
        source_selection_blockers=report.source_selection_blockers,
        latest_revocation_reason=report.latest_revocation_reason,
    )


def _policy_status_counts(
    previews: tuple[CatalogSourceFallbackPolicyPreview, ...],
) -> tuple[CatalogSourceFallbackPolicyStatusCount, ...]:
    status_order: tuple[CatalogSourceFallbackPolicyStatus, ...] = (
        "ready",
        "review_required",
        "blocked",
    )
    counts = dict.fromkeys(status_order, 0)
    for preview in previews:
        counts[preview.policy_status] += 1
    return tuple(
        CatalogSourceFallbackPolicyStatusCount(
            status=status,
            count=counts[status],
        )
        for status in status_order
    )


def _recommended_action_counts(
    previews: tuple[CatalogSourceFallbackPolicyPreview, ...],
) -> tuple[CatalogSourceFallbackPolicyActionCount, ...]:
    action_order: tuple[CatalogSourceFallbackPolicyAction, ...] = (
        "keep_default_source",
        "use_selected_source",
        "repair_catalog_source_coverage",
        "review_source_failover",
        "configure_fallback_source",
        "review_source_request",
        "review_maturity_governance",
    )
    counts = dict.fromkeys(action_order, 0)
    for preview in previews:
        for action in preview.recommended_actions:
            counts[action] += 1
    return tuple(
        CatalogSourceFallbackPolicyActionCount(
            action=action,
            count=counts[action],
        )
        for action in action_order
        if counts[action] > 0
    )


def _dedupe[T](values: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(values))
