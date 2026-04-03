"""Commodity (商品) 域 API 路由."""

import asyncio
from typing import Annotated

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.query.commodity import CommodityQueryFacade
from fastapi import APIRouter, HTTPException

from ditto_interfaces.models.commodity import (
    CommodityBar,
    CommodityQuery,
    to_commodity_bar_list,
)
from ditto_interfaces.models.common import APIResponse

router = APIRouter(prefix="/commodity", tags=["commodity"])


@router.post("/bars", response_model=APIResponse[list[CommodityBar]])
@inject
async def post_bars(
    query: CommodityQuery,
    facade: Annotated[CommodityQueryFacade, FromComponent()],
) -> APIResponse[list[CommodityBar]]:
    """
    查询商品 K 线数据.

    Args:
        query: 查询参数
            - commodity_codes: 商品代码列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000, 范围 1-10000)
        facade: CommodityQueryFacade 依赖注入

    Returns:
        APIResponse 包含商品 K 线数据列表

    """
    # P1-1: 严格校验非法参数
    valid_codes = facade.get_valid_codes()
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
            facade.code_to_instrument_id(code) for code in query.commodity_codes
        ]
    else:
        instrument_ids = facade.get_all_instrument_ids()

    # P1-2: limit 下推到在 DataFrame 层应用
    # 构建查询参数
    start_str = query.start_date.isoformat() if query.start_date else None
    end_str = query.end_date.isoformat() if query.end_date else None
    limit_param = query.limit

    # 查询数据（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        facade.list_bars,
        instrument_ids=instrument_ids,
        start=start_str,
        end=end_str,
        limit=limit_param,
    )

    # 如果 DataFrame 为空,直接返回空列表
    if df.is_empty():
        return APIResponse(data=[])

    # P2-1: 移除 trade_date_utc 的 dt.date() 截断,直接保留原始值
    # 添加 commodity_code 列（从 instrument_id 映射）
    id_to_code_map = {
        iid: facade.instrument_id_to_code(iid) or ""
        for iid in df["instrument_id"].unique().to_list()
    }
    df = df.with_columns(
        pl.col("instrument_id").replace(id_to_code_map).alias("commodity_code")
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
