"""基本面数据 API 路由."""

import asyncio
from datetime import date
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.services.fundamental_service import FundamentalService
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


@router.get("/financials/{report_type}", response_model=APIResponse[list[Financial]])
@inject
async def get_financials(
    report_type: FinancialType,
    instrument_id: str = Query(..., description="标的 ID"),
    as_of_date: date = Query(..., description="PIT 查询日期"),
    service: Annotated[FundamentalService, FromComponent()] = None,  # type: ignore[assignment]
) -> APIResponse[list[Financial]]:
    """
    获取财务报表数据.

    Args:
        report_type: 财务报表类型 (balance_sheet/income_statement/cash_flow)
        instrument_id: 标的 ID
        as_of_date: PIT 查询日期
        service: FundamentalService 依赖注入

    Returns:
        APIResponse 包含财务报表数据列表

    """
    # 根据报表类型调用对应的方法（在线程池中执行，避免阻塞事件循环）
    df = None
    if report_type == FinancialType.BALANCE_SHEET:
        df = await asyncio.to_thread(
            service.get_balance_sheet,
            instrument_id,
            as_of_date,
        )
    elif report_type == FinancialType.INCOME_STATEMENT:
        df = await asyncio.to_thread(
            service.get_income_statement,
            instrument_id,
            as_of_date,
        )
    elif report_type == FinancialType.CASH_FLOW:
        df = await asyncio.to_thread(
            service.get_cash_flow,
            instrument_id,
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
    instrument_id: str = Query(..., description="标的 ID"),
    as_of_date: date = Query(..., description="PIT 查询日期"),
    service: Annotated[FundamentalService, FromComponent()] = None,  # type: ignore[assignment]
) -> APIResponse[list[Dividend]]:
    """
    获取分红数据.

    Args:
        instrument_id: 标的 ID
        as_of_date: PIT 查询日期
        service: FundamentalService 依赖注入

    Returns:
        APIResponse 包含分红数据列表

    """
    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.get_dividend, instrument_id, as_of_date)

    if df is None or df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    dividends = to_dividend_list(df)

    return APIResponse(data=dividends)


@router.get("/corporate-actions", response_model=APIResponse[list[CorporateAction]])
@inject
async def list_corporate_actions(
    instrument_id: str = Query(..., description="标的 ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    service: Annotated[FundamentalService, FromComponent()] = None,  # type: ignore[assignment]
) -> APIResponse[list[CorporateAction]]:
    """
    查询公司行动列表.

    Args:
        instrument_id: 标的 ID
        start_date: 开始日期
        end_date: 结束日期
        service: FundamentalService 依赖注入

    Returns:
        APIResponse 包含公司行动列表

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

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        service.list_corporate_actions,
        instrument_id,
        start_date,
        end_date,
    )

    if df.is_empty():
        return APIResponse(data=[])

    # 转换为模型列表
    actions = to_corporate_action_list(df)

    return APIResponse(data=actions)
