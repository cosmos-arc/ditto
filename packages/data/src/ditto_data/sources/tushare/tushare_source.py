"""Tushare data source — facade 委托入口."""

from __future__ import annotations

import polars as pl

from ditto_data.config import DataSourceSettings
from ditto_data.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_data.sources.tushare.adapters.fx import FxTushareAdapter
from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter
from ditto_data.sources.tushare.adapters.industry import IndustryTushareAdapter
from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_data.sources.tushare.adapters.metal import MetalTushareAdapter
from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.etf_index_source import (
    fetch_etf_basic,
    fetch_etf_daily,
    fetch_fund_adj,
    fetch_index_basic,
    fetch_index_daily,
    fetch_sw_industry,
)
from ditto_data.sources.tushare.fundamental_source import (
    fetch_balance_sheet,
    fetch_cash_flow,
    fetch_corporate_actions,
    fetch_dividend,
    fetch_income_statement,
    fetch_margin_trading,
    fetch_pledge_ratio,
    fetch_valuation_metrics,
)
from ditto_data.sources.tushare.macro_source import (
    fetch_commodities,
    fetch_fx_daily,
    fetch_macro_indicators,
    fetch_metal_daily,
)
from ditto_data.sources.tushare.stock_source import (
    fetch_adj_factor,
    fetch_adj_factor_by_ticker,
    fetch_calendar,
    fetch_st_history,
    fetch_stock_basic,
    fetch_stock_daily,
    fetch_stock_limit,
    fetch_stock_status,
)


class TushareSource:
    """Tushare Pro data source (组合模式入口)."""

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
        self._metal = MetalTushareAdapter(_client=self._client)

    # ── Calendar + Stock ─────────────────────────────────────────────

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch trading calendar. 委托给 stock_source.fetch_calendar."""
        return fetch_calendar(self._calendar, start_date, end_date)

    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """Fetch stock basic information. 委托给 stock_source.fetch_stock_basic."""
        return fetch_stock_basic(self._stock, source_ticker)

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch stock daily OHLCV bars. 委托给 stock_source.fetch_stock_daily."""
        return fetch_stock_daily(
            self._stock,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock adjustment factors. 委托给 stock_source.fetch_adj_factor."""
        return fetch_adj_factor(self._stock, trade_date)

    def fetch_adj_factor_by_ticker(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch stock adj factors by ticker. 委托给 stock_source."""
        return fetch_adj_factor_by_ticker(self._stock, ts_code, start_date, end_date)

    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock limit up/down prices. 委托给 stock_source.fetch_stock_limit."""
        return fetch_stock_limit(self._stock, trade_date)

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock status information. 委托给 stock_source.fetch_stock_status."""
        return fetch_stock_status(self._stock, trade_date)

    def fetch_st_history(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch ST status change history. 委托给 stock_source.fetch_st_history."""
        return fetch_st_history(
            self._stock,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    # ── ETF + Index + Industry ───────────────────────────────────────

    def fetch_etf_basic(self) -> pl.DataFrame:
        """Fetch ETF basic information. 委托给 etf_index_source.fetch_etf_basic."""
        return fetch_etf_basic(self._etf)

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch ETF daily OHLCV bars. 委托给 etf_index_source.fetch_etf_daily."""
        return fetch_etf_daily(
            self._etf,
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
        """Fetch ETF/fund adjustment factors. 委托给 etf_index_source.fetch_fund_adj."""
        return fetch_fund_adj(
            self._etf,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_index_basic(self) -> pl.DataFrame:
        """Fetch index basic information. 委托给 etf_index_source.fetch_index_basic."""
        return fetch_index_basic(self._index)

    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch index daily OHLCV bars. 委托给 etf_index_source.fetch_index_daily."""
        return fetch_index_daily(
            self._index,
            trade_date=trade_date,
            ts_codes=ts_codes,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """获取申万行业分类. 委托给 etf_index_source.fetch_sw_industry."""
        return fetch_sw_industry(self._industry, level)

    # ── Fundamental + Capital ────────────────────────────────────────

    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch balance sheet data. 委托给 fundamental_source.fetch_balance_sheet."""
        return fetch_balance_sheet(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch income statement data. 委托给 fundamental_source."""
        return fetch_income_statement(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch cash flow data. 委托给 fundamental_source.fetch_cash_flow."""
        return fetch_cash_flow(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch dividend data. 委托给 fundamental_source.fetch_dividend."""
        return fetch_dividend(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch valuation metrics data. 委托给 fundamental_source."""
        return fetch_valuation_metrics(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch margin trading data. 委托给 fundamental_source.fetch_margin_trading."""
        return fetch_margin_trading(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch pledge ratio data. 委托给 fundamental_source.fetch_pledge_ratio."""
        return fetch_pledge_ratio(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """Fetch corporate actions data. 委托给 fundamental_source."""
        return fetch_corporate_actions(self._fundamental, trade_date)

    # ── Macro + FX + Metal + Commodity ───────────────────────────────

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """Fetch macro indicators data. 委托给 macro_source.fetch_macro_indicators."""
        return fetch_macro_indicators(self._macro, trade_date)

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch FX daily data. 委托给 macro_source.fetch_fx_daily."""
        return fetch_fx_daily(
            self._fx,
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch precious metals daily data. 委托给 macro_source.fetch_metal_daily."""
        return fetch_metal_daily(
            self._metal,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Tushare 不支持商品数据."""
        return fetch_commodities(codes, start_date, end_date)

    def close(self) -> None:
        """
        释放 HTTP 连接资源.

        调用内部 TushareClient 的 close 方法释放网络资源。
        """
        if hasattr(self, "_client") and self._client:
            self._client.close()
