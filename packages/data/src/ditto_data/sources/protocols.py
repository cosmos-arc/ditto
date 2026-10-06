"""
Domain-level Fetcher Protocols for external data sources.

Each Protocol represents a cohesive data domain, replacing the monolithic
DataSource ABC (25 abstract methods) with focused interfaces that satisfy
the Interface Segregation Principle.

Consumers depend only on the Protocols they need, not the full DataSource.
"""

from __future__ import annotations

from datetime import date, datetime
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

    def fetch_csrc_industry(self) -> pl.DataFrame:
        """获取证监会行业分类（#517 industry_classification 第二来源）."""
        ...

    def fetch_sw_industry_concepts(
        self,
        asof_date: str | None = None,
        level: int = 1,
        *,
        knowledge_date: date | None = None,
    ) -> pl.DataFrame:
        """获取 effective-dated 申万行业成分."""
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

    def fetch_global_index_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_at: datetime | None = None,
    ) -> pl.DataFrame:
        """获取带显式可见时间的全球指数日线行情."""
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

    def fetch_fund_nav(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取 ETF/基金单位净值（#483）."""
        ...

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """获取股票交易状态."""
        ...

    def fetch_st_history(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取 ST 状态变更历史（事件流）."""
        ...

    def fetch_limit_list(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取涨跌停/炸板名单（#519 事件型，金额元）."""
        ...

    def fetch_fund_share(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取基金份额（#522 fd_share 万份）."""
        ...

    def fetch_name_history(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取证券名称变更历史（事件流）."""
        ...

    def fetch_futures_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取国内期货合约日线（amount 万元，原始口径）."""
        ...

    def fetch_futures_basic(self) -> pl.DataFrame:
        """获取期货合约信息快照（按交易所分片）."""
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

    def fetch_fina_indicator(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取官方口径财务指标（#521，118 列透传，kd=公告日）."""
        ...

    def fetch_fund_portfolio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取基金季度持仓（#522 公告日驱动，kd=公告日）."""
        ...

    def fetch_earnings_forecast(
        self,
        ann_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取业绩预告（净利润上下限万元，修订版本保留）."""
        ...

    def fetch_earnings_express(
        self,
        ann_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取业绩快报（金额元，含审计状态）."""
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

    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch monthly index weight observations (trade_date = observation day)."""
        ...

    def fetch_index_valuation(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取指数每日估值（市值元、股本股）."""
        ...

    def fetch_moneyflow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取个股资金流向（#518 金额万元/量手）."""
        ...

    def fetch_cyq_perf(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取每日筹码及胜率（#523）."""
        ...

    def fetch_hk_hold(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取沪深港通持股（#520 vol 股/ratio %）."""
        ...

    def fetch_hsgt_top10(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取沪深港通十大成交股（#520 金额元）."""
        ...

    def fetch_top_list(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取龙虎榜个股明细（#519 金额元，reason 进主键）."""
        ...

    def fetch_top_inst(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取龙虎榜席位明细（#519 金额元）."""
        ...


class MacroFetcher(Protocol):
    """Macro indicators, FX, commodities, and metals."""

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """获取宏观指标."""
        ...

    def fetch_macro_indicators_by_codes(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        """获取带实际抓取日的中国宏观快照."""
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
