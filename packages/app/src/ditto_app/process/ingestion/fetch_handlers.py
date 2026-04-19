"""
数据集获取处理器映射.

从 ``IngestionCoordinator._fetch_data`` 和 ``_fetch_by_dataset`` 提取。
提供 Dataset→lambda 映射，将数据集枚举路由到正确的 DataSource 方法。
"""

from __future__ import annotations

from collections.abc import Callable

import polars as pl
from ditto_data.models import FX_CODE_TO_INSTRUMENT_ID, Dataset
from ditto_data.sources.base import DataSource
from ditto_kernel.instrument import InstrumentIngestParams

__all__ = [
    "build_daily_fetch_handlers",
    "build_instrument_fetch_handlers",
]


def build_daily_fetch_handlers(
    source: DataSource,
    trade_date: str,
    *,
    fetch_commodity_daily: Callable[[str], pl.DataFrame],
    get_cached_index_codes: Callable[[], list[str]],
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """
    构建日期级获取处理器映射.

    Args:
        source: 数据源.
        trade_date: 交易日期 (YYYY-MM-DD).
        fetch_commodity_daily: 商品数据获取函数.
        get_cached_index_codes: 获取缓存的指数代码列表.

    Returns:
        Dataset → 无参获取函数映射.

    """
    _calendar_year = trade_date[:4]

    return {
        Dataset.CALENDAR: lambda y=_calendar_year: source.fetch_calendar(
            f"{y}-01-01", f"{y}-12-31"
        ),
        Dataset.STOCK_BASIC: source.fetch_stock_basic,
        Dataset.ETF_BASIC: source.fetch_etf_basic,
        Dataset.STOCK_DAILY: lambda: source.fetch_stock_daily(trade_date),
        Dataset.ETF_DAILY: lambda: source.fetch_etf_daily(trade_date),
        Dataset.STOCK_STATUS: lambda: source.fetch_stock_status(trade_date),
        Dataset.ADJ_FACTOR: lambda: source.fetch_adj_factor(trade_date),
        Dataset.FUND_ADJ: lambda: source.fetch_fund_adj(trade_date),
        Dataset.BALANCE_SHEET: lambda: source.fetch_balance_sheet(trade_date),
        Dataset.INCOME_STATEMENT: lambda: source.fetch_income_statement(trade_date),
        Dataset.CASH_FLOW: lambda: source.fetch_cash_flow(trade_date),
        Dataset.DIVIDEND: lambda: source.fetch_dividend(trade_date),
        Dataset.VALUATION_METRICS: lambda: source.fetch_valuation_metrics(trade_date),
        Dataset.MARGIN_TRADING: lambda: source.fetch_margin_trading(trade_date),
        Dataset.PLEDGE_RATIO: lambda: source.fetch_pledge_ratio(trade_date),
        Dataset.MACRO_INDICATORS: lambda: source.fetch_macro_indicators(trade_date),
        Dataset.CORPORATE_ACTIONS: lambda: source.fetch_corporate_actions(trade_date),
        Dataset.INDEX_BASIC: source.fetch_index_basic,
        Dataset.INDEX_DAILY: lambda: source.fetch_index_daily(
            trade_date,
            ts_codes=get_cached_index_codes(),
        ),
        Dataset.FX_DAILY: lambda: source.fetch_fx_daily(
            ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
            start_date=trade_date,
            end_date=trade_date,
        ),
        Dataset.COMMODITY_DAILY: lambda: fetch_commodity_daily(trade_date),
    }


def build_instrument_fetch_handlers(
    source: DataSource,
    source_ticker: str,
    params: InstrumentIngestParams,
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """
    构建按标的获取处理器映射.

    Args:
        source: 数据源.
        source_ticker: 数据源代码.
        params: 摄取参数.

    Returns:
        Dataset → 无参获取函数映射.

    """
    return {
        # Market 域
        Dataset.STOCK_DAILY: lambda: source.fetch_stock_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.ETF_DAILY: lambda: source.fetch_etf_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.INDEX_DAILY: lambda: source.fetch_index_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.ADJ_FACTOR: lambda: source.fetch_adj_factor_by_ticker(
            ts_code=source_ticker,
            start_date=params.start_date.replace("-", ""),
            end_date=params.end_date.replace("-", ""),
        ),
        Dataset.FUND_ADJ: lambda: source.fetch_fund_adj(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        # Fundamental 域
        Dataset.BALANCE_SHEET: lambda: source.fetch_balance_sheet(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.INCOME_STATEMENT: lambda: source.fetch_income_statement(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.CASH_FLOW: lambda: source.fetch_cash_flow(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.DIVIDEND: lambda: source.fetch_dividend(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        # Capital 域
        Dataset.VALUATION_METRICS: lambda: source.fetch_valuation_metrics(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.MARGIN_TRADING: lambda: source.fetch_margin_trading(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.PLEDGE_RATIO: lambda: source.fetch_pledge_ratio(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
    }
