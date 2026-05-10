"""
Stock & Calendar 数据获取 — 从 TushareSource 提取的股票/日历 fetch 逻辑.

提供 fetch_calendar / fetch_stock_basic / fetch_stock_daily /
fetch_adj_factor / fetch_adj_factor_by_ticker / fetch_stock_limit /
fetch_stock_status / fetch_st_history 模块级函数，
供 TushareSource 的同名方法委托调用。
"""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter


def fetch_calendar(
    calendar: CalendarTushareAdapter,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch trading calendar.

    Args:
        calendar: Calendar 数据适配器.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        DataFrame with columns:
        - trade_date: Date
        - is_open: Boolean

    Raises:
        SourceFetchError: If fetch fails.

    """
    return calendar.fetch_calendar(start_date, end_date)


def fetch_stock_basic(
    stock: StockTushareAdapter,
    source_ticker: str | None = None,
) -> pl.DataFrame:
    """
    Fetch stock basic information.

    Supports two modes:
    - Batch mode: No source_ticker, fetch all stocks
    - Single mode: With source_ticker, fetch specific stock

    Args:
        stock: Stock 数据适配器.
        source_ticker: Stock code (e.g., "600519.SH"). Optional.

    Returns:
        DataFrame with columns:
        - source_ticker: Source code
        - ticker: Display ticker
        - name: Stock name
        - exchange: Exchange code
        - list_date: Listing date
        - list_status: Listing status

    Raises:
        SourceFetchError: If fetch fails.

    """
    return stock.fetch_stock_basic(source_ticker)


def fetch_stock_daily(
    stock: StockTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch stock daily OHLCV bars.

    Supports two query modes:
    - By date (batch): Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        stock: Stock 数据适配器.
        trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Required with source_ticker.
        end_date: End date (YYYY-MM-DD). Required with source_ticker.

    Returns:
        DataFrame with columns (same as ETF daily schema):
        - source_ticker: Source code
        - trade_date: Date
        - open, high, low, close, pre_close: Float64
        - volume, amount: Float64
        - pct_change: Float64

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.
        SourceTransformationError: If data transformation fails.

    """
    return stock.fetch_stock_daily(
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_adj_factor(
    stock: StockTushareAdapter,
    trade_date: str,
) -> pl.DataFrame:
    """
    Fetch stock adjustment factors.

    Args:
        stock: Stock 数据适配器.
        trade_date: Trade date (YYYY-MM-DD).

    Returns:
        DataFrame with columns:
        - source_ticker: Source code
        - trade_date: Date
        - knowledge_date: Date (PIT safety: when this data became known)
        - adj_factor: Float64

    Raises:
        SourceFetchError: If fetch fails.

    """
    return stock.fetch_adj_factor(trade_date)


def fetch_adj_factor_by_ticker(
    stock: StockTushareAdapter,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch stock adjustment factors by ticker (for backfill).

    Args:
        stock: Stock 数据适配器.
        ts_code: Stock code (e.g., "000001.SZ").
        start_date: Start date (YYYYMMDD).
        end_date: End date (YYYYMMDD).

    Returns:
        DataFrame with columns:
        - source_ticker: Source code
        - trade_date: Date
        - knowledge_date: Date
        - adj_factor: Float64

    Raises:
        SourceFetchError: If fetch fails.

    """
    return stock.fetch_adj_factor_by_ticker(ts_code, start_date, end_date)


def fetch_stock_limit(
    stock: StockTushareAdapter,
    trade_date: str,
) -> pl.DataFrame:
    """
    Fetch stock limit up/down prices (B.3).

    Args:
        stock: Stock 数据适配器.
        trade_date: Trade date (YYYY-MM-DD).

    Returns:
        DataFrame with columns:
        - source_ticker: Source code (e.g., "000001.SZ")
        - trade_date: Date
        - up_limit: Float64 (涨停价)
        - down_limit: Float64 (跌停价)

    Raises:
        SourceFetchError: If fetch fails.

    """
    return stock.fetch_stock_limit(trade_date)


def fetch_stock_status(
    stock: StockTushareAdapter,
    trade_date: str,
) -> pl.DataFrame:
    """
    Fetch stock status information (B.3).

    Combines data from multiple Tushare APIs:
    - suspend_d: 停牌信息
    - stock_st: ST状态
    - stock_basic: list_status

    Args:
        stock: Stock 数据适配器.
        trade_date: Trade date (YYYY-MM-DD).

    Returns:
        DataFrame with columns:
        - source_ticker: Source code (e.g., "000001.SZ")
        - trade_date: Date
        - is_suspended: Boolean
        - suspend_timing: Utf8 (e.g., "09:30-10:00" or null)
        - is_st: Boolean
        - st_type: Utf8 (e.g., "ST" or null)
        - list_status: Utf8 (L=正常, D=退市, P=暂停)

    Raises:
        SourceFetchError: If fetch fails.

    """
    return stock.fetch_stock_status(trade_date)


def fetch_st_history(
    stock: StockTushareAdapter,
    *,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch ST status change history (B.3).

    Args:
        stock: Stock 数据适配器.
        ts_code: Stock code (e.g., "000001.SZ"). None for all stocks.
        start_date: Start date (YYYY-MM-DD). None for no limit.
        end_date: End date (YYYY-MM-DD). None for no limit.

    Returns:
        DataFrame with columns:
        - source_ticker: Stock code (e.g., "000001.SZ")
        - change_date: Date of status change (Date)
        - end_date: Date when status ended (Date), NULL if still active
        - change_reason: Reason for change (e.g., "ST", "*ST", "撤销ST")

    Raises:
        SourceFetchError: If fetch fails.

    """
    return stock.fetch_st_history(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
    )
