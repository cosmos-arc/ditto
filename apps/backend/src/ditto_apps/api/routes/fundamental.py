"""
基本面数据 API 路由.

maturity: experimental
"""

from __future__ import annotations

import asyncio
from datetime import date as date_type
from typing import Annotated

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from fastapi import APIRouter, Depends

from ditto_apps.api.errors import DateRangeError, FutureDateError
from ditto_apps.api.params import DateRangeQueryParams, PITQueryParams
from ditto_apps.api.utils.identifier import resolve_identifier_for_api
from ditto_apps.models.common import APIResponse
from ditto_apps.models.fundamental import (
    CorporateAction,
    Dividend,
    Financial,
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)

router = APIRouter(prefix="/fundamental", tags=["fundamental"])


def _reject_future_date(value: date_type | None, field_name: str) -> None:
    """如果日期为未来日期则抛出 FutureDateError."""
    if value is not None and value > date_type.today():
        raise FutureDateError(field_name=field_name, date_value=value.isoformat())


def _experimental_kwargs(allow_experimental_data: bool) -> dict[str, bool]:
    if allow_experimental_data:
        return {"allow_experimental_data": True}
    return {}


def _fetch_financials(
    facade: FundamentalQueryFacade,
    report_type: FinancialType,
    *,
    instrument_id: int,
    as_of_date: date_type,
    allow_experimental_data: bool = False,
) -> pl.DataFrame | None:
    kwargs = _experimental_kwargs(allow_experimental_data)
    if report_type == FinancialType.BALANCE_SHEET:
        return facade.get_balance_sheet(instrument_id, as_of_date, **kwargs)
    if report_type == FinancialType.INCOME_STATEMENT:
        return facade.get_income_statement(instrument_id, as_of_date, **kwargs)
    if report_type == FinancialType.CASH_FLOW:
        return facade.get_cash_flow(instrument_id, as_of_date, **kwargs)
    return None


def _fetch_dividend(
    facade: FundamentalQueryFacade,
    *,
    instrument_id: int,
    as_of_date: date_type,
    allow_experimental_data: bool = False,
) -> pl.DataFrame | None:
    return facade.get_dividend(
        instrument_id,
        as_of_date,
        **_experimental_kwargs(allow_experimental_data),
    )


def _fetch_corporate_actions(
    facade: FundamentalQueryFacade,
    *,
    instrument_id: int,
    start_date: date_type,
    end_date: date_type,
    as_of_date: date_type | None = None,
    allow_experimental_data: bool = False,
) -> pl.DataFrame:
    return facade.list_corporate_actions(
        instrument_id,
        start_date,
        end_date,
        as_of_date,
        **_experimental_kwargs(allow_experimental_data),
    )


@router.get(
    "/financials/{report_type}",
    response_model=APIResponse[list[Financial]],
    operation_id="fundamental_get_financials",
)
@inject
async def get_financials(
    report_type: FinancialType,
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[PITQueryParams, Depends()],
) -> APIResponse[list[Financial]]:
    """
    获取财务报表数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        FutureDateError: 400 如果 as_of_date 为未来日期

    """
    _reject_future_date(params.as_of_date, "as_of_date")

    resolved_id = resolve_identifier_for_api(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="fundamental",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 根据报表类型调用对应的方法（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _fetch_financials,
        fundamental_facade,
        report_type,
        instrument_id=resolved_id,
        as_of_date=params.as_of_date,
        allow_experimental_data=params.allow_experimental_data,
    )

    if df is None or df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    financials = to_financial_list(df, report_type)

    return APIResponse(data=financials)


@router.get(
    "/dividend",
    response_model=APIResponse[list[Dividend]],
    operation_id="fundamental_get_dividend",
)
@inject
async def get_dividend(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[PITQueryParams, Depends()],
) -> APIResponse[list[Dividend]]:
    """
    获取分红数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        FutureDateError: 400 如果 as_of_date 为未来日期

    """
    _reject_future_date(params.as_of_date, "as_of_date")

    resolved_id = resolve_identifier_for_api(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="fundamental",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _fetch_dividend,
        fundamental_facade,
        instrument_id=resolved_id,
        as_of_date=params.as_of_date,
        allow_experimental_data=params.allow_experimental_data,
    )

    if df is None or df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    dividends = to_dividend_list(df)

    return APIResponse(data=dividends)


@router.get(
    "/corporate-actions",
    response_model=APIResponse[list[CorporateAction]],
    operation_id="fundamental_list_corporate_actions",
)
@inject
async def list_corporate_actions(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[DateRangeQueryParams, Depends()],
) -> APIResponse[list[CorporateAction]]:
    """
    查询公司行动列表.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        DateRangeError: 400 如果 start_date > end_date
        FutureDateError: 400 如果 as_of_date 为未来日期

    """
    # 验证日期范围
    if params.start_date > params.end_date:
        raise DateRangeError(
            start_date=params.start_date.isoformat(),
            end_date=params.end_date.isoformat(),
        )

    _reject_future_date(params.as_of_date, "as_of_date")

    resolved_id = resolve_identifier_for_api(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="fundamental",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _fetch_corporate_actions,
        fundamental_facade,
        instrument_id=resolved_id,
        start_date=params.start_date,
        end_date=params.end_date,
        as_of_date=params.as_of_date,
        allow_experimental_data=params.allow_experimental_data,
    )

    if df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    actions = to_corporate_action_list(df)

    return APIResponse(data=actions)
