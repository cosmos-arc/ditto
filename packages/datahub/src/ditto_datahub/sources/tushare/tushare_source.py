"""Tushare data source implementation."""

from __future__ import annotations

import polars as pl

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_datahub.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter


class TushareSource(DataSource):
    """
    Tushare Pro data source (组合模式入口).

    使用组合模式委托给专门的 Adapter 类：
    - CalendarTushareAdapter: Trading calendar
    - StockTushareAdapter: Stock-related data
    - ETFTushareAdapter: ETF-related data

    Attributes:
        _calendar: Calendar data adapter.
        _stock: Stock data adapter.
        _etf: ETF data adapter.

    """

    def __init__(
        self,
        settings: DataSourceSettings,
        token: str | None = None,
    ) -> None:
        """
        Initialize Tushare source.

        Args:
            settings: 数据源配置（包含 URL/timeout 等参数）.
            token: API token（可选，优先于 settings 中的 token）。

        """
        self._calendar = CalendarTushareAdapter(token=token, settings=settings)
        self._stock = StockTushareAdapter(token=token, settings=settings)
        self._etf = ETFTushareAdapter(token=token, settings=settings)
        self._capital = CapitalTushareAdapter(token=token, settings=settings)
        self._fundamental = FundamentalTushareAdapter(token=token, settings=settings)
        self._macro = MacroTushareAdapter(token=token, settings=settings)

    @staticmethod
    def _to_compact_date(trade_date: str) -> str:
        """Convert YYYY-MM-DD to YYYYMMDD for Tushare APIs."""
        return trade_date.replace("-", "")

    # Calendar 相关方法 - 委托给 CalendarTushareAdapter
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

    # Stock 相关方法 - 委托给 StockTushareAdapter
    def fetch_stock_basic(self) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SZ")
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
            - source_ticker: Source code
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
            - source_ticker: Source code
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
            - source_ticker: Source code (e.g., "000001.SZ")
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
        return self._stock.fetch_stock_status(trade_date)

    # ETF 相关方法 - 委托给 ETFTushareAdapter
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        Fetch ETF basic information.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "510300.SH")
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
            - source_ticker: Source code
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
            - source_ticker: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._etf.fetch_fund_adj(trade_date)

    # Capital/Fundamental 相关方法 - 委托给 CapitalTushareAdapter
    def fetch_balance_sheet(self, trade_date: str) -> pl.DataFrame:
        """Fetch balance sheet data for a trade date window."""
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_balance_sheet(
            ts_code=None,
            start_date=compact_date,
            end_date=compact_date,
        )

    def fetch_income_statement(self, trade_date: str) -> pl.DataFrame:
        """Fetch income statement data for a trade date window."""
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_income_statement(
            ts_code=None,
            start_date=compact_date,
            end_date=compact_date,
        )

    def fetch_cash_flow(self, trade_date: str) -> pl.DataFrame:
        """Fetch cash flow data for a trade date window."""
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_cash_flow(
            ts_code=None,
            start_date=compact_date,
            end_date=compact_date,
        )

    def fetch_dividend(self, trade_date: str) -> pl.DataFrame:
        """Fetch dividend data."""
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_dividend(ex_date=compact_date)

    def fetch_valuation_metrics(self, trade_date: str) -> pl.DataFrame:
        """Fetch valuation metrics data."""
        compact_date = self._to_compact_date(trade_date)
        return self._capital.fetch_valuation_metrics(trade_date=compact_date)

    def fetch_margin_trading(self, trade_date: str) -> pl.DataFrame:
        """Fetch margin trading data."""
        compact_date = self._to_compact_date(trade_date)
        return self._capital.fetch_margin_trading(trade_date=compact_date)

    def fetch_pledge_ratio(self, trade_date: str) -> pl.DataFrame:
        """Fetch pledge ratio data."""
        compact_date = self._to_compact_date(trade_date)
        return self._capital.fetch_pledge_ratio(report_date=compact_date)

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """Fetch macro indicators data."""
        return self._macro.fetch_macro_indicators(trade_date)

    def fetch_futures(self, trade_date: str) -> pl.DataFrame:
        """Fetch futures data."""
        compact_date = self._to_compact_date(trade_date)
        return self._capital.fetch_futures(
            ts_code=None,
            start_date=compact_date,
            end_date=compact_date,
        )

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """Fetch corporate actions data."""
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_corporate_actions(
            ts_code=None,
            start_date=compact_date,
            end_date=compact_date,
        )
