"""
Fundamental + Capital 数据获取 — 从 TushareSource 提取的基本面/资金 fetch 逻辑.

提供 fetch_balance_sheet / fetch_income_statement / fetch_cash_flow /
fetch_dividend / fetch_corporate_actions / fetch_valuation_metrics /
fetch_margin_trading / fetch_pledge_ratio 模块级函数，
供 TushareSource 的同名方法委托调用。
"""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare._fundamental import (
    fetch_balance_sheet as _fetch_balance_sheet,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_cash_flow as _fetch_cash_flow,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_corporate_actions as _fetch_corporate_actions,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_dividend as _fetch_dividend,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_income_statement as _fetch_income_statement,
)
from ditto_data.sources.tushare._utils import to_compact_date
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter


def fetch_balance_sheet(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch balance sheet data（委托给 _fundamental 模块）."""
    return _fetch_balance_sheet(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_income_statement(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch income statement data（委托给 _fundamental 模块）."""
    return _fetch_income_statement(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_cash_flow(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch cash flow data（委托给 _fundamental 模块）."""
    return _fetch_cash_flow(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_dividend(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch dividend data（委托给 _fundamental 模块）."""
    return _fetch_dividend(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_corporate_actions(
    fundamental: FundamentalTushareAdapter,
    trade_date: str,
) -> pl.DataFrame:
    """Fetch corporate actions data（委托给 _fundamental 模块）."""
    return _fetch_corporate_actions(
        fundamental,
        to_compact_date,
        trade_date,
    )


# ── Capital 相关方法（估值/融资融券/质押） ──────────────────────────


def fetch_valuation_metrics(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch valuation metrics data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        capital: Capital 数据适配器.
        trade_date: 交易日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with valuation_metrics SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询
        compact_date = to_compact_date(trade_date)
        return capital.fetch_valuation_metrics(trade_date=compact_date)

    # 按标的查询
    if not source_ticker:
        raise ValueError("按标的查询必须指定 source_ticker")
    compact_start = to_compact_date(start_date) if start_date else None
    compact_end = to_compact_date(end_date) if end_date else None
    return capital.fetch_valuation_metrics(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def fetch_margin_trading(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch margin trading data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        capital: Capital 数据适配器.
        trade_date: 交易日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with margin_trading SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询
        compact_date = to_compact_date(trade_date)
        return capital.fetch_margin_trading(trade_date=compact_date)

    # 按标的查询
    if not source_ticker:
        raise ValueError("按标的查询必须指定 source_ticker")
    compact_start = to_compact_date(start_date) if start_date else None
    compact_end = to_compact_date(end_date) if end_date else None
    return capital.fetch_margin_trading(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def fetch_pledge_ratio(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch pledge ratio data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker (start_date/end_date ignored)

    Args:
        capital: Capital 数据适配器.
        trade_date: 报告期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with pledge_ratio SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询
        compact_date = to_compact_date(trade_date)
        return capital.fetch_pledge_ratio(report_date=compact_date)

    # 按标的查询（pledge_ratio API 不支持日期范围）
    return capital.fetch_pledge_ratio(ts_code=source_ticker)
