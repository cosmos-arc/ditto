"""股票状态数据获取与合并模块."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger

from ditto_datahub.meta.schemas import (
    TUSHARE_LIST_STATUS_SCHEMA,
    TUSHARE_ST_SCHEMA,
    TUSHARE_SUSPEND_SCHEMA,
)
from ditto_datahub.sources.tushare.client import TushareClient


class StockStatusMerger:
    """
    股票状态数据获取与合并器.

    负责从 Tushare API 获取并合并股票的状态数据，包括：
    - 停牌数据 (suspend_d API)
    - ST 状态数据 (stock_st API)
    - 上市状态数据 (stock_basic API)

    Attributes:
        _client: Tushare API 客户端实例.

    """

    def __init__(self, client: TushareClient) -> None:
        """
        初始化 StockStatusMerger.

        Args:
            client: Tushare API 客户端实例.

        """
        self._client = client

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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            logger.warning(
                "Failed to fetch stock_basic list_status",
                event="tushare_stock_basic_fetch_error",
                error=str(e),
            )
        return list_status_df

    def merge_status_data(
        self,
        list_status_df: pl.DataFrame,
        suspend_df: pl.DataFrame,
        st_df: pl.DataFrame,
        trade_date: str,
    ) -> pl.DataFrame:
        """
        合并状态数据（list_status + suspend + ST）.

        Args:
            list_status_df: 上市状态数据 (columns: ts_code, list_status)
            suspend_df: 停牌数据 (columns: ts_code, suspend_timing)
            st_df: ST状态数据 (columns: ts_code, name)
            trade_date: 交易日期 (YYYY-MM-DD 格式)

        Returns:
            DataFrame with columns:
            - src_code: 股票代码
            - trade_date: 交易日期
            - is_suspended: 是否停牌 (Boolean)
            - suspend_timing: 停牌时间段 (String, e.g. "09:30-10:00" or "")
            - is_st: 是否ST (Boolean)
            - st_type: ST类型 (String, e.g. "ST" or "")
            - list_status: 上市状态 (String: L=正常, D=退市, P=暂停)

        """
        # Start with all stock codes from list_status (as reference)
        result = list_status_df.rename({"ts_code": "src_code"})

        # Add suspension info
        if not suspend_df.is_empty():
            suspend_expanded = suspend_df.with_columns(
                pl.lit(True).alias("is_suspended")
            )
            result = result.join(
                suspend_expanded.rename({"ts_code": "src_code"}),
                on="src_code",
                how="left",
            )
        else:
            result = result.with_columns(pl.lit(None).alias("is_suspended"))
            result = result.with_columns(pl.lit(None).alias("suspend_timing"))

        # Add ST status
        if not st_df.is_empty():
            st_expanded = st_df.with_columns(
                pl.lit(True).alias("is_st"),
                pl.col("name").alias("st_type"),
            )
            result = result.join(
                st_expanded.rename({"ts_code": "src_code"}),
                on="src_code",
                how="left",
            )
        else:
            result = result.with_columns(pl.lit(None).alias("is_st"))
            result = result.with_columns(pl.lit(None).alias("st_type"))

        # Fill null values with defaults
        result = result.with_columns(
            pl.col("is_suspended").fill_null(False),
            pl.col("suspend_timing").fill_null(""),
            pl.col("is_st").fill_null(False),
            pl.col("st_type").fill_null(""),
            pl.col("list_status").fill_null("L"),  # Default to 正常
        )

        # Add trade_date column
        result = result.with_columns(
            pl.lit(trade_date).str.to_date("%Y-%m-%d").alias("trade_date")
        )

        # Select and reorder columns
        result = result.select(
            "src_code",
            "trade_date",
            "is_suspended",
            "suspend_timing",
            "is_st",
            "st_type",
            "list_status",
        )

        return result
