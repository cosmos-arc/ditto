"""FRED data source implementation."""

from __future__ import annotations

import polars as pl

from ditto_data.sources.base import DataSource
from ditto_data.sources.fred.adapters.commodity import CommodityFredAdapter
from ditto_data.sources.fred.adapters.macro import MacroFredAdapter
from ditto_data.sources.fred.indicators import FRED_INDICATORS, list_fred_indicators

# 预计算所有 FRED 指标代码
ALL_FRED_CODES: list[str] = list(FRED_INDICATORS.keys())

# 预计算 commodity/vix 代码
ALL_COMMODITY_CODES: list[str] = [
    ind.code for ind in list_fred_indicators(category="commodity")
]
ALL_VIX_CODES: list[str] = [ind.code for ind in list_fred_indicators(category="vix")]


class FredSource(DataSource):
    """
    FRED (Federal Reserve Economic Data) data source.

    FRED 提供宏观指标数据和商品/VIX 数据，其他方法抛出 NotImplementedError。

    Attributes:
        _macro: FRED 宏观数据 adapter。
        _commodity: FRED 商品数据 adapter。
        _api_key: FRED API key。

    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize FRED source.

        Args:
            api_key: FRED API key（可选，优先使用环境变量）。

        """
        self._api_key = api_key
        self._macro = MacroFredAdapter(api_key=api_key)
        self._commodity = CommodityFredAdapter(api_key=api_key)

    # Macro 相关方法 - 委托给 MacroFredAdapter
    def fetch_macro_indicators(
        self,
        trade_date: str,
        codes: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        Fetch macro indicators from FRED.

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)。
            codes: 指标代码列表 (如 ["US_CPI_YOY", "US_GDP_QOQ"])。
                如果为 None，获取所有可用指标。

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns。

        Raises:
            SourceFetchError: If fetch fails。

        """
        # 如果没有指定 codes，获取所有指标
        if codes is None:
            codes = ALL_FRED_CODES

        # FRED 的日期范围查询
        # 对于单一交易日，使用 start_date=end_date
        return self._macro.fetch_indicators(
            codes=codes,
            start_date=trade_date,
            end_date=trade_date,
        )

    def fetch_macro_indicators_range(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch macro indicators for a date range from FRED.

        Args:
            codes: 指标代码列表 (如 ["US_CPI_YOY", "US_GDP_QOY"])。
            start_date: 开始日期 (YYYY-MM-DD)。
            end_date: 结束日期 (YYYY-MM-DD)。

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns。

        Raises:
            SourceFetchError: If fetch fails。

        """
        return self._macro.fetch_indicators(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    # Commodity 相关方法 - 委托给 CommodityFredAdapter
    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch commodity daily prices from FRED.

        Args:
            codes: Commodity codes (e.g., ["COMMOD_WTI", "COMMOD_GOLD"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._commodity.fetch_commodities(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    # ========== DataSource 抽象方法实现 ==========
    # FRED 只支持宏观数据和商品数据，其他方法抛出 NotImplementedError

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """FRED 不支持交易日历。"""
        raise NotImplementedError("FRED does not support trading calendar")

    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """FRED 不支持股票数据。"""
        raise NotImplementedError("FRED does not support stock data")

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持股票数据。"""
        raise NotImplementedError("FRED does not support stock data")

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """FRED 不支持复权因子。"""
        raise NotImplementedError("FRED does not support adjustment factors")

    def fetch_adj_factor_by_ticker(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """FRED 不支持复权因子。"""
        raise NotImplementedError("FRED does not support adjustment factors")

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """FRED 不支持股票状态。"""
        raise NotImplementedError("FRED does not support stock status")

    def fetch_st_history(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持 ST 状态变更历史。"""
        raise NotImplementedError("FRED does not support ST status change history")

    def fetch_etf_basic(self) -> pl.DataFrame:
        """FRED 不支持 ETF 数据。"""
        raise NotImplementedError("FRED does not support ETF data")

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持 ETF 数据。"""
        raise NotImplementedError("FRED does not support ETF data")

    def fetch_fund_adj(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持基金复权因子。"""
        raise NotImplementedError("FRED does not support fund adjustment factors")

    def fetch_index_basic(self) -> pl.DataFrame:
        """FRED 不支持指数数据。"""
        raise NotImplementedError("FRED does not support index data")

    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持指数数据。"""
        raise NotImplementedError("FRED does not support index data")

    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持财务数据。"""
        raise NotImplementedError("FRED does not support financial data")

    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持财务数据。"""
        raise NotImplementedError("FRED does not support financial data")

    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持财务数据。"""
        raise NotImplementedError("FRED does not support financial data")

    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持股息数据。"""
        raise NotImplementedError("FRED does not support dividend data")

    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持估值数据。"""
        raise NotImplementedError("FRED does not support valuation metrics")

    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持融资融券数据。"""
        raise NotImplementedError("FRED does not support margin trading data")

    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """FRED 不支持质押数据。"""
        raise NotImplementedError("FRED does not support pledge ratio data")

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """FRED 不支持公司行为数据。"""
        raise NotImplementedError("FRED does not support corporate actions")

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """FRED 不支持行业分类数据。"""
        raise NotImplementedError("FRED does not support industry data")

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """FRED 不支持汇率数据。"""
        raise NotImplementedError("FRED does not support FX data")

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """FRED 不支持贵金属数据（请使用 Tushare 数据源）。"""
        raise NotImplementedError(
            "FRED precious metals data stopped updating in 2021. Use Tushare source."
        )
