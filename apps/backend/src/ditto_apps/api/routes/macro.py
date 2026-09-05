"""
Macro 域 API 路由.

maturity: experimental
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.macro import MacroQueryFacade
from fastapi import APIRouter, Query

from ditto_apps.models.common import APIResponse
from ditto_apps.models.macro import (
    Indicator,
    IndicatorQuery,
    to_indicator_list,
)

router = APIRouter(prefix="/macro", tags=["macro"])


def _experimental_kwargs(allow_experimental_data: bool) -> dict[str, bool]:
    if allow_experimental_data:
        return {"allow_experimental_data": True}
    return {}


def _find_indicators(
    facade: MacroQueryFacade,
    query: IndicatorQuery,
) -> pl.DataFrame:
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None
    return facade.find_indicators(
        indicators=query.indicators,
        start=start_str,
        end=end_str,
        category=query.category.value if query.category is not None else None,
        frequency=query.frequency.value if query.frequency is not None else None,
        **_experimental_kwargs(query.allow_experimental_data),
    )


def _list_indicators(
    facade: MacroQueryFacade,
    *,
    start: str,
    end: str,
    category: str | None = None,
    allow_experimental_data: bool = False,
) -> pl.DataFrame:
    return facade.list_indicators(
        start=start,
        end=end,
        category=category,
        **_experimental_kwargs(allow_experimental_data),
    )


@router.post(
    "/indicators",
    response_model=APIResponse[list[Indicator]],
    operation_id="macro_post_indicators",
)
@inject
async def post_indicators(
    query: IndicatorQuery,
    facade: Annotated[MacroQueryFacade, FromComponent()],
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
        facade: MacroQueryFacade 依赖注入

    Returns:
        APIResponse 包含宏观指标数据列表

    """
    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(_find_indicators, facade, query)

    # 转换为模型列表
    indicators = to_indicator_list(df)

    return APIResponse(data=indicators)


@router.get(
    "/indicators/metadata",
    response_model=APIResponse[list[Indicator]],
    operation_id="macro_get_indicators_metadata",
)
@inject
async def get_indicators_metadata(
    facade: Annotated[MacroQueryFacade, FromComponent()],
    start: Annotated[str, Query(description="开始日期 (YYYY-MM-DD)")],
    end: Annotated[str, Query(description="结束日期 (YYYY-MM-DD)")],
    category: Annotated[str | None, Query(description="类别过滤")] = None,
    allow_experimental_data: Annotated[
        bool,
        Query(description="显式允许 experimental 数据集进入研究态查询"),
    ] = False,
) -> APIResponse[list[Indicator]]:
    """
    获取指标元数据列表.

    Args:
        facade: MacroQueryFacade 依赖注入
        start: 开始日期 (YYYY-MM-DD)
        end: 结束日期 (YYYY-MM-DD)
        category: 类别过滤 (可选)
        allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

    Returns:
        APIResponse 包含宏观指标数据列表

    """
    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _list_indicators,
        facade,
        start=start,
        end=end,
        category=category,
        allow_experimental_data=allow_experimental_data,
    )

    # 转换为模型列表
    indicators = to_indicator_list(df)

    return APIResponse(data=indicators)
