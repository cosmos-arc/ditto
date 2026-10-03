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
from ditto_application.config import get_all_datasets
from ditto_application.queries.catalog import (
    CatalogAsset,
    CatalogQueryFacade,
)
from ditto_application.queries.ingestion_status import (
    IngestionStatusQueryFacade,
    summarize_status_by_maturity,
)
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import NotFoundError
from ditto_apps.api.routes.ingestion_source_health_mapping import (
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
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


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
