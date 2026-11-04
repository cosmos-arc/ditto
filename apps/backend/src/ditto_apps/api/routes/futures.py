"""
Futures (期货) 模 API 路由（#658 批次4c）.

maturity: experimental
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.futures import FuturesQueryFacade
from fastapi import APIRouter, Query

from ditto_apps.models.common import APIResponse, DataCoverageInfo
from ditto_apps.models.futures import (
    FuturesBarsQuery,
    FuturesBarsResponse,
    FuturesContractsResponse,
    to_futures_bar_list,
    to_futures_contract_list,
)

router = APIRouter(prefix="/futures", tags=["futures"])


def _coverage(
    coverage_facade: DatasetCoverageQueryFacade, dataset: str
) -> DataCoverageInfo | None:
    limit = coverage_facade.get(dataset)
    return DataCoverageInfo.from_view(limit) if limit is not None else None


@router.post(
    "/bars",
    response_model=APIResponse[FuturesBarsResponse],
    operation_id="futures_post_bars",
)
@inject
async def post_bars(
    query: FuturesBarsQuery,
    facade: Annotated[FuturesQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
) -> APIResponse[FuturesBarsResponse]:
    """
    查询期货合约日线（latest_available：同日多版本收敛至最新摄取日）.

    合约以 source_ticker（ts_code 形态，如 "RB2410.SHF"）为键，不映射
    instrument_id；六所（SHFE/CZCE/DCE/INE/CFFEX/GFEX）实际合约，含到期
    前完整日线。amount 万元；首日 pre_settle 与无成交日 OHLC 以 null 透出。
    limit 取窗口内最新 N 行（按交易日）；空 source_tickers 列表拒绝。

    Raises:
        AppQueryError: 400 未显式 allow_experimental_data 时拒绝

    Args:
        query: 查询参数
            - source_tickers: 合约代码列表 (可选, 缺省=全部合约, 空列表拒绝)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 窗口内最新 N 行 (默认 1000, 范围 1-10000)
            - allow_experimental_data: 显式允许 experimental 数据集
        facade: FuturesQueryFacade 依赖注入
        coverage_facade: 覆盖限制查询 facade

    Returns:
        APIResponse 包含期货日线数据（bars+语义+知界）

    """
    df = await asyncio.to_thread(
        facade.get_futures_daily,
        query.start_date.isoformat() if query.start_date else None,
        query.end_date.isoformat() if query.end_date else None,
        query.source_tickers,
        allow_experimental_data=query.allow_experimental_data,
    )
    if not df.is_empty() and df.height > query.limit:
        # 最新 N 行：按交易日倒序截断后恢复升序（图表入口取近端）。
        df = (
            df.sort("trade_date", descending=True)
            .head(query.limit)
            .sort(["trade_date", "source_ticker"])
        )
    return APIResponse(
        data=FuturesBarsResponse(
            bars=to_futures_bar_list(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "futures_daily"),
        ),
    )


@router.get(
    "/contracts",
    response_model=APIResponse[FuturesContractsResponse],
    operation_id="futures_get_contracts",
)
@inject
async def get_contracts(
    facade: Annotated[FuturesQueryFacade, FromComponent()],
    coverage_facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
    exchange: str | None = Query(
        None, description="交易所过滤 (SHFE/CZCE/DCE/INE/CFFEX/GFEX)"
    ),
    fut_code: str | None = Query(None, description="品种代码过滤 (如 RB)"),
    allow_experimental_data: bool = Query(
        False,
        description="显式允许 experimental 数据集进入研究态查询",
    ),
) -> APIResponse[FuturesContractsResponse]:
    """
    查询期货合约身份（与日线同范围，含已到期合约）.

    list_date/delist_date 为源端声明窗口（非本地观察）；delist_date null=
    未提供而非在市推断；source/knowledge_date 随行（来源与快照摄取日传播）。

    Raises:
        AppQueryError: 400 未显式 allow_experimental_data 时拒绝

    """
    df = await asyncio.to_thread(
        facade.get_futures_contracts,
        exchange,
        fut_code,
        allow_experimental_data=allow_experimental_data,
    )
    return APIResponse(
        data=FuturesContractsResponse(
            contracts=to_futures_contract_list(df),
            read_semantics="latest_available",
            data_coverage=_coverage(coverage_facade, "futures_basic"),
        ),
    )
