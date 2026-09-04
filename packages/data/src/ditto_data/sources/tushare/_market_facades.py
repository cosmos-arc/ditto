"""Stock, ETF, index, and industry facade groups for TushareSource."""

from __future__ import annotations

from datetime import date, datetime

import polars as pl

from ditto_data.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter
from ditto_data.sources.tushare.adapters.industry import IndustryTushareAdapter
from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_data.sources.tushare.etf_index_source import (
    fetch_etf_basic,
    fetch_etf_daily,
    fetch_fund_adj,
    fetch_global_index_daily,
    fetch_index_basic,
    fetch_index_daily,
    fetch_sw_industry,
    fetch_sw_industry_concepts,
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

__all__ = ["EtfIndexFacade", "StockFacade"]


class StockFacade:
    """股票/日历数据域 facade."""

    def __init__(
        self,
        calendar: CalendarTushareAdapter,
        stock: StockTushareAdapter,
    ) -> None:
        self._calendar = calendar
        self._stock = stock

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """获取交易日历."""
        return fetch_calendar(self._calendar, start_date, end_date)

    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """获取股票基本信息."""
        return fetch_stock_basic(self._stock, source_ticker)

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股票日线 OHLCV."""
        return fetch_stock_daily(
            self._stock,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """获取股票复权因子."""
        return fetch_adj_factor(self._stock, trade_date)

    def fetch_adj_factor_by_ticker(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按标的获取复权因子."""
        return fetch_adj_factor_by_ticker(self._stock, ts_code, start_date, end_date)

    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """获取股票涨跌停价格."""
        return fetch_stock_limit(self._stock, trade_date)

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """获取股票状态信息."""
        return fetch_stock_status(self._stock, trade_date)

    def fetch_st_history(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取 ST 状态变更历史."""
        return fetch_st_history(
            self._stock,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )


class EtfIndexFacade:
    """ETF/指数/行业数据域 facade."""

    def __init__(
        self,
        etf: ETFTushareAdapter,
        index: IndexTushareAdapter,
        industry: IndustryTushareAdapter,
    ) -> None:
        self._etf = etf
        self._index = index
        self._industry = industry

    def fetch_etf_basic(self) -> pl.DataFrame:
        """获取 ETF 基本信息."""
        return fetch_etf_basic(self._etf)

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取 ETF 日线 OHLCV."""
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
        """获取 ETF/基金复权因子."""
        return fetch_fund_adj(
            self._etf,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_index_basic(self) -> pl.DataFrame:
        """获取指数基本信息."""
        return fetch_index_basic(self._index)

    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取指数日线 OHLCV."""
        return fetch_index_daily(
            self._index,
            trade_date=trade_date,
            ts_codes=ts_codes,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """获取申万行业分类."""
        return fetch_sw_industry(self._industry, level)

    def fetch_global_index_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_at: datetime | None = None,
    ) -> pl.DataFrame:
        """获取带显式市场时区和可见时间的全球指数日线."""
        return fetch_global_index_daily(
            self._index,
            codes,
            start_date,
            end_date,
            observed_at=observed_at,
        )

    def fetch_sw_industry_concepts(
        self,
        asof_date: str | None = None,
        level: int = 1,
        *,
        knowledge_date: date | None = None,
    ) -> pl.DataFrame:
        """获取 effective-dated 申万行业成分."""
        return fetch_sw_industry_concepts(
            self._industry,
            asof_date=asof_date,
            level=level,
            knowledge_date=knowledge_date,
        )
