"""元数据 API 路由."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_kernel.instrument import AssetClass
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import BadRequestError, NotFoundError
from ditto_apps.models.common import (
    APIResponse,
    PaginationRequest,
)
from ditto_apps.models.metadata import (
    ETFCandidateQueryParams,
    ETFCandidateResponse,
    Instrument,
    to_instrument,
    to_instrument_list,
)

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get(
    "/etf-reference-snapshots",
    response_model=APIResponse[list[str]],
    operation_id="metadata_list_etf_reference_snapshots",
)
@inject
async def list_etf_reference_snapshots(
    facade: Annotated[MetadataQueryFacade, FromComponent()],
    cutoff: datetime,
) -> APIResponse[list[str]]:
    """List source snapshots published by the selected knowledge cutoff."""
    if cutoff.tzinfo is None:
        raise BadRequestError("knowledge cutoff must include a UTC offset")
    snapshots = await asyncio.to_thread(
        facade.list_etf_reference_snapshots,
        cutoff=cutoff.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return APIResponse(data=snapshots)


@router.get(
    "/etf-candidates",
    response_model=APIResponse[list[ETFCandidateResponse]],
    operation_id="metadata_list_etf_candidates",
)
@inject
async def list_etf_candidates(
    facade: Annotated[MetadataQueryFacade, FromComponent()],
    query: Annotated[ETFCandidateQueryParams, Query()],
) -> APIResponse[list[ETFCandidateResponse]]:
    """Compare ETFs by exposure using one explicit published reference snapshot."""
    if query.cutoff.tzinfo is None:
        raise BadRequestError("knowledge cutoff must include a UTC offset")
    try:
        rows = await asyncio.to_thread(
            facade.list_etf_candidates,
            asof=query.asof.isoformat(),
            cutoff=query.cutoff.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_snapshot_id=query.source_snapshot_id,
            exposure=query.exposure,
            asset_exposure=query.asset_exposure,
            search=query.search,
            sort_field=query.sort_field,
        )
    except AppQueryError as exc:
        raise BadRequestError(str(exc)) from exc
    return APIResponse(
        data=[ETFCandidateResponse.model_validate(asdict(row)) for row in rows]
    )


@router.get(
    "/instruments/{instrument_id}",
    response_model=APIResponse[Instrument],
    operation_id="metadata_get_instrument",
)
@inject
async def get_instrument(
    instrument_id: int,
    facade: Annotated[MetadataQueryFacade, FromComponent()],
) -> APIResponse[Instrument]:
    """
    获取单个标的详情.

    Args:
        instrument_id: 标的 ID
        facade: MetadataQueryFacade 依赖注入

    Returns:
        APIResponse 包含 Instrument 标的信息

    Raises:
        NotFoundError: 404 如果标的不存在

    """
    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    row = await asyncio.to_thread(facade.get_instrument, instrument_id)
    if row is None:
        raise NotFoundError("Instrument not found")
    return APIResponse(data=to_instrument(row))


@router.get(
    "/instruments",
    response_model=APIResponse[list[Instrument]],
    operation_id="metadata_list_instruments",
)
@inject
async def list_instruments(
    facade: Annotated[MetadataQueryFacade, FromComponent()],
    asset_class: AssetClass | None = None,
    exchange: str | None = None,
    is_active: bool | None = None,
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[Instrument]]:
    """
    查询标的列表.

    Args:
        asset_class: 资产类别过滤 (可选)
        exchange: 交易所过滤 (可选)
        is_active: 活跃状态过滤 (可选)
        pagination: 分页参数
        facade: MetadataQueryFacade 依赖注入

    Returns:
        APIResponse 包含 Instrument 列表 + 分页信息

    """
    # 构建查询参数
    asset_class_str = asset_class.value if asset_class else None

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        facade.find_securities,
        asset_class=asset_class_str,
        exchange=exchange,
        is_active=is_active,
    )

    # 转换为模型列表
    all_instruments = to_instrument_list(df)

    return paginate(all_instruments, pagination)
