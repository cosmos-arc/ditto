"""Tushare data source implementation."""

from __future__ import annotations

import polars as pl

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_datahub.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_datahub.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_datahub.sources.tushare.adapters.fx import FxTushareAdapter
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
        self._fx = FxTushareAdapter(_client=self._client)

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
    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Supports two modes:
        - Batch mode: No source_ticker, fetch all stocks
        - Single mode: With source_ticker, fetch specific stock

        Args:
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
        return self._stock.fetch_stock_basic(source_ticker)

    def fetch_stock_daily(
        self,
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
        return self._stock.fetch_stock_daily(
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

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

    def fetch_etf_daily(
        self,
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
        return self._etf.fetch_etf_daily(
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_fund_adj(
        self,
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
        return self._etf.fetch_fund_adj(
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

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
        return self._index.fetch_daily(
            trade_date=trade_date,
            ts_codes=ts_codes,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

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

    # Fundamental 相关方法 - 支持双模式查询
    def fetch_balance_sheet(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._fundamental.fetch_balance_sheet_vip(ann_date=compact_date)

        # 按标的查询
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
        compact_start = self._to_compact_date(start_date)
        compact_end = self._to_compact_date(end_date)
        return self._fundamental.fetch_balance_sheet(
            ts_code=source_ticker,
            start_date=compact_start,
            end_date=compact_end,
        )

    def fetch_income_statement(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._fundamental.fetch_income_statement_vip(ann_date=compact_date)

        # 按标的查询
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
        compact_start = self._to_compact_date(start_date)
        compact_end = self._to_compact_date(end_date)
        return self._fundamental.fetch_income_statement(
            ts_code=source_ticker,
            start_date=compact_start,
            end_date=compact_end,
        )

    def fetch_cash_flow(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._fundamental.fetch_cash_flow_vip(ann_date=compact_date)

        # 按标的查询
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
        compact_start = self._to_compact_date(start_date)
        compact_end = self._to_compact_date(end_date)
        return self._fundamental.fetch_cash_flow(
            ts_code=source_ticker,
            start_date=compact_start,
            end_date=compact_end,
        )

    def fetch_dividend(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._fundamental.fetch_dividend(ex_date=compact_date)

        # 按标的查询
        if not source_ticker:
            raise ValueError("按标的查询必须指定 source_ticker")
        compact_start = self._to_compact_date(start_date) if start_date else None
        compact_end = self._to_compact_date(end_date) if end_date else None
        return self._fundamental.fetch_dividend(
            ts_code=source_ticker,
            start_date=compact_start,
            end_date=compact_end,
        )

    # Capital 相关方法 - 支持双模式查询
    def fetch_valuation_metrics(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._capital.fetch_valuation_metrics(trade_date=compact_date)

        # 按标的查询
        if not source_ticker:
            raise ValueError("按标的查询必须指定 source_ticker")
        compact_start = self._to_compact_date(start_date) if start_date else None
        compact_end = self._to_compact_date(end_date) if end_date else None
        return self._capital.fetch_valuation_metrics(
            ts_code=source_ticker,
            start_date=compact_start,
            end_date=compact_end,
        )

    def fetch_margin_trading(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._capital.fetch_margin_trading(trade_date=compact_date)

        # 按标的查询
        if not source_ticker:
            raise ValueError("按标的查询必须指定 source_ticker")
        compact_start = self._to_compact_date(start_date) if start_date else None
        compact_end = self._to_compact_date(end_date) if end_date else None
        return self._capital.fetch_margin_trading(
            ts_code=source_ticker,
            start_date=compact_start,
            end_date=compact_end,
        )

    def fetch_pledge_ratio(
        self,
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
            compact_date = self._to_compact_date(trade_date)
            return self._capital.fetch_pledge_ratio(report_date=compact_date)

        # 按标的查询（pledge_ratio API 不支持日期范围）
        return self._capital.fetch_pledge_ratio(ts_code=source_ticker)

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """Fetch macro indicators data."""
        return self._macro.fetch_macro_indicators(trade_date)

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """Fetch corporate actions data."""
        compact_date = self._to_compact_date(trade_date)
        return self._fundamental.fetch_corporate_actions(
            ts_code=None,
            start_date=compact_date,
            end_date=compact_date,
        )

    # FX 相关方法 - 委托给 FxTushareAdapter
    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch FX daily data from Tushare.

        Args:
            ts_codes: FX ticker codes (e.g., ["USDCNH.FXCM"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with FX_SOURCE_SCHEMA columns.

        """
        return self._fx.fetch_fx_daily(
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Tushare 不支持商品数据。"""
        raise NotImplementedError("Tushare does not support commodity data")

    def close(self) -> None:
        """
        释放 HTTP 连接资源.

        调用内部 TushareClient 的 close 方法释放网络资源。
        """
        if hasattr(self, "_client") and self._client:
            self._client.close()
