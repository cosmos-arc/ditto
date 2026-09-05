"""
Capital 域 API 路由.

maturity: experimental
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from fastapi import APIRouter, Query

from ditto_apps.api.utils.identifier import resolve_identifier_for_api
from ditto_apps.models.capital import (
    Margin,
    Valuation,
    to_margin_list,
    to_valuation_list,
)
from ditto_apps.models.common import APIResponse

router = APIRouter(prefix="/capital", tags=["capital"])


def _experimental_kwargs(allow_experimental_data: bool) -> dict[str, bool]:
    if allow_experimental_data:
        return {"allow_experimental_data": True}
    return {}


def _fetch_margin(
    facade: CapitalQueryFacade,
    *,
    instrument_id: int,
    as_of_date: date,
    allow_experimental_data: bool = False,
) -> pl.DataFrame:
    return facade.get_margin_trading(
        instrument_id,
        as_of_date,
        **_experimental_kwargs(allow_experimental_data),
    )


def _fetch_valuation(
    facade: CapitalQueryFacade,
    *,
    instrument_id: int,
    as_of_date: date,
    allow_experimental_data: bool = False,
) -> pl.DataFrame:
    return facade.get_valuation_metrics(
        instrument_id,
        as_of_date,
        **_experimental_kwargs(allow_experimental_data),
    )


@router.get(
    "/margin",
    response_model=APIResponse[list[Margin]],
    operation_id="capital_get_margin",
)
@inject
async def get_margin(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    as_of_date: date = Query(..., description="时间点查询日期"),
    allow_experimental_data: bool = Query(
        False,
        description="显式允许 experimental 数据集进入研究态查询",
    ),
) -> APIResponse[list[Margin]]:
    """
    获取融资融券数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    """
    resolved_id = resolve_identifier_for_api(
        metadata_facade,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        as_of_date=as_of_date,
        domain="capital",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _fetch_margin,
        capital_facade,
        instrument_id=resolved_id,
        as_of_date=as_of_date,
        allow_experimental_data=allow_experimental_data,
    )

    # 转换为模型列表
    margins = to_margin_list(df)

    return APIResponse(data=margins)


@router.get(
    "/valuation",
    response_model=APIResponse[list[Valuation]],
    operation_id="capital_get_valuation",
)
@inject
async def get_valuation(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    as_of_date: date = Query(..., description="时间点查询日期"),
    allow_experimental_data: bool = Query(
        False,
        description="显式允许 experimental 数据集进入研究态查询",
    ),
) -> APIResponse[list[Valuation]]:
    """
    获取估值指标数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    """
    resolved_id = resolve_identifier_for_api(
        metadata_facade,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        as_of_date=as_of_date,
        domain="capital",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _fetch_valuation,
        capital_facade,
        instrument_id=resolved_id,
        as_of_date=as_of_date,
        allow_experimental_data=allow_experimental_data,
    )

    # 转换为模型列表
    valuations = to_valuation_list(df)

    return APIResponse(data=valuations)
