"""
基本面数据获取 — 从 TushareSource 提取的基本面 fetch 逻辑.

提供 fetch_balance_sheet / fetch_income_statement / fetch_cash_flow /
fetch_dividend / fetch_corporate_actions 模块级函数，
供 TushareSource 的同名方法委托调用。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import polars as pl

from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter


def fetch_balance_sheet(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch balance sheet data.

    Supports two query modes:
    - By date batch: Specify trade_date (uses VIP API)
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 公告日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Required with source_ticker.
        end_date: End date (YYYY-MM-DD). Required with source_ticker.

    Returns:
        DataFrame with balance_sheet SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询（使用 VIP API）
        compact_date = to_compact_date(trade_date)
        return fundamental.fetch_balance_sheet_vip(ann_date=compact_date)

    # 按标的查询
    if not source_ticker or not start_date or not end_date:
        raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
    compact_start = to_compact_date(start_date)
    compact_end = to_compact_date(end_date)
    return fundamental.fetch_balance_sheet(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def fetch_income_statement(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch income statement data.

    Supports two query modes:
    - By date batch: Specify trade_date (uses VIP API)
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 公告日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Required with source_ticker.
        end_date: End date (YYYY-MM-DD). Required with source_ticker.

    Returns:
        DataFrame with income_statement SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询（使用 VIP API）
        compact_date = to_compact_date(trade_date)
        return fundamental.fetch_income_statement_vip(ann_date=compact_date)

    # 按标的查询
    if not source_ticker or not start_date or not end_date:
        raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
    compact_start = to_compact_date(start_date)
    compact_end = to_compact_date(end_date)
    return fundamental.fetch_income_statement(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def fetch_cash_flow(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch cash flow data.

    Supports two query modes:
    - By date batch: Specify trade_date (uses VIP API)
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 公告日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Required with source_ticker.
        end_date: End date (YYYY-MM-DD). Required with source_ticker.

    Returns:
        DataFrame with cash_flow SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询（使用 VIP API）
        compact_date = to_compact_date(trade_date)
        return fundamental.fetch_cash_flow_vip(ann_date=compact_date)

    # 按标的查询
    if not source_ticker or not start_date or not end_date:
        raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
    compact_start = to_compact_date(start_date)
    compact_end = to_compact_date(end_date)
    return fundamental.fetch_cash_flow(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def fetch_dividend(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch dividend data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 除权除息日 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with dividend SourceSchema fields.

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
        return fundamental.fetch_dividend(ex_date=compact_date)

    result = fundamental.fetch_dividend(ts_code=source_ticker)
    if result.is_empty() or start_date is None or end_date is None:
        return result
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    return result.filter(
        pl.col("knowledge_date").is_not_null()
        & pl.col("knowledge_date").is_between(start, end, closed="both")
    )


def fetch_corporate_actions(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    trade_date: str,
) -> pl.DataFrame:
    """
    Fetch corporate actions data.

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 交易日期 (YYYY-MM-DD).

    Returns:
        DataFrame with corporate_actions SourceSchema fields.

    """
    compact_date = to_compact_date(trade_date)
    return fundamental.fetch_corporate_actions(
        ann_date=compact_date,
    )
