"""
数据摄取状态 API 路由.

maturity: infrastructure
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.catalog import (
    DatasetMaturityPromotionRevokeCommand,
    DatasetPromotionReviewCommand,
    ReviewDatasetPromotionEvidenceHandler,
    RevokeDatasetMaturityPromotionHandler,
)
from ditto_application.config import get_all_datasets
from ditto_application.queries.catalog import (
    CatalogAsset,
    CatalogMaturityPromotionHistoryItem,
    CatalogQueryFacade,
)
from ditto_application.queries.ingestion_status import (
    DatasetMaturityGovernanceAttentionItem,
    DatasetMaturityGovernanceAttentionReasonCount,
    DatasetMaturityGovernanceAttentionSeverityCount,
    DatasetMaturityGovernanceItem,
    DatasetMaturityGovernanceReport,
    DatasetMaturityGovernanceSourceFallbackPolicyEffectCount,
    DatasetPromotionCriterionCount,
    DatasetPromotionReadinessItem,
    DatasetPromotionReadinessReport,
    DatasetPromotionReadinessSourceFallbackPolicyEffectCount,
    DatasetPromotionStatusCount,
    IngestionStatusQueryFacade,
    summarize_status_by_maturity,
)
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import NotFoundError
from ditto_apps.api.routes.ingestion_remediation import router as _remediation_router
from ditto_apps.api.routes.ingestion_source_fallback_policy import (
    router as _source_fallback_policy_router,
)
from ditto_apps.api.routes.ingestion_source_health_mapping import (
    to_catalog_source_fallback_policy_preview_response,
    to_catalog_source_fallback_policy_summary_response,
    to_catalog_source_health_report_response,
    to_catalog_source_health_summary_report_response,
)
from ditto_apps.models.common import APIResponse, PaginationRequest
from ditto_apps.models.ingestion import (
    CatalogAssetRefResponse,
    CatalogAssetResponse,
    CatalogSchemaResponse,
    CatalogSourceHealthReportResponse,
    CatalogSourceHealthSummaryReportResponse,
    DatasetMaturitySummaryResponse,
    DatasetStatusResponse,
    DQSummaryResponse,
    IngestionHistoryItem,
    IngestionStatusResponse,
    MaturityPromotionHistoryItem,
    MaturityPromotionRevokeRequest,
    MaturityPromotionRevokeResponse,
    PromotionCriterionCountResponse,
    PromotionEvidenceReviewRequest,
    PromotionEvidenceReviewResponse,
    PromotionReadinessItemResponse,
    PromotionReadinessReportResponse,
    PromotionReadinessSourceFallbackPolicyEffectCountResponse,
    PromotionStatusCountResponse,
)
from ditto_apps.models.maturity_governance import (
    MaturityGovernanceAttentionItemResponse,
    MaturityGovernanceAttentionReasonCountResponse,
    MaturityGovernanceAttentionSeverityCountResponse,
    MaturityGovernanceDatasetResponse,
    MaturityGovernanceReportResponse,
    MaturityGovernanceSourceFallbackPolicyEffectCountResponse,
)
from ditto_apps.models.source_fallback import (
    CatalogSourceFallbackPolicyPreviewResponse,
    CatalogSourceFallbackPolicySummaryResponse,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
router.include_router(_remediation_router)
router.include_router(_source_fallback_policy_router)


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


# 从 Dataset StrEnum 派生，保证单一事实来源
_KNOWN_DATASETS = [dataset.value for dataset in get_all_datasets()]


def to_catalog_asset_response(asset: CatalogAsset) -> CatalogAssetResponse:
    """Map application catalog DTO to API response model."""
    return CatalogAssetResponse(
        asset=CatalogAssetRefResponse(
            dataset_id=asset.asset.dataset_id,
            namespace=asset.asset.namespace,
            partition_keys=list(asset.asset.partition_keys),
        ),
        storage_uri=asset.storage_uri,
        schema_fingerprint=CatalogSchemaResponse(
            schema_hash=asset.schema.schema_hash,
            row_count=asset.schema.row_count,
            created_at=asset.schema.created_at.isoformat()
            if asset.schema.created_at is not None
            else None,
        ),
        source=asset.source,
        freshness_at=asset.freshness_at.isoformat(),
    )


def to_maturity_promotion_history_response(
    item: CatalogMaturityPromotionHistoryItem,
) -> MaturityPromotionHistoryItem:
    """Map application maturity promotion event DTO to API response model."""
    return MaturityPromotionHistoryItem(
        dataset_id=item.dataset_id,
        action=item.action,
        previous_maturity=item.previous_maturity,
        next_maturity=item.next_maturity,
        actor=item.actor,
        action_at=item.action_at.isoformat() if item.action_at is not None else None,
        evidence_uri=item.evidence_uri,
        revocation_reason=item.revocation_reason,
        notes=item.notes,
    )


def to_promotion_status_count_response(
    item: DatasetPromotionStatusCount,
) -> PromotionStatusCountResponse:
    """Map application promotion status count DTO to API response model."""
    return PromotionStatusCountResponse(status=item.status, count=item.count)


def to_promotion_criterion_count_response(
    item: DatasetPromotionCriterionCount,
) -> PromotionCriterionCountResponse:
    """Map application promotion criterion count DTO to API response model."""
    return PromotionCriterionCountResponse(
        criterion=item.criterion,
        count=item.count,
    )


def to_promotion_readiness_source_fallback_policy_effect_count_response(
    item: DatasetPromotionReadinessSourceFallbackPolicyEffectCount,
) -> PromotionReadinessSourceFallbackPolicyEffectCountResponse:
    """Map promotion readiness source policy effect count to API response."""
    return PromotionReadinessSourceFallbackPolicyEffectCountResponse(
        policy_id=item.policy_id,
        policy_status=item.policy_status,
        catalog_selected_source=item.catalog_selected_source,
        effective_selected_source=item.effective_selected_source,
        count=item.count,
    )


def to_promotion_readiness_item_response(
    item: DatasetPromotionReadinessItem,
) -> PromotionReadinessItemResponse:
    """Map application promotion readiness item DTO to API response model."""
    return PromotionReadinessItemResponse(
        dataset_id=item.dataset_id,
        metadata_maturity=item.metadata_maturity,
        current_maturity=item.current_maturity,
        promotion_status=item.promotion_status,
        active_maturity_promotion=item.active_maturity_promotion,
        required_criteria=list(item.required_criteria),
        satisfied_criteria=list(item.satisfied_criteria),
        missing_criteria=list(item.missing_criteria),
        rejected_criteria=list(item.rejected_criteria),
        latest_revocation_reason=item.latest_revocation_reason,
        latest_revoked_by=item.latest_revoked_by,
        latest_revoked_at=item.latest_revoked_at.isoformat()
        if item.latest_revoked_at is not None
        else None,
    )


def to_promotion_readiness_report_response(
    report: DatasetPromotionReadinessReport,
) -> PromotionReadinessReportResponse:
    """Map application promotion readiness report DTO to API response model."""
    return PromotionReadinessReportResponse(
        dataset_count=report.dataset_count,
        promotable_count=report.promotable_count,
        active_promotion_count=report.active_promotion_count,
        status_counts=[
            to_promotion_status_count_response(item) for item in report.status_counts
        ],
        missing_criteria_counts=[
            to_promotion_criterion_count_response(item)
            for item in report.missing_criteria_counts
        ],
        rejected_criteria_counts=[
            to_promotion_criterion_count_response(item)
            for item in report.rejected_criteria_counts
        ],
        source_fallback_policy_effect_counts=[
            to_promotion_readiness_source_fallback_policy_effect_count_response(item)
            for item in report.source_fallback_policy_effect_counts
        ],
        datasets=[
            to_promotion_readiness_item_response(item) for item in report.datasets
        ],
    )


def to_maturity_governance_dataset_response(
    item: DatasetMaturityGovernanceItem,
) -> MaturityGovernanceDatasetResponse:
    """Map application maturity governance item to API response model."""
    return MaturityGovernanceDatasetResponse(
        dataset_id=item.dataset_id,
        current_maturity=item.current_maturity,
        catalog_freshness_status=item.catalog_freshness_status,
        promotion_status=item.promotion_status,
        active_maturity_promotion=item.active_maturity_promotion,
        has_maturity_warning=item.has_maturity_warning,
        required_criteria=list(item.required_criteria),
        satisfied_criteria=list(item.satisfied_criteria),
        latest_revocation_reason=item.latest_revocation_reason,
        latest_revoked_by=item.latest_revoked_by,
        latest_revoked_at=item.latest_revoked_at.isoformat()
        if item.latest_revoked_at is not None
        else None,
        missing_criteria=list(item.missing_criteria),
        rejected_criteria=list(item.rejected_criteria),
    )


def to_maturity_governance_attention_item_response(
    item: DatasetMaturityGovernanceAttentionItem,
) -> MaturityGovernanceAttentionItemResponse:
    """Map application maturity governance attention item to API response."""
    return MaturityGovernanceAttentionItemResponse(
        dataset_id=item.dataset_id,
        attention_reasons=list(item.attention_reasons),
        attention_severity=item.attention_severity,
        dataset=to_maturity_governance_dataset_response(item.dataset),
    )


def to_maturity_governance_attention_reason_count_response(
    item: DatasetMaturityGovernanceAttentionReasonCount,
) -> MaturityGovernanceAttentionReasonCountResponse:
    """Map maturity governance attention reason count to API response."""
    return MaturityGovernanceAttentionReasonCountResponse(
        reason=item.reason,
        count=item.count,
    )


def to_maturity_governance_attention_severity_count_response(
    item: DatasetMaturityGovernanceAttentionSeverityCount,
) -> MaturityGovernanceAttentionSeverityCountResponse:
    """Map maturity governance attention severity count to API response."""
    return MaturityGovernanceAttentionSeverityCountResponse(
        severity=item.severity,
        count=item.count,
    )


def to_maturity_governance_source_fallback_policy_effect_count_response(
    item: DatasetMaturityGovernanceSourceFallbackPolicyEffectCount,
) -> MaturityGovernanceSourceFallbackPolicyEffectCountResponse:
    """Map maturity governance source policy effect count to API response."""
    return MaturityGovernanceSourceFallbackPolicyEffectCountResponse(
        policy_id=item.policy_id,
        policy_status=item.policy_status,
        catalog_selected_source=item.catalog_selected_source,
        effective_selected_source=item.effective_selected_source,
        count=item.count,
    )


def to_maturity_governance_report_response(
    report: DatasetMaturityGovernanceReport,
) -> MaturityGovernanceReportResponse:
    """Map application maturity governance report to API response model."""
    return MaturityGovernanceReportResponse(
        dataset_count=report.dataset_count,
        warning_count=report.warning_count,
        promotable_count=report.promotable_count,
        active_promotion_count=report.active_promotion_count,
        revoked_promotion_count=report.revoked_promotion_count,
        maturity_summary=[
            DatasetMaturitySummaryResponse(
                maturity=item.maturity,
                dataset_count=item.dataset_count,
                fresh_count=item.fresh_count,
                stale_count=item.stale_count,
                missing_count=item.missing_count,
                not_applicable_count=item.not_applicable_count,
                failed_count=item.failed_count,
                warning_count=item.warning_count,
                promotion_ready_count=item.promotion_ready_count,
                promotion_blocked_count=item.promotion_blocked_count,
            )
            for item in report.maturity_summary
        ],
        promotion_status_counts=[
            to_promotion_status_count_response(item)
            for item in report.promotion_status_counts
        ],
        missing_criteria_counts=[
            to_promotion_criterion_count_response(item)
            for item in report.missing_criteria_counts
        ],
        rejected_criteria_counts=[
            to_promotion_criterion_count_response(item)
            for item in report.rejected_criteria_counts
        ],
        datasets=[
            to_maturity_governance_dataset_response(item) for item in report.datasets
        ],
        attention_reason_counts=[
            to_maturity_governance_attention_reason_count_response(item)
            for item in report.attention_reason_counts
        ],
        attention_severity_counts=[
            to_maturity_governance_attention_severity_count_response(item)
            for item in report.attention_severity_counts
        ],
        source_fallback_policy_effect_counts=[
            to_maturity_governance_source_fallback_policy_effect_count_response(item)
            for item in report.source_fallback_policy_effect_counts
        ],
        attention_required=[
            to_maturity_governance_attention_item_response(item)
            for item in report.attention_required
        ],
    )


@router.get(
    "/status",
    response_model=APIResponse[IngestionStatusResponse],
    operation_id="ingestion_get_ingestion_status",
)
@inject
async def get_ingestion_status(
    facade: Annotated[IngestionStatusQueryFacade, FromComponent()],
) -> APIResponse[IngestionStatusResponse]:
    """获取各数据集最新摄取状态."""
    statuses = await run_blocking(facade.get_status, _KNOWN_DATASETS)
    datasets = [
        DatasetStatusResponse(
            dataset=s.dataset,
            latest_date=s.latest_date,
            latest_status=s.latest_status,
            dataset_maturity=s.dataset_maturity,
            dataset_maturity_warning=s.dataset_maturity_warning,
            dataset_promotion_criteria=list(s.dataset_promotion_criteria),
            dataset_promotion_status=s.dataset_promotion_status,
            dataset_promotion_missing_criteria=list(
                s.dataset_promotion_missing_criteria
            ),
            dataset_promotion_satisfied_criteria=list(
                s.dataset_promotion_satisfied_criteria
            ),
            dataset_promotion_rejected_criteria=list(
                s.dataset_promotion_rejected_criteria
            ),
            latest_revocation_reason=s.latest_revocation_reason,
            latest_revoked_by=s.latest_revoked_by,
            latest_revoked_at=s.latest_revoked_at.isoformat()
            if s.latest_revoked_at is not None
            else None,
            record_count=s.record_count,
            last_attempt=s.last_attempt,
            catalog_freshness_at=s.catalog_freshness_at.isoformat()
            if s.catalog_freshness_at is not None
            else None,
            catalog_storage_uri=s.catalog_storage_uri,
            catalog_schema_hash=s.catalog_schema_hash,
            catalog_row_count=s.catalog_row_count,
            catalog_freshness_status=s.catalog_freshness_status,
            catalog_freshness_sla_hours=s.catalog_freshness_sla_hours,
        )
        for s in statuses
    ]
    maturity_summary = [
        DatasetMaturitySummaryResponse(
            maturity=s.maturity,
            dataset_count=s.dataset_count,
            fresh_count=s.fresh_count,
            stale_count=s.stale_count,
            missing_count=s.missing_count,
            not_applicable_count=s.not_applicable_count,
            failed_count=s.failed_count,
            warning_count=s.warning_count,
            promotion_ready_count=s.promotion_ready_count,
            promotion_blocked_count=s.promotion_blocked_count,
        )
        for s in summarize_status_by_maturity(statuses)
    ]
    return APIResponse(
        data=IngestionStatusResponse(
            datasets=datasets,
            maturity_summary=maturity_summary,
        )
    )


@router.get(
    "/history",
    response_model=APIResponse[list[IngestionHistoryItem]],
    operation_id="ingestion_get_ingestion_history",
)
@inject
async def get_ingestion_history(
    facade: Annotated[IngestionStatusQueryFacade, FromComponent()],
    dataset: str = Query(..., description="数据集名称"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数上限"),
) -> APIResponse[list[IngestionHistoryItem]]:
    """获取数据集摄取历史."""
    items = await run_blocking(facade.get_history, dataset, limit)
    return APIResponse(
        data=[
            IngestionHistoryItem(
                dataset=i.dataset,
                trade_date=i.trade_date,
                status=i.status,
                rows=i.rows,
                error_message=i.error_message,
                attempts=i.attempts,
                last_attempt_at=i.last_attempt_at,
            )
            for i in items
        ]
    )


@router.get(
    "/dq-summary",
    response_model=APIResponse[DQSummaryResponse],
    operation_id="ingestion_get_dq_summary",
)
@inject
async def get_dq_summary() -> APIResponse[DQSummaryResponse]:
    """
    获取 DQ 检查摘要.

    V1 占位: 返回空列表，待接入 QualityPatrolService 后填充实际数据。
    """
    return APIResponse(data=DQSummaryResponse(datasets=[]))


@router.post(
    "/catalog/promotion/evidence",
    response_model=APIResponse[PromotionEvidenceReviewResponse],
    operation_id="ingestion_review_dataset_promotion_evidence",
)
@inject
async def review_dataset_promotion_evidence(
    handler: Annotated[ReviewDatasetPromotionEvidenceHandler, FromComponent()],
    request: PromotionEvidenceReviewRequest,
) -> APIResponse[PromotionEvidenceReviewResponse]:
    """Persist reviewer evidence for one dataset promotion criterion."""
    result = await run_blocking(
        handler.handle,
        DatasetPromotionReviewCommand(
            dataset_id=request.dataset_id,
            criterion=request.criterion,
            evidence_uri=request.evidence_uri,
            reviewed_by=request.reviewed_by,
            passed=request.passed,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=PromotionEvidenceReviewResponse(
            dataset_id=result.dataset_id,
            reviewed_criterion=result.reviewed_criterion,
            evidence_uri=result.evidence_uri,
            reviewed_by=result.reviewed_by,
            passed=result.passed,
            reviewed_at=result.reviewed_at.isoformat(),
            promotion_status=result.promotion_status,
            missing_criteria=list(result.missing_criteria),
            satisfied_criteria=list(result.satisfied_criteria),
            rejected_criteria=list(result.rejected_criteria),
            metadata_promoted=result.metadata_promoted,
            dataset_maturity_before=result.dataset_maturity_before,
            dataset_maturity_after=result.dataset_maturity_after,
        )
    )


@router.get(
    "/catalog/promotion/readiness",
    response_model=APIResponse[PromotionReadinessReportResponse],
    operation_id="ingestion_get_catalog_promotion_readiness_report",
)
@inject
async def get_catalog_promotion_readiness_report(
    facade: Annotated[IngestionStatusQueryFacade, FromComponent()],
    dataset_ids: list[str] | None = Query(
        None,
        description="数据集 ID 列表; 缺省使用当前后端已知数据集集合",
    ),
    trade_dates: list[str] | None = Query(
        None,
        description="可选交易日期列表; 提供后聚合 active source fallback policy effect",
    ),
    available_sources: list[str] | None = Query(
        None,
        description=(
            "可选 source=auto 来源列表; 与 trade_dates 一起用于 policy effect 聚合"
        ),
    ),
) -> APIResponse[PromotionReadinessReportResponse]:
    """Return aggregated dataset promotion readiness governance report."""
    report_kwargs: dict[str, tuple[str, ...]] = {}
    if trade_dates is not None or available_sources is not None:
        report_kwargs = {
            "trade_dates": tuple(trade_dates or ()),
            "available_sources": tuple(available_sources or ()),
        }
    report = await run_blocking(
        facade.get_promotion_readiness_report,
        dataset_ids or _KNOWN_DATASETS,
        **report_kwargs,
    )
    return APIResponse(data=to_promotion_readiness_report_response(report))


@router.get(
    "/catalog/maturity/governance",
    response_model=APIResponse[MaturityGovernanceReportResponse],
    operation_id="ingestion_get_catalog_maturity_governance_report",
)
@inject
async def get_catalog_maturity_governance_report(
    facade: Annotated[IngestionStatusQueryFacade, FromComponent()],
    dataset_ids: list[str] | None = Query(
        None,
        description="数据集 ID 列表; 缺省使用当前后端已知数据集集合",
    ),
    trade_dates: list[str] | None = Query(
        None,
        description="可选交易日期列表; 提供后聚合 active source fallback policy effect",
    ),
    available_sources: list[str] | None = Query(
        None,
        description=(
            "可选 source=auto 来源列表; 与 trade_dates 一起用于 policy effect 聚合"
        ),
    ),
) -> APIResponse[MaturityGovernanceReportResponse]:
    """Return unified maturity, readiness and revocation governance report."""
    report_kwargs: dict[str, tuple[str, ...]] = {}
    if trade_dates is not None or available_sources is not None:
        report_kwargs = {
            "trade_dates": tuple(trade_dates or ()),
            "available_sources": tuple(available_sources or ()),
        }
    report = await run_blocking(
        facade.get_maturity_governance_report,
        dataset_ids or _KNOWN_DATASETS,
        **report_kwargs,
    )
    return APIResponse(data=to_maturity_governance_report_response(report))


@router.get(
    "/catalog/promotion/history",
    response_model=APIResponse[list[MaturityPromotionHistoryItem]],
    operation_id="ingestion_list_dataset_maturity_promotion_history",
)
@inject
async def list_dataset_maturity_promotion_history(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    dataset_id: str = Query(..., description="数据集 ID"),
) -> APIResponse[list[MaturityPromotionHistoryItem]]:
    """List dataset maturity promotion governance history."""
    events = await run_blocking(facade.list_maturity_promotion_history, dataset_id)
    return APIResponse(
        data=[to_maturity_promotion_history_response(item) for item in events],
    )


@router.post(
    "/catalog/promotion/revoke",
    response_model=APIResponse[MaturityPromotionRevokeResponse],
    operation_id="ingestion_revoke_dataset_maturity_promotion",
)
@inject
async def revoke_dataset_maturity_promotion(
    handler: Annotated[RevokeDatasetMaturityPromotionHandler, FromComponent()],
    request: MaturityPromotionRevokeRequest,
) -> APIResponse[MaturityPromotionRevokeResponse]:
    """Revoke the current dataset maturity promotion override."""
    result = await run_blocking(
        handler.handle,
        DatasetMaturityPromotionRevokeCommand(
            dataset_id=request.dataset_id,
            revoked_by=request.revoked_by,
            revocation_reason=request.revocation_reason,
            notes=request.notes,
        ),
    )
    return APIResponse(
        data=MaturityPromotionRevokeResponse(
            dataset_id=result.dataset_id,
            revoked_by=result.revoked_by,
            revoked_at=result.revoked_at.isoformat(),
            dataset_maturity_before=result.dataset_maturity_before,
            dataset_maturity_after=result.dataset_maturity_after,
            evidence_uri=result.evidence_uri,
            revocation_reason=result.revocation_reason,
            notes=result.notes,
        )
    )


@router.get(
    "/catalog/assets",
    response_model=APIResponse[list[CatalogAssetResponse]],
    operation_id="ingestion_list_catalog_assets",
)
@inject
async def list_catalog_assets(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    namespace: str | None = Query(None, description="资产命名空间"),
    dataset_id: str | None = Query(None, description="数据集 ID"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[CatalogAssetResponse]]:
    """查询 DataCatalog 资产 freshness/storage/schema 元数据."""
    assets = await run_blocking(
        facade.list_assets,
        namespace=namespace,
        dataset_id=dataset_id,
    )
    return paginate(
        [to_catalog_asset_response(asset) for asset in assets],
        pagination,
    )


@router.get(
    "/catalog/asset",
    response_model=APIResponse[CatalogAssetResponse],
    operation_id="ingestion_get_catalog_asset",
)
@inject
async def get_catalog_asset(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    namespace: str = Query(..., description="资产命名空间"),
    dataset_id: str = Query(..., description="数据集 ID"),
    partition_keys: list[str] | None = Query(None, description="资产分区键"),
) -> APIResponse[CatalogAssetResponse]:
    """查询单个 DataCatalog 资产 freshness/storage/schema 元数据."""
    asset = await run_blocking(
        facade.get_asset,
        namespace=namespace,
        dataset_id=dataset_id,
        partition_keys=tuple(partition_keys or ()),
    )
    if asset is None:
        raise NotFoundError(f"Catalog asset not found: {namespace}/{dataset_id}")
    return APIResponse(data=to_catalog_asset_response(asset))


@router.get(
    "/catalog/source-health",
    response_model=APIResponse[CatalogSourceHealthReportResponse],
    operation_id="ingestion_get_catalog_source_health_report",
)
@inject
async def get_catalog_source_health_report(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    dataset_id: str = Query(..., description="数据集 ID"),
    trade_date: str = Query(..., description="交易日期"),
    available_sources: list[str] | None = Query(
        None,
        description="source=auto 可用来源列表; 缺省使用当前后端默认数据源集合",
    ),
) -> APIResponse[CatalogSourceHealthReportResponse]:
    """Return catalog-backed source health evidence for source=auto decisions."""
    report = await run_blocking(
        facade.get_source_health_report,
        dataset_id=dataset_id,
        trade_date=trade_date,
        available_sources=tuple(available_sources or ("tushare", "fred")),
    )
    return APIResponse(data=to_catalog_source_health_report_response(report))


@router.get(
    "/catalog/source-fallback/preview",
    response_model=APIResponse[CatalogSourceFallbackPolicyPreviewResponse],
    operation_id="ingestion_get_catalog_source_fallback_policy_preview",
)
@inject
async def get_catalog_source_fallback_policy_preview(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    dataset_id: str = Query(..., description="数据集 ID"),
    trade_date: str = Query(..., description="交易日期"),
    available_sources: list[str] | None = Query(
        None,
        description="source=auto 可用来源列表; 缺省使用当前后端默认数据源集合",
    ),
) -> APIResponse[CatalogSourceFallbackPolicyPreviewResponse]:
    """Return read-only backend fallback policy preview for source=auto."""
    preview = await run_blocking(
        facade.get_source_fallback_policy_preview,
        dataset_id=dataset_id,
        trade_date=trade_date,
        available_sources=tuple(available_sources or ("tushare", "fred")),
    )
    return APIResponse(data=to_catalog_source_fallback_policy_preview_response(preview))


@router.get(
    "/catalog/source-fallback/summary",
    response_model=APIResponse[CatalogSourceFallbackPolicySummaryResponse],
    operation_id="ingestion_get_catalog_source_fallback_policy_summary",
)
@inject
async def get_catalog_source_fallback_policy_summary(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    dataset_ids: list[str] = Query(..., description="数据集 ID 列表"),
    trade_dates: list[str] = Query(..., description="交易日期列表"),
    available_sources: list[str] | None = Query(
        None,
        description="source=auto 可用来源列表; 缺省使用当前后端默认数据源集合",
    ),
) -> APIResponse[CatalogSourceFallbackPolicySummaryResponse]:
    """Return aggregated backend fallback policy previews."""
    report = await run_blocking(
        facade.get_source_fallback_policy_summary,
        dataset_ids=tuple(dataset_ids),
        trade_dates=tuple(trade_dates),
        available_sources=tuple(available_sources or ("tushare", "fred")),
    )
    return APIResponse(data=to_catalog_source_fallback_policy_summary_response(report))


@router.get(
    "/catalog/source-health/summary",
    response_model=APIResponse[CatalogSourceHealthSummaryReportResponse],
    operation_id="ingestion_get_catalog_source_health_summary_report",
)
@inject
async def get_catalog_source_health_summary_report(
    facade: Annotated[CatalogQueryFacade, FromComponent()],
    dataset_ids: list[str] = Query(..., description="数据集 ID 列表"),
    trade_dates: list[str] = Query(..., description="交易日期列表"),
    available_sources: list[str] | None = Query(
        None,
        description="source=auto 可用来源列表; 缺省使用当前后端默认数据源集合",
    ),
) -> APIResponse[CatalogSourceHealthSummaryReportResponse]:
    """Return aggregated catalog-backed source health diagnostics."""
    report = await run_blocking(
        facade.get_source_health_summary,
        dataset_ids=tuple(dataset_ids),
        trade_dates=tuple(trade_dates),
        available_sources=tuple(available_sources or ("tushare", "fred")),
    )
    return APIResponse(data=to_catalog_source_health_summary_report_response(report))
