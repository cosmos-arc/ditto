"""Macro 域 API 路由."""

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.models import MacroCategory
from ditto_datahub.services.macro_service import MacroQuery, MacroService
from fastapi import APIRouter, Query

from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.macro import (
    Indicator,
    IndicatorQuery,
    to_indicator_list,
)

router = APIRouter(prefix="/macro", tags=["macro"])


@router.post("/indicators", response_model=APIResponse[list[Indicator]])
@inject
async def post_indicators(
    query: IndicatorQuery,
    service: Annotated[MacroService, FromComponent()],
) -> APIResponse[list[Indicator]]:
    """
    查询宏观指标数据.

    Args:
        query: 查询参数
            - indicators: 指标 ID 或代码列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - category: 类别过滤 (economic/interest_rate/exchange_rate/money_supply)
            - frequency: 频率过滤 (daily/monthly/quarterly)
        service: MacroService 依赖注入

    Returns:
        APIResponse 包含宏观指标数据列表

    """
    # 构建查询对象
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None

    service_query = MacroQuery(
        indicators=query.indicators,
        start=start_str,
        end=end_str,
        category=query.category,
        frequency=query.frequency,
    )

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.find_indicators, service_query)

    # 转换为模型列表
    indicators = to_indicator_list(df)

    return APIResponse(data=indicators)


@router.get("/indicators/metadata", response_model=APIResponse[list[Indicator]])
@inject
async def get_indicators_metadata(
    service: Annotated[MacroService, FromComponent()],
    start: Annotated[str, Query(description="开始日期 (YYYY-MM-DD)")],
    end: Annotated[str, Query(description="结束日期 (YYYY-MM-DD)")],
    category: Annotated[MacroCategory | None, Query(description="类别过滤")] = None,
) -> APIResponse[list[Indicator]]:
    """
    获取指标元数据列表.

    Args:
        service: MacroService 依赖注入
        start: 开始日期 (YYYY-MM-DD)
        end: 结束日期 (YYYY-MM-DD)
        category: 类别过滤 (可选)

    Returns:
        APIResponse 包含宏观指标数据列表

    """
    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        service.list_indicators,
        start=start,
        end=end,
        category=category,
    )

    # 转换为模型列表
    indicators = to_indicator_list(df)

    return APIResponse(data=indicators)
