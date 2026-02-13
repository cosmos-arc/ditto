"""元数据 API 路由."""

from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.services.metadata_service import MetadataService
from fastapi import APIRouter, HTTPException, Query

from ditto_port.models.common import APIResponse
from ditto_port.models.metadata import (
    AssetClass,
    Instrument,
    to_instrument,
    to_instrument_list,
)

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/instruments/{instrument_id}", response_model=Instrument)
@inject
async def get_instrument(
    instrument_id: int,
    service: Annotated[MetadataService, FromComponent()],
) -> Instrument:
    """
    获取单个标的详情.

    Args:
        instrument_id: 标的 ID
        service: MetadataService 依赖注入

    Returns:
        Instrument 标的信息

    Raises:
        HTTPException: 404 如果标的不存在

    """
    row = service.get_instrument(instrument_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return to_instrument(row)


@router.get("/instruments", response_model=APIResponse[list[Instrument]])
@inject
async def list_instruments(
    service: Annotated[MetadataService, FromComponent()],
    asset_class: AssetClass | None = None,
    exchange: str | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=1000, description="返回数量限制"),
) -> APIResponse[list[Instrument]]:
    """
    查询标的列表.

    Args:
        asset_class: 资产类别过滤 (可选)
        exchange: 交易所过滤 (可选)
        is_active: 活跃状态过滤 (可选)
        limit: 返回数量限制, 默认 100, 范围 1-1000
        service: MetadataService 依赖注入

    Returns:
        APIResponse 包含 Instrument 列表

    """
    # 构建查询参数
    asset_class_str = asset_class.value if asset_class else None

    # 调用 service
    df = service.find_securities(
        asset_class=asset_class_str,
        exchange=exchange,
        is_active=is_active,
    )

    # 转换为模型列表
    instruments = to_instrument_list(df)

    # 应用 limit
    instruments = instruments[:limit]

    return APIResponse(data=instruments)
