"""Tushare data source implementation."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare.calendar_source import CalendarTushareSource
from ditto_datahub.sources.tushare.etf_source import ETFTushareSource
from ditto_datahub.sources.tushare.stock_source import StockTushareSource


class TushareSource(DataSource):
    """
    Tushare Pro data source (组合模式入口).

    使用组合模式委托给专门的 Source 类：
    - CalendarTushareSource: Trading calendar
    - StockTushareSource: Stock-related data
    - ETFTushareSource: ETF-related data

    Attributes:
        _calendar: Calendar data source.
        _stock: Stock data source.
        _etf: ETF data source.

    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize Tushare source.

        Args:
            token: API token. Reads from keyring or ~/.ditto/secrets.toml if None.

        """
        self._calendar = CalendarTushareSource(token=token)
        self._stock = StockTushareSource(token=token)
        self._etf = ETFTushareSource(token=token)

    # Calendar 相关方法 - 委托给 CalendarTushareSource
    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """
        Fetch trading calendar.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - trade_date: Date
            - is_open: Boolean

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._calendar.fetch_calendar(start_date, end_date)

    # Stock 相关方法 - 委托给 StockTushareSource
    def fetch_stock_basic(self) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - symbol: Display symbol (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_stock_basic()

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        return self._stock.fetch_stock_daily(trade_date)

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_adj_factor(trade_date)

    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock limit up/down prices (B.3).

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - up_limit: Float64 (涨停价)
            - down_limit: Float64 (跌停价)

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_stock_limit(trade_date)

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock status information (B.3).

        Combines data from multiple Tushare APIs:
        - suspend_d: 停牌信息
        - stock_st: ST状态
        - stock_basic: list_status

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - is_suspended: Boolean
            - suspend_timing: Utf8 (e.g., "09:30-10:00" or null)
            - is_st: Boolean
            - st_type: Utf8 (e.g., "ST" or null)
            - list_status: Utf8 (L=正常, D=退市, P=暂停)

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_stock_status(trade_date)

    # ETF 相关方法 - 委托给 ETFTushareSource
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        Fetch ETF basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "510300.SH")
            - symbol: Display symbol (e.g., "510300")
            - name: ETF name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._etf.fetch_etf_basic()

    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        return self._etf.fetch_etf_daily(trade_date)

    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF/fund adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._etf.fetch_fund_adj(trade_date)
