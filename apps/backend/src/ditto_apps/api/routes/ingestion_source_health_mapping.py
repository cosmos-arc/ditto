"""Source-health API response mapping helpers."""

from __future__ import annotations

from ditto_application.queries.catalog import (
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
        source_selection_status=report.source_selection_status,
        source_selection_blockers=list(report.source_selection_blockers),
        attention_reasons=list(report.attention_reasons),
        sources=[
            to_catalog_source_health_response(source) for source in report.sources
        ],
        unsupported_sources=list(report.unsupported_sources),
        failover_from_default=report.failover_from_default,
        fallback_sources=list(report.fallback_sources),
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
        source_selection_status=item.source_selection_status,
        source_selection_blockers=list(item.source_selection_blockers),
        attention_reasons=list(item.attention_reasons),
        attention_severity=item.attention_severity,
        unsupported_sources=list(item.unsupported_sources),
        failover_from_default=item.failover_from_default,
        fallback_sources=list(item.fallback_sources),
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
