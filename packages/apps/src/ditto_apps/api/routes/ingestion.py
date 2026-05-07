"""数据摄取状态 API 路由."""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.config import get_all_datasets
from ditto_application.queries.ingestion_status import (
    IngestionStatusQueryFacade,
)
from fastapi import APIRouter, Query

from ditto_apps.models.common import APIResponse
from ditto_apps.models.ingestion import (
    DatasetStatusResponse,
    DQSummaryResponse,
    IngestionHistoryItem,
    IngestionStatusResponse,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# 从 Dataset StrEnum 派生，保证单一事实来源
_KNOWN_DATASETS = [dataset.value for dataset in get_all_datasets()]


@router.get("/status", response_model=APIResponse[IngestionStatusResponse])
@inject
async def get_ingestion_status(
    facade: Annotated[IngestionStatusQueryFacade, FromComponent()],
) -> APIResponse[IngestionStatusResponse]:
    """获取各数据集最新摄取状态."""
    statuses = await asyncio.to_thread(facade.get_status, _KNOWN_DATASETS)
    datasets = [
        DatasetStatusResponse(
            dataset=s.dataset,
            latest_date=s.latest_date,
            latest_status=s.latest_status,
            record_count=s.record_count,
            last_attempt=s.last_attempt,
        )
        for s in statuses
    ]
    return APIResponse(data=IngestionStatusResponse(datasets=datasets))


@router.get("/history", response_model=APIResponse[list[IngestionHistoryItem]])
@inject
async def get_ingestion_history(
    facade: Annotated[IngestionStatusQueryFacade, FromComponent()],
    dataset: str = Query(..., description="数据集名称"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数上限"),
) -> APIResponse[list[IngestionHistoryItem]]:
    """获取数据集摄取历史."""
    items = await asyncio.to_thread(facade.get_history, dataset, limit)
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


@router.get("/dq-summary", response_model=APIResponse[DQSummaryResponse])
@inject
async def get_dq_summary() -> APIResponse[DQSummaryResponse]:
    """
    获取 DQ 检查摘要.

    V1 占位: 返回空列表，待接入 QualityPatrolService 后填充实际数据。
    """
    return APIResponse(data=DQSummaryResponse(datasets=[]))
