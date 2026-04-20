"""
Domain-level Fetcher Protocols for external data sources.

Each Protocol represents a cohesive data domain, replacing the monolithic
DataSource ABC (25 abstract methods) with focused interfaces that satisfy
the Interface Segregation Principle.

Consumers depend only on the Protocols they need, not the full DataSource.
"""

from __future__ import annotations

from typing import Protocol

import polars as pl


class MetadataFetcher(Protocol):
    """Metadata and reference data source (T0, no trade_date needed)."""

    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """获取股票基础信息."""
        ...

    def fetch_etf_basic(self) -> pl.DataFrame:
        """获取 ETF 基础信息."""
        ...

    def fetch_index_basic(self) -> pl.DataFrame:
        """获取指数基础信息."""
        ...

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """获取交易日历."""
        ...

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """获取申万行业分类."""
        ...


class MarketFetcher(Protocol):
    """Market OHLCV bars, adjustment factors, and stock status."""

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股票日线行情."""
        ...

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取 ETF 日线行情."""
        ...

    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取指数日线行情."""
        ...

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """获取复权因子."""
        ...

    def fetch_adj_factor_by_ticker(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按代码获取复权因子."""
        ...

    def fetch_fund_adj(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取基金复权因子."""
        ...

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """获取股票交易状态."""
        ...


class FundamentalFetcher(Protocol):
    """Financial statements and corporate actions."""

    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取资产负债表."""
        ...

    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取利润表."""
        ...

    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取现金流量表."""
        ...

    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取分红数据."""
        ...

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """获取公司行动数据."""
        ...


class CapitalFetcher(Protocol):
    """Capital market data (valuation, margin trading, pledge ratio)."""

    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取估值指标."""
        ...

    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取融资融券数据."""
        ...

    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股权质押比例."""
        ...


class MacroFetcher(Protocol):
    """Macro indicators, FX, commodities, and metals."""

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """获取宏观指标."""
        ...

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取外汇日线数据."""
        ...

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取商品日线数据."""
        ...

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取金属日线数据."""
        ...


class CommodityFetcher(Protocol):
    """外部商品数据源（如 FRED），仅提供 fetch_commodities 能力."""

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取商品日线数据."""
        ...
