"""Tushare data source implementation."""

from __future__ import annotations

import polars as pl

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_datahub.sources.tushare.adapters.index import IndexTushareAdapter
from ditto_datahub.sources.tushare.adapters.industry import IndustryTushareAdapter
from ditto_datahub.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_datahub.sources.tushare.client import TushareClient


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
        _client: 共享的 TushareClient 实例。

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
        # 创建单例 client，所有 adapter 共享
        self._client = TushareClient(token=token, settings=settings)

        # 注入共享 client 到所有 adapter
        self._calendar = CalendarTushareAdapter(_client=self._client)
        self._stock = StockTushareAdapter(_client=self._client)
        self._etf = ETFTushareAdapter(_client=self._client)
        self._index = IndexTushareAdapter(_client=self._client)
        self._industry = IndustryTushareAdapter(_client=self._client)
        self._capital = CapitalTushareAdapter(_client=self._client)
        self._fundamental = FundamentalTushareAdapter(_client=self._client)
        self._macro = MacroTushareAdapter(_client=self._client)

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
            - ticker: Display ticker (e.g., "000001")
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
            - ticker: Display ticker (e.g., "510300")
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

    # Index 相关方法 - 委托给 IndexTushareAdapter
    def fetch_index_basic(self) -> pl.DataFrame:
        """
        Fetch index basic information.

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
        return self._index.fetch_basic()

    def fetch_index_daily(
        self,
        trade_date: str,
        ts_codes: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Fetch index daily OHLCV bars.

        注意：Tushare index_daily API 要求 ts_code 参数，
        此方法逐个查询指定指数列表并合并结果。

        Args:
            trade_date: Trade date (YYYY-MM-DD).
            ts_codes: List of ts_codes (e.g., ["000001.SH", "399001.SZ"]).
                由编排层提供，不在 Source 层硬编码。
                如果为 None，将抛出 ValueError。

        Returns:
            DataFrame with columns (matching INDEX_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: If ts_codes is None or empty.
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        if not ts_codes:
            raise ValueError(
                "ts_codes is required - index codes should be provided by orchestration"
            )
        return self._index.fetch_daily(trade_date, ts_codes)

    # Industry 相关方法 - 委托给 IndustryTushareAdapter
    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """
        获取申万行业分类.

        Args:
            level: 行业级别 (1=一级行业, 2=二级行业).

        Returns:
            DataFrame with columns:
            - source_ticker: 行业代码 (e.g., "801010.SI")
            - industry_name: 行业名称
            - level: 行业级别 (1 or 2)

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._industry.fetch_sw_industry(level)

    # Financial 相关方法 - 使用 VIP API 批量获取（需要 5000+ 积分）
    def fetch_balance_sheet(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch balance sheet data for a trade date.

        使用 VIP API (balancesheet_vip) 按 ann_date 获取全部股票数据。
        无需指定 ts_code，可批量获取当日公告的所有资产负债表。

        Args:
            trade_date: 公告日期 (YYYY-MM-DD)

        Returns:
            当日公告的全部股票资产负债表数据

        """
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_balance_sheet_vip(ann_date=compact_date)

    def fetch_income_statement(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch income statement data for a trade date.

        使用 VIP API (income_vip) 按 ann_date 获取全部股票数据。
        无需指定 ts_code，可批量获取当日公告的所有利润表。

        Args:
            trade_date: 公告日期 (YYYY-MM-DD)

        Returns:
            当日公告的全部股票利润表数据

        """
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_income_statement_vip(ann_date=compact_date)

    def fetch_cash_flow(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch cash flow data for a trade date.

        使用 VIP API (cashflow_vip) 按 ann_date 获取全部股票数据。
        无需指定 ts_code，可批量获取当日公告的所有现金流量表。

        Args:
            trade_date: 公告日期 (YYYY-MM-DD)

        Returns:
            当日公告的全部股票现金流量表数据

        """
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_cash_flow_vip(ann_date=compact_date)

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

    def close(self) -> None:
        """
        释放 HTTP 连接资源.

        调用内部 TushareClient 的 close 方法释放网络资源。
        """
        if hasattr(self, "_client") and self._client:
            self._client.close()
