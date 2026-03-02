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
from fastapi import APIRouter, HTTPException

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

# 反向映射：instrument_id -> commodity_code
_INSTRUMENT_ID_TO_COMMODITY_CODE = {v: k for k, v in _ALL_COMMODITY_MAPPINGS.items()}


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
            - commodity_codes: 商品代码列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000, 范围 1-10000)
        market_service: MarketService 依赖注入

    Returns:
        APIResponse 包含商品 K 线数据列表

    """
    # P1-1: 严格校验非法参数
    valid_codes = set(_ALL_COMMODITY_MAPPINGS.keys())
    if query.commodity_codes:
        invalid_codes = [c for c in query.commodity_codes if c not in valid_codes]
        if invalid_codes:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_commodity_codes",
                    "message": f"Invalid commodity codes: {invalid_codes}",
                    "valid_codes": list(valid_codes),
                },
            )

        instrument_ids = [
            _ALL_COMMODITY_MAPPINGS[code] for code in query.commodity_codes
        ]
    else:
        instrument_ids = list(_ALL_COMMODITY_MAPPINGS.values())

    # P1-2: limit 下推到在 DataFrame 层应用
    # 构建查询参数
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None
    limit_param = query.limit

    # 查询数据（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        market_service.list_bars,
        instrument_ids=instrument_ids,
        start=start_str,
        end=end_str,
        asset_class="commodity",
        limit=limit_param,  # 传递 limit 参数
    )

    # 如果 DataFrame 为空,直接返回空列表
    if df.is_empty():
        return APIResponse(data=[])

    # P2-1: 移除 trade_date_utc 的 dt.date() 截断,直接保留原始值
    # 添加 commodity_code 列（从 instrument_id 映射）
    df = df.with_columns(
        pl.col("instrument_id")
        .replace(_INSTRUMENT_ID_TO_COMMODITY_CODE)
        .alias("commodity_code")
    )

    # 选择并重命名列以匹配模型（移除 dt.date() 截断)
    df = df.select(
        "commodity_code",
        pl.col("trade_date_utc").alias("trade_date_utc"),  # 直接保留，不截断
        "open",
        "high",
        "low",
        "close",
    )

    # 转换为模型列表
    bars = to_commodity_bar_list(df)

    return APIResponse(data=bars)
