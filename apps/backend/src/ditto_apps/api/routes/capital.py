"""
Capital 域 API 路由.

maturity: experimental
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.capital_profile import (
    CapitalProfileQueryFacade,
    CapitalProfileRequest,
)
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.errors import DateRangeError, FutureDateError
from ditto_apps.api.params import DateRangeQueryParams, PITQueryParams
from ditto_apps.api.utils.identifier import (
    resolve_identifier_or_404,
)
from ditto_apps.models.capital import (
    CapitalProfileQuery,
    CapitalProfileResponse,
    DisclosureRowsResponse,
    Margin,
    MarginBlock,
    MoneyflowBlock,
    TopInstBlock,
    TopListBlock,
    Valuation,
    to_disclosure_rows,
    to_margin_list,
    to_margin_profile_rows,
    to_moneyflow_rows,
    to_top_inst_rows,
    to_top_list_rows,
    to_valuation_list,
)
from ditto_apps.models.common import APIResponse, DataCoverageInfo

router = APIRouter(prefix="/capital", tags=["capital"])

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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
    获取融资融券数据（pit_asof：as_of 可见版本，日粒度 as_of=上海日终）.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        NotFoundError: 404 如果标识符在 as_of_date 不可解析

    """
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        as_of_date=as_of_date,
        domain="capital",
    )

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

    return APIResponse(data=margins, read_semantics="pit_asof")


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
    获取估值指标数据（pit_asof：as_of 可见版本，日粒度 as_of=上海日终）.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    Raises:
        NotFoundError: 404 如果标识符在 as_of_date 不可解析

    """
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        as_of_date=as_of_date,
        domain="capital",
    )

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

    return APIResponse(data=valuations, read_semantics="pit_asof")


def _coverage(
    coverage_facade: DatasetCoverageQueryFacade, dataset: str
) -> DataCoverageInfo | None:
    limit = coverage_facade.get(dataset)
    return DataCoverageInfo.from_view(limit) if limit is not None else None


def _block_sources(rows: pl.DataFrame) -> list[str]:
    """块内行来源去重升序(来源身份随画像传播)."""
    if rows.is_empty() or "source" not in rows.columns:
        return []
    return sorted(str(item) for item in rows["source"].unique().to_list())


@router.post(
    "/profile",
    response_model=APIResponse[CapitalProfileResponse],
    operation_id="capital_post_profile",
)
@inject
async def post_capital_profile(
    query: CapitalProfileQuery,
    profile_facade: Annotated[CapitalProfileQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
) -> APIResponse[CapitalProfileResponse]:
    """
    个股资金画像（#658 批次3：四数据集同标的同窗口联看）.

    必需块 moneyflow/top_list/top_inst（latest_available＝库内现存行，无 PIT
    过滤）；可选块 margin_trading（pit_asof=end_date）带实际末端与待补列表
    （迟发数据按 09:15 披露承诺，待补窗=尾部 5 个交易日，与夜修滑窗对齐）。
    每块携带 data_coverage 覆盖限制快照；无事件/空窗是合法状态，不冒充失败。

    标识符三选一（优先级 instrument_id > standard_ticker > ticker），
    按 end_date 解析。四数据集均 experimental，须显式
    allow_experimental_data=true。

    Raises:
        NotFoundError: 404 如果标识符在 end_date 不可解析

    """
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=query.instrument_id,
        standard_ticker=query.standard_ticker,
        ticker=query.ticker,
        as_of_date=query.end_date,
        domain="capital",
    )
    result = await asyncio.to_thread(
        profile_facade.get_profile,
        CapitalProfileRequest(
            instrument_id=resolved_id,
            start=query.start_date,
            end=query.end_date,
            allow_experimental_data=query.allow_experimental_data,
            today=datetime.now(_SHANGHAI_TZ).date(),
        ),
    )
    profile = CapitalProfileResponse(
        instrument_id=resolved_id,
        window={
            "start": query.start_date.isoformat(),
            "end": query.end_date.isoformat(),
        },
        moneyflow=MoneyflowBlock(
            rows=to_moneyflow_rows(result.moneyflow.rows),
            latest_trade_date=result.moneyflow.latest_trade_date,
            sources=_block_sources(result.moneyflow.rows),
            data_coverage=_coverage(coverage_facade, "moneyflow"),
        ),
        top_list=TopListBlock(
            rows=to_top_list_rows(result.top_list.rows),
            latest_trade_date=result.top_list.latest_trade_date,
            sources=_block_sources(result.top_list.rows),
            data_coverage=_coverage(coverage_facade, "top_list"),
        ),
        top_inst=TopInstBlock(
            rows=to_top_inst_rows(result.top_inst.rows),
            latest_trade_date=result.top_inst.latest_trade_date,
            sources=_block_sources(result.top_inst.rows),
            data_coverage=_coverage(coverage_facade, "top_inst"),
        ),
        margin_trading=MarginBlock(
            rows=to_margin_profile_rows(result.margin_trading.rows),
            latest_trade_date=result.margin_trading.latest_trade_date,
            sources=_block_sources(result.margin_trading.rows),
            pending_trade_dates=list(result.margin_trading.pending_trade_dates),
            read_error=result.margin_trading.read_error,
            data_coverage=_coverage(coverage_facade, "margin_trading"),
        ),
    )
    # 混合语义响应(margin=pit_asof、其余=latest_available):信封不声明
    # 单一语义,各块 read_semantics 自持(correctness F4)。
    return APIResponse(data=profile)


# ── #658 批次4b 消费接线：北向双库/持仓双榜 GET ────────────────────────


@router.get(
    "/hk-hold",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="capital_get_hk_hold",
)
@inject
async def get_hk_hold(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[DateRangeQueryParams, Depends()],
) -> APIResponse[DisclosureRowsResponse]:
    """
    逐标的北向持股窗口读(latest_available;2024-08-19 知识日分段).

    2024-08-19 起季度披露制:非季末交易日无行=制度性缺席不是缺口
    (docs/data/event-disclosure-verification.md 分段详证)。
    """
    _validate_disclosure_window(params.start_date, params.end_date, params.as_of_date)
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.end_date,
        domain="capital",
    )
    df = await asyncio.to_thread(
        capital_facade.get_hk_hold,
        resolved_id,
        params.start_date.isoformat(),
        params.end_date.isoformat(),
        **_experimental_kwargs(params.allow_experimental_data),
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "hk_hold"),
        ),
    )


@router.get(
    "/hsgt-top10",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="capital_get_hsgt_top10",
)
@inject
async def get_hsgt_top10(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    start_date: date = Query(..., description="窗口起点"),
    end_date: date = Query(..., description="窗口终点"),
    market_type: str | None = Query(
        None, description="1=沪股通 3=深股通(本地库仅北向);缺省全通道"
    ),
    allow_experimental_data: bool = Query(False),
) -> APIResponse[DisclosureRowsResponse]:
    """
    市场级沪深港通十大成交窗口读(latest_available;每日 20 行事件型).

    2024-08-19 改制后 buy/sell/net_amount 官方停披——null 保留不填零。
    """
    _validate_disclosure_window(start_date, end_date)
    df = await asyncio.to_thread(
        capital_facade.get_hsgt_top10s,
        start_date.isoformat(),
        end_date.isoformat(),
        market_type,
        **_experimental_kwargs(allow_experimental_data),
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "hsgt_top10"),
        ),
    )


@router.get(
    "/top10-holders",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="capital_get_top10_holders",
)
@inject
async def get_top10_holders(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[DateRangeQueryParams, Depends()],
) -> APIResponse[DisclosureRowsResponse]:
    """
    逐标的前十大股东窗口读(latest_available;report_date 报告期粒度).

    修订=新公告日(knowledge_date)版本行并存;名单跌出≠清仓;
    hold_change 0=不变 null=新进;两榜与流通榜语义独立不互推。
    """
    _validate_disclosure_window(params.start_date, params.end_date, params.as_of_date)
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.end_date,
        domain="capital",
    )
    df = await asyncio.to_thread(
        capital_facade.get_top10_holders,
        resolved_id,
        params.start_date.isoformat(),
        params.end_date.isoformat(),
        **_experimental_kwargs(params.allow_experimental_data),
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "top10_holders"),
        ),
    )


@router.get(
    "/top10-floatholders",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="capital_get_top10_floatholders",
)
@inject
async def get_top10_floatholders(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[DateRangeQueryParams, Depends()],
) -> APIResponse[DisclosureRowsResponse]:
    """逐标的前十大流通股东窗口读(独立流通股榜口径)."""
    _validate_disclosure_window(params.start_date, params.end_date, params.as_of_date)
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.end_date,
        domain="capital",
    )
    df = await asyncio.to_thread(
        capital_facade.get_top10_floatholders,
        resolved_id,
        params.start_date.isoformat(),
        params.end_date.isoformat(),
        **_experimental_kwargs(params.allow_experimental_data),
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "top10_floatholders"),
        ),
    )


@router.get(
    "/pledge-ratio",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="capital_get_pledge_ratio",
)
@inject
async def get_pledge_ratio(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[PITQueryParams, Depends()],
) -> APIResponse[DisclosureRowsResponse]:
    """逐标的质押比 PIT 读(report_date 锚;周频披露节奏非日历完整)."""
    _validate_disclosure_window(as_of=params.as_of_date)
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.as_of_date,
        domain="capital",
    )
    df = await asyncio.to_thread(
        capital_facade.get_pledge_ratio,
        resolved_id,
        params.as_of_date,
        **_experimental_kwargs(params.allow_experimental_data),
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="pit_asof",
            data_coverage=_coverage(coverage_facade, "pledge_ratio"),
        ),
    )


@router.get(
    "/index-valuation",
    response_model=APIResponse[DisclosureRowsResponse],
    operation_id="capital_get_index_valuation",
)
@inject
async def get_index_valuation(
    capital_facade: Annotated[CapitalQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    metadata_facade: Annotated[MetadataQueryFacade, FromComponent()],
    params: Annotated[DateRangeQueryParams, Depends()],
) -> APIResponse[DisclosureRowsResponse]:
    """
    逐指数估值窗口读(latest_available;total_mv/float_mv 元).

    市值单位元(与个股 daily_basic 万元不同,doc_id=128);同日多版本
    (knowledge_date=摄取日)收敛到最新;标的须为指数(instrument 解析)。
    """
    _validate_disclosure_window(params.start_date, params.end_date, params.as_of_date)
    resolved_id = resolve_identifier_or_404(
        metadata_facade,
        instrument_id=params.instrument_id,
        standard_ticker=params.standard_ticker,
        ticker=params.ticker,
        as_of_date=params.end_date,
        domain="capital",
    )
    df = await asyncio.to_thread(
        capital_facade.get_index_valuation,
        resolved_id,
        params.start_date.isoformat(),
        params.end_date.isoformat(),
        **_experimental_kwargs(params.allow_experimental_data),
    )
    return APIResponse(
        data=DisclosureRowsResponse(
            rows=to_disclosure_rows(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "index_valuation"),
        ),
    )


def _validate_disclosure_window(
    start: date | None = None,
    end: date | None = None,
    as_of: date | None = None,
) -> None:
    """倒置窗口/未来 as_of fail-closed(fundamental corporate-actions 先例)."""
    if start is not None and end is not None and start > end:
        raise DateRangeError(start_date=start.isoformat(), end_date=end.isoformat())
    if as_of is not None and as_of > date.today():
        raise FutureDateError(field_name="as_of_date", date_value=as_of.isoformat())
