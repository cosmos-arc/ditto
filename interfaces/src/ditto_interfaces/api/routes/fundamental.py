"""基本面数据 API 路由."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from fastapi import APIRouter, Query

from ditto_interfaces.api.errors import DateRangeError
from ditto_interfaces.api.utils.identifier import resolve_identifier_for_api
from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.fundamental import (
    CorporateAction,
    Dividend,
    Financial,
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)

router = APIRouter(prefix="/fundamental", tags=["fundamental"])


@router.get("/financials/{report_type}", response_model=APIResponse[list[Financial]])
@inject
async def get_financials(
    report_type: FinancialType,
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    as_of_date: date = Query(..., description="PIT 查询日期"),
) -> APIResponse[list[Financial]]:
    """
    获取财务报表数据.

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
        domain="fundamental",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 根据报表类型调用对应的方法（在线程池中执行，避免阻塞事件循环）
    df = None
    if report_type == FinancialType.BALANCE_SHEET:
        df = await asyncio.to_thread(
            fundamental_facade.get_balance_sheet,
            resolved_id,
            as_of_date,
        )
    elif report_type == FinancialType.INCOME_STATEMENT:
        df = await asyncio.to_thread(
            fundamental_facade.get_income_statement,
            resolved_id,
            as_of_date,
        )
    elif report_type == FinancialType.CASH_FLOW:
        df = await asyncio.to_thread(
            fundamental_facade.get_cash_flow,
            resolved_id,
            as_of_date,
        )

    if df is None or df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    financials = to_financial_list(df, report_type)

    return APIResponse(data=financials)


@router.get("/dividend", response_model=APIResponse[list[Dividend]])
@inject
async def get_dividend(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    as_of_date: date = Query(..., description="PIT 查询日期"),
) -> APIResponse[list[Dividend]]:
    """
    获取分红数据.

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
        domain="fundamental",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        fundamental_facade.get_dividend,
        resolved_id,
        as_of_date,
    )

    if df is None or df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    dividends = to_dividend_list(df)

    return APIResponse(data=dividends)


@router.get("/corporate-actions", response_model=APIResponse[list[CorporateAction]])
@inject
async def list_corporate_actions(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
) -> APIResponse[list[CorporateAction]]:
    """
    查询公司行动列表.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        DateRangeError: 400 如果 start_date > end_date

    """
    # 验证日期范围
    if start_date > end_date:
        raise DateRangeError(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

    resolved_id = resolve_identifier_for_api(
        metadata_facade,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        domain="fundamental",
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        fundamental_facade.list_corporate_actions,
        resolved_id,
        start_date,
        end_date,
    )

    if df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    actions = to_corporate_action_list(df)

    return APIResponse(data=actions)
