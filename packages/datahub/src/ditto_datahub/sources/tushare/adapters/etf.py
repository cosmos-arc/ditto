"""ETF 适配器实现."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.transformer import (
    ETF_BASIC_MAPPING,
    FUND_ADJ_MAPPING,
    TushareDataTransformer,
)


class ETFTushareAdapter(BaseTushareAdapter):
    """
    ETF Tushare 适配器.

    专门处理 ETF 相关数据获取，包括：
    - ETF 基本信息
    - ETF 日线数据
    - 基金复权因子

    """

    @traced("source.tushare.fetch_etf_basic")
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        获取 ETF 基本信息.

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
        logger.info(
            "Fetching Tushare ETF basic info",
            event="tushare_etf_basic_fetch_start",
        )

        with tushare_fetch_error_handler("etf_basic", "fund_basic"):
            response = self._client.query(
                api_name="fund_basic",  # ETF basic 使用 fund_basic API
                fields="ts_code,name,list_date",  # fund_basic 可能没有 exchange 字段
            )

            return TushareDataTransformer.transform(
                response, "etf_basic", ETF_BASIC_MAPPING
            )

    @traced("source.tushare.fetch_etf_daily")
    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """
        获取 ETF 日线 OHLCV 数据.

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
        logger.info(
            "Fetching Tushare ETF daily",
            event="tushare_etf_daily_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("etf_daily", "fund_daily"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_daily",
                ts_code="",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "etf_daily",
            )

    @traced("source.tushare.fetch_fund_adj")
    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """
        获取 ETF/基金复权因子.

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
        logger.info(
            "Fetching Tushare fund adj factors",
            event="tushare_fund_adj_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("fund_adj", "fund_adj"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_adj",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            return TushareDataTransformer.transform(
                response, "fund_adj", FUND_ADJ_MAPPING
            )
