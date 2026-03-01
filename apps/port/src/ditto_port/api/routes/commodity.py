"""Commodity (商品) 域 API 路由."""

import asyncio
from typing import Annotated

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.sources.fred.adapters.commodity import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from fastapi import APIRouter

from ditto_port.models.commodity import (
    CommodityBar,
    CommodityQuery,
    to_commodity_bar_list,
)
from ditto_port.models.common import APIResponse

router = APIRouter(prefix="/commodity", tags=["commodity"])

# 合并 commodity 和 VIX 的映射
_ALL_COMMODITY_MAPPINGS = {
    **COMMODITY_CODE_TO_INSTRUMENT_ID,
    **VIX_CODE_TO_INSTRUMENT_ID,
}

# 反向映射：instrument_id -> symbol
_INSTRUMENT_ID_TO_SYMBOL = {v: k for k, v in _ALL_COMMODITY_MAPPINGS.items()}


@router.post("/bars", response_model=APIResponse[list[CommodityBar]])
@inject
async def post_bars(
    query: CommodityQuery,
    market_service: Annotated[MarketService, FromComponent()],
) -> APIResponse[list[CommodityBar]]:
    """
    查询商品 K 线数据.

    Args:
        query: 查询参数
            - symbols: 商品代码列表 (可选, 如 ["COMMOD_WTI", "COMMOD_GOLD", "VIX_30D"])
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000)
        market_service: MarketService 依赖注入

    Returns:
        APIResponse 包含商品 K 线数据列表

    """
    # 获取 instrument_ids
    if query.symbols:
        instrument_ids = [
            _ALL_COMMODITY_MAPPINGS[symbol]
            for symbol in query.symbols
            if symbol in _ALL_COMMODITY_MAPPINGS
        ]
    else:
        instrument_ids = list(_ALL_COMMODITY_MAPPINGS.values())

    if not instrument_ids:
        return APIResponse(data=[])

    # 构建查询参数
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None

    # 查询数据（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        market_service.list_bars,
        instrument_ids=instrument_ids,
        start=start_str,
        end=end_str,
    )

    # 如果 DataFrame 为空，直接返回空列表
    if df.is_empty():
        return APIResponse(data=[])

    # 添加 symbol 列（从 instrument_id 映射）
    df = df.with_columns(
        pl.col("instrument_id").replace(_INSTRUMENT_ID_TO_SYMBOL).alias("symbol")
    )

    # 选择并重命名列以匹配模型
    df = df.select(
        "symbol",
        pl.col("trade_date_utc").dt.date().cast(pl.String).alias("trade_date_utc"),
        "open",
        "high",
        "low",
        "close",
    )

    # 转换为模型列表
    bars = to_commodity_bar_list(df)

    # 应用 limit
    bars = bars[: query.limit]

    return APIResponse(data=bars)
