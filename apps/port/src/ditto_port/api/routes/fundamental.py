"""基本面数据 API 路由."""

import asyncio
from datetime import date
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.errors import AmbiguousTickerError
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_infra.foundation import logger
from fastapi import APIRouter, HTTPException, Query

from ditto_port.models.common import APIResponse
from ditto_port.models.fundamental import (
    CorporateAction,
    Dividend,
    Financial,
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)

router = APIRouter(prefix="/fundamental", tags=["fundamental"])


def _resolve_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    standard_ticker: str | None,
    ticker: str | None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符（instrument_id / standard_ticker / ticker），
    委托给 MetadataService.resolve_instrument_identifier 进行统一解析。

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    Raises:
        HTTPException: 标识符缺失或解析失败时.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        raise HTTPException(
            status_code=422,
            detail="必须提供 instrument_id、standard_ticker 或 ticker 之一",
        )

    try:
        result = metadata_service.resolve_instrument_identifier(
            instrument_id=instrument_id,
            standard_ticker=standard_ticker,
            ticker=ticker,
            source="tushare",
            asset_class="stock",
        )
    except AmbiguousTickerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name == "NoIdentifierProvidedError":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.exception("Unexpected error resolving fundamental identifier")
        raise HTTPException(
            status_code=500, detail="Failed to resolve identifier"
        ) from exc

    return result  # int | None


@router.get("/financials/{report_type}", response_model=APIResponse[list[Financial]])
@inject
async def get_financials(
    report_type: FinancialType,
    service: Annotated[FundamentalService, FromComponent()],
    metadata_service: Annotated[MetadataService, FromComponent()],
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
    resolved_id = _resolve_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 根据报表类型调用对应的方法（在线程池中执行，避免阻塞事件循环）
    df = None
    if report_type == FinancialType.BALANCE_SHEET:
        df = await asyncio.to_thread(
            service.get_balance_sheet,
            resolved_id,
            as_of_date,
        )
    elif report_type == FinancialType.INCOME_STATEMENT:
        df = await asyncio.to_thread(
            service.get_income_statement,
            resolved_id,
            as_of_date,
        )
    elif report_type == FinancialType.CASH_FLOW:
        df = await asyncio.to_thread(
            service.get_cash_flow,
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
    service: Annotated[FundamentalService, FromComponent()],
    metadata_service: Annotated[MetadataService, FromComponent()],
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
    resolved_id = _resolve_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.get_dividend, resolved_id, as_of_date)

    if df is None or df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    dividends = to_dividend_list(df)

    return APIResponse(data=dividends)


@router.get("/corporate-actions", response_model=APIResponse[list[CorporateAction]])
@inject
async def list_corporate_actions(
    service: Annotated[FundamentalService, FromComponent()],
    metadata_service: Annotated[MetadataService, FromComponent()],
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
        HTTPException: 400 如果 start_date > end_date

    """
    # 验证日期范围
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail=(
                f"start_date ({start_date}) cannot be greater than "
                f"end_date ({end_date})"
            ),
        )

    resolved_id = _resolve_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        service.list_corporate_actions,
        resolved_id,
        start_date,
        end_date,
    )

    if df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    actions = to_corporate_action_list(df)

    return APIResponse(data=actions)
