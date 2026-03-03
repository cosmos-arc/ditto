"""Capital 域 API 路由."""

import asyncio
from datetime import date
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.services.capital_service import CapitalService
from fastapi import APIRouter, Query

from ditto_port.models.capital import (
    Margin,
    Valuation,
    to_margin_list,
    to_valuation_list,
)
from ditto_port.models.common import APIResponse

router = APIRouter(prefix="/capital", tags=["capital"])


@router.get("/margin", response_model=APIResponse[list[Margin]])
@inject
async def get_margin(
    service: Annotated[CapitalService, FromComponent()],
    instrument_id: str = Query(..., description="标的 ID"),
    as_of_date: date = Query(..., description="时间点查询日期"),
) -> APIResponse[list[Margin]]:
    """
    获取融资融券数据.

    Args:
        service: CapitalService 依赖注入
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    Returns:
        APIResponse 包含融资融券数据列表

    """
    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.get_margin_trading, instrument_id, as_of_date)

    # 转换为模型列表
    margins = to_margin_list(df)

    return APIResponse(data=margins)


@router.get("/valuation", response_model=APIResponse[list[Valuation]])
@inject
async def get_valuation(
    service: Annotated[CapitalService, FromComponent()],
    instrument_id: str = Query(..., description="标的 ID"),
    as_of_date: date = Query(..., description="时间点查询日期"),
) -> APIResponse[list[Valuation]]:
    """
    获取估值指标数据.

    Args:
        service: CapitalService 依赖注入
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    Returns:
        APIResponse 包含估值指标数据列表

    """
    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        service.get_valuation_metrics,
        instrument_id,
        as_of_date,
    )

    # 转换为模型列表
    valuations = to_valuation_list(df)

    return APIResponse(data=valuations)
