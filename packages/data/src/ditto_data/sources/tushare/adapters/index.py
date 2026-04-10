"""指数数据适配器."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import INDEX_BASIC_MAPPING
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


class IndexTushareAdapter(BaseTushareAdapter):
    """
    指数 Tushare 适配器.

    专门处理指数相关数据获取，包括：
    - 指数基本信息
    - 指数日线数据

    注意：
    - Tushare index_daily API 必须指定 ts_code 参数
    - 不支持仅用 trade_date 获取所有指数数据
    - 指数代码列表由编排层提供，不在 Adapter 层硬编码
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
    def fetch_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数日线 OHLCV 数据.

        支持两种查询模式：
        - 按日期批量：指定 trade_date + ts_codes（由编排层提供指数列表）
        - 按标的+时间段：指定 source_ticker + start_date + end_date

        注意：Tushare index_daily API 必须指定 ts_code 参数，不支持仅用 trade_date。

        Args:
            trade_date: Trade date (YYYY-MM-DD). 与 ts_codes 配合使用.
            ts_codes: List of ts_codes (e.g., ["000001.SH", "399001.SZ"]).
                由编排层提供，不在 Adapter 层硬编码.
            source_ticker: Source code (e.g., "000001.SH").
            start_date: Start date (YYYY-MM-DD). 与 source_ticker 配合使用.
            end_date: End date (YYYY-MM-DD). 与 source_ticker 配合使用.

        Returns:
            DataFrame with columns (matching INDEX_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: 参数组合无效.
            SourceFetchError: If all fetches fail.

        """
        # 参数校验
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")

        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")

        # 按日期批量查询
        if trade_date:
            if not ts_codes:
                raise ValueError("按日期查询必须指定 ts_codes")
            return self._fetch_daily_by_date(trade_date, ts_codes)

        # 按标的+时间段查询（此时 source_ticker 必定不为 None）
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")

        return self._fetch_daily_by_ticker(source_ticker, start_date, end_date)

    def _fetch_daily_by_date(
        self, trade_date: str, ts_codes: list[str]
    ) -> pl.DataFrame:
        """按日期获取指数日线数据."""
        logger.info(
            "Fetching Tushare index daily",
            event="tushare_index_daily_fetch_start",
            trade_date=trade_date,
            num_codes=len(ts_codes),
        )

        ts_date = trade_date.replace("-", "")
        dfs: list[pl.DataFrame] = []

        # 逐个查询每个指数
        for ts_code in ts_codes:
            try:
                api_name = f"index_daily:{ts_code}"
                with tushare_fetch_error_handler("index_daily", api_name):
                    response = self._client.query(
                        api_name="index_daily",
                        ts_code=ts_code,
                        start_date=ts_date,
                        end_date=ts_date,
                        fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
                    )
                    if response.height > 0:
                        dfs.append(response)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch index {ts_code}",
                    event="tushare_index_daily_fetch_failed",
                    ts_code=ts_code,
                    error=str(e),
                )
                continue

        if not dfs:
            logger.warning(
                "No index data fetched",
                event="tushare_index_daily_empty",
                trade_date=trade_date,
                ts_codes=ts_codes,
            )
            # 返回空 DataFrame 但保持正确的 schema
            return TushareDataTransformer.transform_daily_ohlcv(
                pl.DataFrame(),
                "index_daily",
            )

        # 合并所有结果
        combined = pl.concat(dfs)
        return TushareDataTransformer.transform_daily_ohlcv(
            combined,
            "index_daily",
        )

    def _fetch_daily_by_ticker(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按标的+时间段获取指数日线数据（内部方法）."""
        logger.info(
            "Fetching Tushare index daily by ticker",
            event="tushare_index_daily_ticker_fetch_start",
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("index_daily", f"index_daily:{source_ticker}"):
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            response = self._client.query(
                api_name="index_daily",
                ts_code=source_ticker,
                start_date=ts_start,
                end_date=ts_end,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "index_daily",
            )
