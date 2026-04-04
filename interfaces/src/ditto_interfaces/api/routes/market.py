"""行情数据 API 路由."""

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.query.market import MarketQueryFacade
from fastapi import APIRouter

from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.market import (
    Bar,
    BarsQuery,
    to_bar_list,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.post("/bars", response_model=APIResponse[list[Bar]])
@inject
async def post_bars(
    query: BarsQuery,
    facade: Annotated[MarketQueryFacade, FromComponent()],
) -> APIResponse[list[Bar]]:
    """
    查询 K 线数据.

    Args:
        query: 查询参数
            - instrument_ids: 标的 ID 列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - adjustment: 复权类型 (none/qfq/hfq)
            - limit: 返回数量限制 (1-10000)
        facade: MarketQueryFacade 依赖注入

    Returns:
        APIResponse 包含 K 线数据列表

    """
    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        facade.find_bars,
        instrument_ids=query.instrument_ids or [],
        start=query.start_date.isoformat() if query.start_date else None,
        end=query.end_date.isoformat() if query.end_date else None,
        adj=query.adjustment.value,
    )

    # 转换为模型列表
    bars = to_bar_list(df)

    # 应用 limit
    bars = bars[: query.limit]

    return APIResponse(data=bars)
