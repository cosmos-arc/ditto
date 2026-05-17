"""
ETF/Index/Industry 数据获取 — 从 TushareSource 提取的 ETF/指数/行业 fetch 逻辑.

提供 fetch_etf_basic / fetch_etf_daily / fetch_fund_adj /
fetch_index_basic / fetch_index_daily / fetch_sw_industry 模块级函数，
供 TushareSource 的同名方法委托调用。
"""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter
from ditto_data.sources.tushare.adapters.industry import IndustryTushareAdapter


def fetch_etf_basic(
    etf: ETFTushareAdapter,
) -> pl.DataFrame:
    """
    Fetch ETF basic information.

    Args:
        etf: ETF 数据适配器.

    Returns:
        DataFrame with columns:
        - source_ticker: Source code (e.g., "510300.SH")
        - ticker: Display ticker (e.g., "510300")
        - name: ETF name
        - exchange: Exchange code
        - list_date: Listing date

    Raises:
        SourceFetchError: If fetch fails.

    """
    return etf.fetch_etf_basic()


def fetch_etf_daily(
    etf: ETFTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch ETF daily OHLCV bars.

    Supports two query modes:
    - By date (batch): Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        etf: ETF 数据适配器.
        trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "510300.SH").
        start_date: Start date (YYYY-MM-DD). Required with source_ticker.
        end_date: End date (YYYY-MM-DD). Required with source_ticker.

    Returns:
        DataFrame with columns (matching ETF_DAILY_SCHEMA):
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
    return etf.fetch_etf_daily(
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_fund_adj(
    etf: ETFTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch ETF/fund adjustment factors.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        etf: ETF 数据适配器.
        trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "510300.SH").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with columns:
        - source_ticker: Source code
        - trade_date: Date
        - adj_factor: Float64

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    return etf.fetch_fund_adj(
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_index_basic(
    index: IndexTushareAdapter,
) -> pl.DataFrame:
    """
    Fetch index basic information.

    Args:
        index: Index 数据适配器.

    Returns:
        DataFrame with columns:
        - source_ticker: Source code (e.g., "000001.SH")
        - ticker: Display ticker (e.g., "000001")
        - name: Index name
        - exchange: Exchange code
        - list_date: Listing date

    Raises:
        SourceFetchError: If fetch fails.

    """
    return index.fetch_basic()


def fetch_index_daily(
    index: IndexTushareAdapter,
    *,
    trade_date: str | None = None,
    ts_codes: list[str] | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch index daily OHLCV bars.

    Supports two query modes:
    - By date (batch): Specify trade_date (optionally with ts_codes filter)
    - By ticker + date range: Specify source_ticker + start_date + end_date

    注意：Tushare index_daily API 要求 ts_code 参数，
    此方法逐个查询指定指数列表并合并结果。

    Args:
        index: Index 数据适配器.
        trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
        ts_codes: List of ts_codes (e.g., ["000001.SH", "399001.SZ"]).
            Only used with trade_date mode.
        source_ticker: Source code (e.g., "000001.SH").
        start_date: Start date (YYYY-MM-DD). Required with source_ticker.
        end_date: End date (YYYY-MM-DD). Required with source_ticker.

    Returns:
        DataFrame with columns (matching INDEX_DAILY_SCHEMA):
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
    return index.fetch_daily(
        trade_date=trade_date,
        ts_codes=ts_codes,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_sw_industry(
    industry: IndustryTushareAdapter,
    level: int = 1,
) -> pl.DataFrame:
    """
    获取申万行业分类.

    Args:
        industry: Industry 数据适配器.
        level: 行业级别 (1=一级行业, 2=二级行业).

    Returns:
        DataFrame with columns:
        - source_ticker: 行业代码 (e.g., "801010.SI")
        - industry_name: 行业名称
        - level: 行业级别 (1 or 2)

    Raises:
        SourceFetchError: If fetch fails.

    """
    return industry.fetch_sw_industry(level)
