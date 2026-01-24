"""股票状态数据适配器."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger

from ditto_datahub.meta.schemas import (
    TUSHARE_LIST_STATUS_SCHEMA,
    TUSHARE_ST_SCHEMA,
    TUSHARE_SUSPEND_SCHEMA,
)
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.client import TushareClient


class StockStatusAdapter(BaseTushareAdapter):
    """
    股票状态数据适配器.

    负责从 Tushare API 获取股票的状态数据，包括：
    - 停牌数据 (suspend_d API)
    - ST 状态数据 (stock_st API)
    - 上市状态数据 (stock_basic API)

    Attributes:
        _client: Tushare API 客户端实例.

    """

    def __init__(self, *, client: TushareClient) -> None:
        """
        初始化 StockStatusAdapter.

        Args:
            client: Tushare API 客户端实例（必须传入）.

        """
        super().__init__(_client=client)

    def fetch_suspend_data(self, ts_date: str) -> pl.DataFrame:
        """
        获取停牌数据（从 suspend_d API）.

        Args:
            ts_date: 交易日期 (YYYYMMDD 格式)

        Returns:
            DataFrame with columns: ts_code, suspend_timing
            如果获取失败返回空 DataFrame

        """
        suspend_df = pl.DataFrame(schema=TUSHARE_SUSPEND_SCHEMA)
        try:
            suspend_response = self._client.query(
                api_name="suspend_d",
                suspend_date=ts_date,
                fields="ts_code,suspend_timing",
            )
            if len(suspend_response) > 0:
                suspend_df = suspend_response
        except (SourceFetchError, SourceAuthenticationError, SourceRateLimitError) as e:
            logger.warning(
                "Failed to fetch suspend_d data",
                event="tushare_suspend_d_fetch_error",
                error=str(e),
            )
        return suspend_df

    def fetch_st_data(self) -> pl.DataFrame:
        """
        获取 ST 状态数据（从 stock_st API）.

        Returns:
            DataFrame with columns: ts_code, name
            如果获取失败返回空 DataFrame

        Note:
            stock_st API 不需要日期参数，返回所有当前 ST 股票.

        """
        st_df = pl.DataFrame(schema=TUSHARE_ST_SCHEMA)
        try:
            st_response = self._client.query(
                api_name="stock_st",
                fields="ts_code,name",
            )
            if len(st_response) > 0:
                st_df = st_response
        except (SourceFetchError, SourceAuthenticationError, SourceRateLimitError) as e:
            logger.warning(
                "Failed to fetch stock_st data",
                event="tushare_stock_st_fetch_error",
                error=str(e),
            )
        return st_df

    def fetch_list_status_data(self) -> pl.DataFrame:
        """
        获取上市状态数据（从 stock_basic API）.

        Returns:
            DataFrame with columns: ts_code, list_status
            如果获取失败返回空 DataFrame

        Note:
            stock_basic API 不需要日期参数，返回所有股票的上市状态.
            list_status: L=正常, D=退市, P=暂停.

        """
        list_status_df = pl.DataFrame(schema=TUSHARE_LIST_STATUS_SCHEMA)
        try:
            basic_response = self._client.query(
                api_name="stock_basic",
                fields="ts_code,list_status",
            )
            if len(basic_response) > 0:
                list_status_df = basic_response
        except (SourceFetchError, SourceAuthenticationError, SourceRateLimitError) as e:
            logger.warning(
                "Failed to fetch stock_basic list_status",
                event="tushare_stock_basic_fetch_error",
                error=str(e),
            )
        return list_status_df
