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
from ditto_application.queries.capital_profile import (
    CapitalProfileQueryFacade,
    CapitalProfileRequest,
)
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from fastapi import APIRouter, Query

from ditto_apps.api.utils.identifier import (
    resolve_identifier_or_404,
)
from ditto_apps.models.capital import (
    CapitalProfileQuery,
    CapitalProfileResponse,
    Margin,
    MarginBlock,
    MoneyflowBlock,
    TopInstBlock,
    TopListBlock,
    Valuation,
    to_margin_list,
    to_moneyflow_rows,
    to_top_inst_rows,
    to_top_list_rows,
    to_valuation_list,
)
from ditto_apps.models.common import APIResponse, DataCoverageInfo

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
            data_coverage=_coverage(coverage_facade, "moneyflow"),
        ),
        top_list=TopListBlock(
            rows=to_top_list_rows(result.top_list.rows),
            latest_trade_date=result.top_list.latest_trade_date,
            data_coverage=_coverage(coverage_facade, "top_list"),
        ),
        top_inst=TopInstBlock(
            rows=to_top_inst_rows(result.top_inst.rows),
            latest_trade_date=result.top_inst.latest_trade_date,
            data_coverage=_coverage(coverage_facade, "top_inst"),
        ),
        margin_trading=MarginBlock(
            rows=to_margin_list(result.margin_trading.rows),
            latest_trade_date=result.margin_trading.latest_trade_date,
            pending_trade_dates=list(result.margin_trading.pending_trade_dates),
            data_coverage=_coverage(coverage_facade, "margin_trading"),
        ),
    )
    return APIResponse(
        data=profile,
        read_semantics="latest_available",
    )
