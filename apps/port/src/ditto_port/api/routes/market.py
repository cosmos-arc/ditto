"""行情数据 API 路由."""

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.services.market_service import (
    AdjType,
    MarketBarsQuery,
    MarketService,
)
from fastapi import APIRouter

from ditto_port.models.common import APIResponse
from ditto_port.models.market import (
    Adjustment,
    Bar,
    BarsQuery,
    to_bar_list,
)

router = APIRouter(prefix="/market", tags=["market"])


def _map_adjustment(adj: Adjustment) -> AdjType:
    """将 API 层的 Adjustment 映射到 Service 层的 AdjType."""
    mapping = {
        Adjustment.NONE: AdjType.NONE,
        Adjustment.QFQ: AdjType.QFQ,
        Adjustment.HFQ: AdjType.HFQ,
    }
    return mapping[adj]


@router.post("/bars", response_model=APIResponse[list[Bar]])
@inject
async def post_bars(
    query: BarsQuery,
    service: Annotated[MarketService, FromComponent()],
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
        service: MarketService 依赖注入

    Returns:
        APIResponse 包含 K 线数据列表

    """
    # 构建查询对象
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None

    service_query = MarketBarsQuery(
        instrument_ids=query.instrument_ids,
        start=start_str,
        end=end_str,
        adj=_map_adjustment(query.adjustment),
    )

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.find_bars, service_query)

    # 转换为模型列表
    bars = to_bar_list(df)

    # 应用 limit
    bars = bars[: query.limit]

    return APIResponse(data=bars)
