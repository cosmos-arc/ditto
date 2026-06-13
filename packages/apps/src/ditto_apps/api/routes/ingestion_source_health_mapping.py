"""Source-health API response mapping helpers."""

from __future__ import annotations

from ditto_application.queries.catalog import (
    CatalogSourceFallbackPolicyActionCount,
    CatalogSourceFallbackPolicyEffect,
    CatalogSourceFallbackPolicyPreview,
    CatalogSourceFallbackPolicyStatusCount,
    CatalogSourceFallbackPolicySummaryReport,
    CatalogSourceHealth,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthAttentionReasonCount,
    CatalogSourceHealthAttentionSeverityCount,
    CatalogSourceHealthReport,
    CatalogSourceHealthStatusCount,
    CatalogSourceHealthSummaryReport,
    CatalogSourceSelectionCount,
    CatalogSourceSelectionStatusCount,
)

from ditto_apps.models.ingestion import (
    CatalogSourceFallbackPolicyEffectResponse,
    CatalogSourceHealthAttentionItemResponse,
    CatalogSourceHealthAttentionReasonCountResponse,
    CatalogSourceHealthAttentionSeverityCountResponse,
    CatalogSourceHealthReportResponse,
    CatalogSourceHealthResponse,
    CatalogSourceHealthStatusCountResponse,
    CatalogSourceHealthSummaryReportResponse,
    CatalogSourceSelectionCountResponse,
    CatalogSourceSelectionStatusCountResponse,
)
from ditto_apps.models.source_fallback import (
    CatalogSourceFallbackPolicyActionCountResponse,
    CatalogSourceFallbackPolicyPreviewResponse,
    CatalogSourceFallbackPolicyStatusCountResponse,
    CatalogSourceFallbackPolicySummaryResponse,
)


def to_catalog_source_fallback_policy_preview_response(
    preview: CatalogSourceFallbackPolicyPreview,
) -> CatalogSourceFallbackPolicyPreviewResponse:
    """Map application fallback-policy preview DTO to API response model."""
    return CatalogSourceFallbackPolicyPreviewResponse(
        dataset_id=preview.dataset_id,
        namespace=preview.namespace,
        trade_date=preview.trade_date,
        default_source=preview.default_source,
        selected_source=preview.selected_source,
        recommended_source=preview.recommended_source,
        selected_freshness_status=preview.selected_freshness_status,
        policy_status=preview.policy_status,
        recommended_actions=list(preview.recommended_actions),
        approval_required=preview.approval_required,
        execution_allowed=preview.execution_allowed,
        reason_codes=list(preview.reason_codes),
        fallback_sources=list(preview.fallback_sources),
        unsupported_sources=list(preview.unsupported_sources),
        source_selection_status=preview.source_selection_status,
        source_selection_blockers=list(preview.source_selection_blockers),
        latest_revocation_reason=preview.latest_revocation_reason,
    )


def _to_catalog_source_fallback_policy_status_count_response(
    item: CatalogSourceFallbackPolicyStatusCount,
) -> CatalogSourceFallbackPolicyStatusCountResponse:
    return CatalogSourceFallbackPolicyStatusCountResponse(
        status=item.status,
        count=item.count,
    )


def _to_catalog_source_fallback_policy_action_count_response(
    item: CatalogSourceFallbackPolicyActionCount,
) -> CatalogSourceFallbackPolicyActionCountResponse:
    return CatalogSourceFallbackPolicyActionCountResponse(
        action=item.action,
        count=item.count,
    )


def to_catalog_source_fallback_policy_summary_response(
    report: CatalogSourceFallbackPolicySummaryReport,
) -> CatalogSourceFallbackPolicySummaryResponse:
    """Map application fallback-policy summary DTO to API response model."""
    return CatalogSourceFallbackPolicySummaryResponse(
        dataset_ids=list(report.dataset_ids),
        trade_dates=list(report.trade_dates),
        available_sources=list(report.available_sources),
        total_previews=report.total_previews,
        approval_required_count=report.approval_required_count,
        execution_allowed_count=report.execution_allowed_count,
        policy_status_counts=[
            _to_catalog_source_fallback_policy_status_count_response(item)
            for item in report.policy_status_counts
        ],
        recommended_action_counts=[
            _to_catalog_source_fallback_policy_action_count_response(item)
            for item in report.recommended_action_counts
        ],
        previews=[
            to_catalog_source_fallback_policy_preview_response(item)
            for item in report.previews
        ],
    )


def to_catalog_source_health_response(
    item: CatalogSourceHealth,
) -> CatalogSourceHealthResponse:
    """Map application source-health DTO to API response model."""
    return CatalogSourceHealthResponse(
        source=item.source,
        supported=item.supported,
        freshness_status=item.freshness_status,
        freshness_sla_hours=item.freshness_sla_hours,
        freshness_at=item.freshness_at.isoformat()
        if item.freshness_at is not None
        else None,
        storage_uri=item.storage_uri,
        schema_hash=item.schema_hash,
        row_count=item.row_count,
    )


def _to_catalog_source_fallback_policy_effect_response(
    effect: CatalogSourceFallbackPolicyEffect | None,
) -> CatalogSourceFallbackPolicyEffectResponse | None:
    if effect is None:
        return None
    return CatalogSourceFallbackPolicyEffectResponse(
        policy_id=effect.policy_id,
        policy_status=effect.policy_status,
        catalog_selected_source=effect.catalog_selected_source,
        effective_selected_source=effect.effective_selected_source,
        reason_codes=list(effect.reason_codes),
        recommended_actions=list(effect.recommended_actions),
    )


def to_catalog_source_health_report_response(
    report: CatalogSourceHealthReport,
) -> CatalogSourceHealthReportResponse:
    """Map application source-health report DTO to API response model."""
    return CatalogSourceHealthReportResponse(
        dataset_id=report.dataset_id,
        namespace=report.namespace,
        trade_date=report.trade_date,
        default_source=report.default_source,
        selected_source=report.selected_source,
        selected_freshness_status=report.selected_freshness_status,
        selected_source_health=to_catalog_source_health_response(
            report.selected_source_health
        ),
        source_fallback_policy_effect=(
            _to_catalog_source_fallback_policy_effect_response(
                report.source_fallback_policy_effect
            )
        ),
        source_selection_status=report.source_selection_status,
        source_selection_blockers=list(report.source_selection_blockers),
        attention_reasons=list(report.attention_reasons),
        sources=[
            to_catalog_source_health_response(source) for source in report.sources
        ],
        unsupported_sources=list(report.unsupported_sources),
        failover_from_default=report.failover_from_default,
        fallback_sources=list(report.fallback_sources),
        latest_revocation_reason=report.latest_revocation_reason,
        latest_revoked_by=report.latest_revoked_by,
        latest_revoked_at=report.latest_revoked_at.isoformat()
        if report.latest_revoked_at is not None
        else None,
    )


def _to_catalog_source_health_status_count_response(
    item: CatalogSourceHealthStatusCount,
) -> CatalogSourceHealthStatusCountResponse:
    return CatalogSourceHealthStatusCountResponse(
        status=item.status,
        count=item.count,
    )


def _to_catalog_source_selection_count_response(
    item: CatalogSourceSelectionCount,
) -> CatalogSourceSelectionCountResponse:
    return CatalogSourceSelectionCountResponse(
        source=item.source,
        count=item.count,
    )


def _to_catalog_source_selection_status_count_response(
    item: CatalogSourceSelectionStatusCount,
) -> CatalogSourceSelectionStatusCountResponse:
    return CatalogSourceSelectionStatusCountResponse(
        status=item.status,
        count=item.count,
    )


def _to_catalog_source_health_attention_reason_count_response(
    item: CatalogSourceHealthAttentionReasonCount,
) -> CatalogSourceHealthAttentionReasonCountResponse:
    return CatalogSourceHealthAttentionReasonCountResponse(
        reason=item.reason,
        count=item.count,
    )


def _to_catalog_source_health_attention_severity_count_response(
    item: CatalogSourceHealthAttentionSeverityCount,
) -> CatalogSourceHealthAttentionSeverityCountResponse:
    return CatalogSourceHealthAttentionSeverityCountResponse(
        severity=item.severity,
        count=item.count,
    )


def _to_catalog_source_health_attention_response(
    item: CatalogSourceHealthAttentionItem,
) -> CatalogSourceHealthAttentionItemResponse:
    return CatalogSourceHealthAttentionItemResponse(
        dataset_id=item.dataset_id,
        namespace=item.namespace,
        trade_date=item.trade_date,
        default_source=item.default_source,
        selected_source=item.selected_source,
        selected_freshness_status=item.selected_freshness_status,
        selected_source_health=to_catalog_source_health_response(
            item.selected_source_health
        ),
        source_fallback_policy_effect=(
            _to_catalog_source_fallback_policy_effect_response(
                item.source_fallback_policy_effect
            )
        ),
        source_selection_status=item.source_selection_status,
        source_selection_blockers=list(item.source_selection_blockers),
        attention_reasons=list(item.attention_reasons),
        attention_severity=item.attention_severity,
        unsupported_sources=list(item.unsupported_sources),
        failover_from_default=item.failover_from_default,
        fallback_sources=list(item.fallback_sources),
        latest_revocation_reason=item.latest_revocation_reason,
        latest_revoked_by=item.latest_revoked_by,
        latest_revoked_at=item.latest_revoked_at.isoformat()
        if item.latest_revoked_at is not None
        else None,
    )


def to_catalog_source_health_summary_report_response(
    report: CatalogSourceHealthSummaryReport,
) -> CatalogSourceHealthSummaryReportResponse:
    """Map application source-health summary DTO to API response model."""
    return CatalogSourceHealthSummaryReportResponse(
        dataset_ids=list(report.dataset_ids),
        trade_dates=list(report.trade_dates),
        available_sources=list(report.available_sources),
        total_reports=report.total_reports,
        failover_count=report.failover_count,
        no_fallback_source_count=report.no_fallback_source_count,
        revoked_promotion_count=report.revoked_promotion_count,
        status_counts=[
            _to_catalog_source_health_status_count_response(item)
            for item in report.status_counts
        ],
        selected_source_counts=[
            _to_catalog_source_selection_count_response(item)
            for item in report.selected_source_counts
        ],
        source_selection_status_counts=[
            _to_catalog_source_selection_status_count_response(item)
            for item in report.source_selection_status_counts
        ],
        fallback_source_counts=[
            _to_catalog_source_selection_count_response(item)
            for item in report.fallback_source_counts
        ],
        attention_reason_counts=[
            _to_catalog_source_health_attention_reason_count_response(item)
            for item in report.attention_reason_counts
        ],
        attention_severity_counts=[
            _to_catalog_source_health_attention_severity_count_response(item)
            for item in report.attention_severity_counts
        ],
        attention_required=[
            _to_catalog_source_health_attention_response(item)
            for item in report.attention_required
        ],
        reports=[
            to_catalog_source_health_report_response(item) for item in report.reports
        ],
    )
