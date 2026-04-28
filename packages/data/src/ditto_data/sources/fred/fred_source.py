"""FRED data source implementation."""

from __future__ import annotations

import polars as pl

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


class FredSource:
    """
    FRED (Federal Reserve Economic Data) data source.

    仅提供宏观指标和商品/VIX 数据，不继承 DataSource ABC。
    消费者按需依赖 MacroFetcher Protocol 即可。

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
        if codes is None:
            codes = ALL_FRED_CODES

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
