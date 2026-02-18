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
        trade_date: str,
        ts_codes: list[str],
    ) -> pl.DataFrame:
        """
        获取指数日线 OHLCV 数据.

        注意：Tushare index_daily API 要求 ts_code 参数，
        此方法逐个查询指定指数列表并合并结果。

        Args:
            trade_date: Trade date (YYYY-MM-DD).
            ts_codes: List of ts_codes (e.g., ["000001.SH", "399001.SZ"]).
                由编排层提供，不在 Adapter 层硬编码。

        Returns:
            DataFrame with columns (matching INDEX_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If all fetches fail.
            ValueError: If ts_codes is empty.

        """
        if not ts_codes:
            raise ValueError("ts_codes is required - provided by orchestration layer")

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
