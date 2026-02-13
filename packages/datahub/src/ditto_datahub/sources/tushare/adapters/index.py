"""指数数据适配器."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.transformer import (
    INDEX_BASIC_MAPPING,
    TushareDataTransformer,
)


class IndexTushareAdapter(BaseTushareAdapter):
    """
    指数 Tushare 适配器.

    专门处理指数相关数据获取，包括：
    - 指数基本信息
    - 指数日线数据
    """

    @traced("source.tushare.fetch_index_basic")
    def fetch_basic(self) -> pl.DataFrame:
        """
        获取指数基本信息.

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
        logger.info(
            "Fetching Tushare index basic info",
            event="tushare_index_basic_fetch_start",
        )

        with tushare_fetch_error_handler("index_basic", "index_basic"):
            response = self._client.query(
                api_name="index_basic",
                fields="ts_code,name,market,list_date",
            )

            return TushareDataTransformer.transform(
                response, "index_basic", INDEX_BASIC_MAPPING
            )

    @traced("source.tushare.fetch_index_daily")
    def fetch_daily(self, trade_date: str) -> pl.DataFrame:
        """
        获取指数日线 OHLCV 数据.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (matching INDEX_DAILY_SCHEMA):
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
            "Fetching Tushare index daily",
            event="tushare_index_daily_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("index_daily", "index_daily"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="index_daily",
                ts_code="",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "index_daily",
            )
