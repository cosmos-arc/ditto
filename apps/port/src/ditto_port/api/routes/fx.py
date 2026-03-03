"""FX (外汇) 娡 API 路由."""

import asyncio
from typing import Annotated

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.models import FX_CODE_TO_INSTRUMENT_ID
from ditto_datahub.services.market_service import MarketService
from fastapi import APIRouter, HTTPException

from ditto_port.models.common import APIResponse
from ditto_port.models.fx import FxBar, FxQuery, to_fx_bar_list

router = APIRouter(prefix="/fx", tags=["fx"])

# 反向映射：instrument_id -> currency_pair (e.g., 4000001 -> "USDCNH.FXCM")
_INSTRUMENT_ID_TO_CURRENCY_PAIR = {v: k for k, v in FX_CODE_TO_INSTRUMENT_ID.items()}


@router.post("/bars", response_model=APIResponse[list[FxBar]])
@inject
async def post_bars(
    query: FxQuery,
    market_service: Annotated[MarketService, FromComponent()],
) -> APIResponse[list[FxBar]]:
    """
    查询外汇 K 线数据.

    Args:
        query: 查询参数
            - currency_pairs: 货币对列表 (可选, 如 ["USDCNH.FXCM", "EURUSD.FXCM"])
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000, 范围 1-10000)
        market_service: MarketService 依赖注入

    Returns:
        APIResponse 包含外汇 K 线数据列表

    """
    # P1-1: 严格校验非法参数
    valid_pairs = set(FX_CODE_TO_INSTRUMENT_ID.keys())
    if query.currency_pairs:
        invalid_pairs = [p for p in query.currency_pairs if p not in valid_pairs]
        if invalid_pairs:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_currency_pairs",
                    "message": f"Invalid currency pairs: {invalid_pairs}",
                    "valid_pairs": list(valid_pairs),
                },
            )

        instrument_ids = [
            FX_CODE_TO_INSTRUMENT_ID[pair] for pair in query.currency_pairs
        ]
    else:
        instrument_ids = list(FX_CODE_TO_INSTRUMENT_ID.values())

    # P1-2: limit 下推到在 DataFrame 层应用
    # 构建查询参数
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None
    limit_param = query.limit

    # 查询数据（在线程池中执行，避免阻塞事件循环)
    df = await asyncio.to_thread(
        market_service.list_bars,
        instrument_ids=instrument_ids,
        start=start_str,
        end=end_str,
        asset_class="fx",
        limit=limit_param,  # 传递 limit 参数
    )

    # 如果 DataFrame 为空,直接返回空列表
    if df.is_empty():
        return APIResponse(data=[])

    # P2-1: 移除 trade_date_utc 的 dt.date() 截断,直接保留原始值
    # 添加 currency_pair 列（从 instrument_id 映射）
    df = df.with_columns(
        pl.col("instrument_id")
        .replace(_INSTRUMENT_ID_TO_CURRENCY_PAIR)
        .alias("currency_pair")
    )

    # 选择并重命名列以匹配模型（移除 dt.date() 截断)
    df = df.select(
        "currency_pair",
        pl.col("trade_date_utc").alias("trade_date_utc"),  # 直接保留，不截断
        "open",
        "high",
        "low",
        "close",
    )

    # 转换为模型列表
    bars = to_fx_bar_list(df)

    return APIResponse(data=bars)
