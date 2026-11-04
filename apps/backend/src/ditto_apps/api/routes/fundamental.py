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
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.errors import DateRangeError, FutureDateError
from ditto_apps.api.params import DateRangeQueryParams, PITQueryParams
from ditto_apps.api.utils.identifier import resolve_identifier_or_404
from ditto_apps.models.capital import (
    DisclosureRowsResponse,
    to_disclosure_rows,
)
from ditto_apps.models.common import (
    APIResponse,
    DataCoverageInfo,
    ReadSemantics,
)
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
    获取财务报表数据（pit_asof：as_of 可见版本，日粒度 as_of=上海日终）.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    修订多版本收敛到 as_of 可见的最新披露版本；行级透出
    knowledge_date/effective_from/effective_to（#628 事实/公告/版本分开）.

    Raises:
        FutureDateError: 400 如果 as_of_date 为未来日期
        NotFoundError: 404 如果标识符在 as_of_date 不可解析

    """
    _reject_future_date(params.as_of_date, "as_of_date")

    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="fundamental",
    )

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
        return APIResponse(data=[], read_semantics="pit_asof")

    # 转换为模型列表
    financials = to_financial_list(df, report_type)

    return APIResponse(data=financials, read_semantics="pit_asof")


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
    获取分红数据（pit_asof：as_of 可见版本，日粒度 as_of=上海日终）.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    未披露数值以 null 透出，不零填充（#628）.

    Raises:
        FutureDateError: 400 如果 as_of_date 为未来日期
        NotFoundError: 404 如果标识符在 as_of_date 不可解析

    """
    _reject_future_date(params.as_of_date, "as_of_date")

    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="fundamental",
    )

    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        _fetch_dividend,
        fundamental_facade,
        instrument_id=resolved_id,
        as_of_date=params.as_of_date,
        allow_experimental_data=params.allow_experimental_data,
    )

    if df is None or df.is_empty():
        return APIResponse(data=[], read_semantics="pit_asof")

    # 转换为模型列表
    dividends = to_dividend_list(df)

    return APIResponse(data=dividends, read_semantics="pit_asof")


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

    读取语义由 as_of_date 决定（#628）：给定=pit_asof（同事实键多版本
    收敛到最新可见披露）；缺省=latest_available（版本历史原样返回，
    多版本行可见，行级 knowledge/effective 轴可区分）.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        DateRangeError: 400 如果 start_date > end_date
        FutureDateError: 400 如果 as_of_date 为未来日期
        NotFoundError: 404 如果标识符不可解析

    """
    # 验证日期范围
    if params.start_date > params.end_date:
        raise DateRangeError(
            start_date=params.start_date.isoformat(),
            end_date=params.end_date.isoformat(),
        )

    _reject_future_date(params.as_of_date, "as_of_date")

    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="fundamental",
    )

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

    semantics: ReadSemantics = "pit_asof" if params.as_of_date else "latest_available"
    if df.is_empty():
        return APIResponse(data=[], read_semantics=semantics)

    # 转换为模型列表
    actions = to_corporate_action_list(df)

    return APIResponse(data=actions, read_semantics=semantics)


# ── #658 批次4b 消费接线：披露帧窗口读 ────────────────────────────────


@router.get(
    "/indicators",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="fundamental_get_indicators",
)
@inject
async def get_indicators(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[DateRangeQueryParams, Depends()],
) -> APIResponse[DisclosureRowsResponse]:
    """
    逐标的财务指标窗口读(report_date 窗口;110 指标列透传).

    knowledge_date=公告日;as_of 给定时按 knowledge_date<=as_of 收敛到
    最新公告版本(修订选版);跨年错位已由 #620 修复。
    """
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.end_date,
        domain="fundamental",
    )
    df = await asyncio.to_thread(
        fundamental_facade.get_fina_indicator,
        resolved_id,
        params.start_date.isoformat(),
        params.end_date.isoformat(),
        params.as_of_date.isoformat() if params.as_of_date else None,
        **{"allow_experimental_data": params.allow_experimental_data},
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="pit_asof" if params.as_of_date else "latest_available",
            data_coverage=_disclosure_coverage(coverage_facade, "fina_indicator"),
        ),
    )


@router.get(
    "/earnings-express",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="fundamental_get_earnings_express",
)
@inject
async def get_earnings_express(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    ticker: str = Query(..., description="裸代码, 如 000001(ticker 键库)"),
    start_date: date_type = Query(..., description="公告日窗口起点"),
    end_date: date_type = Query(..., description="公告日窗口终点"),
    allow_experimental_data: bool = Query(False),
) -> APIResponse[DisclosureRowsResponse]:
    """
    逐标的业绩快报窗口读(ann_date 公告事件;金额元).

    平日 0 行=无公告正常;audit_status 透出不伪称已审计;
    快报与三表非同颗粒度(已审数浓缩披露)。
    """
    df = await asyncio.to_thread(
        fundamental_facade.get_earnings_express,
        ticker,
        start_date.isoformat(),
        end_date.isoformat(),
        **{"allow_experimental_data": allow_experimental_data},
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_disclosure_coverage(coverage_facade, "earnings_express"),
        ),
    )


@router.get(
    "/earnings-forecast",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="fundamental_get_earnings_forecast",
)
@inject
async def get_earnings_forecast(
    fundamental_facade: Annotated[FundamentalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    ticker: str = Query(..., description="裸代码, 如 000001(ticker 键库)"),
    start_date: date_type = Query(..., description="公告日窗口起点"),
    end_date: date_type = Query(..., description="公告日窗口终点"),
    allow_experimental_data: bool = Query(False),
) -> APIResponse[DisclosureRowsResponse]:
    """
    逐标的业绩预告窗口读(ann_date 公告事件;净利润上下界万元).

    同日修订按 update_flag 独立版本;2024-01-31 源端翻页损坏按
    证据归因关闭(#658 批次2 §5.1),chunk 保持可重试。
    """
    df = await asyncio.to_thread(
        fundamental_facade.get_earnings_forecast,
        ticker,
        start_date.isoformat(),
        end_date.isoformat(),
        **{"allow_experimental_data": allow_experimental_data},
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_disclosure_coverage(coverage_facade, "earnings_forecast"),
        ),
    )


def _disclosure_coverage(
    coverage_facade: DatasetCoverageQueryFacade, dataset: str
) -> DataCoverageInfo | None:
    limit = coverage_facade.get(dataset)
    if limit is None:
        return None
    return DataCoverageInfo.from_view(limit)
