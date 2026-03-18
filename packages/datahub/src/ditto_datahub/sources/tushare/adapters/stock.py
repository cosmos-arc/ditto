"""股票适配器实现."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors import StatusMerger
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.mappings import (
    ADJ_FACTOR_MAPPING,
    STOCK_BASIC_MAPPING,
    STOCK_LIMIT_MAPPING,
)
from ditto_datahub.sources.tushare.processors.transformer import TushareDataTransformer


class StockTushareAdapter(BaseTushareAdapter):
    """
    股票 Tushare 适配器.

    专门处理股票相关数据获取，包括：
    - 股票基本信息
    - 股票日线数据
    - 复权因子
    - 涨跌停价格
    - 股票状态

    """

    @traced("source.tushare.fetch_stock_basic")
    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """
        获取股票基本信息.

        支持两种模式：
        - 批量模式：不传 source_ticker，获取所有股票（包含正常上市/退市/暂停）
        - 单只模式：传入 source_ticker，获取指定股票

        Args:
            source_ticker: 股票代码 (e.g., "600519.SH")，可选。
                如果不传，则获取所有状态的股票。

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SZ")
            - ticker: Display ticker (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code
            - list_date: Listing date
            - list_status: Listing status (L=正常, D=退市, P=暂停)

        Raises:
            SourceFetchError: If fetch fails.

        """
        if source_ticker:
            # 单只股票模式
            logger.info(
                "Fetching single stock basic info",
                event="tushare_stock_basic_ticker_fetch_start",
                source_ticker=source_ticker,
            )
            with tushare_fetch_error_handler("stock_basic", "stock_basic_by_ticker"):
                response = self._client.query(
                    api_name="stock_basic",
                    ts_code=source_ticker,
                    fields="ts_code,symbol,name,exchange,list_date,delist_date,list_status",
                )

                if len(response) == 0:
                    logger.warning(
                        "Stock not found in Tushare",
                        event="tushare_stock_basic_not_found",
                        source_ticker=source_ticker,
                    )
                    return self._empty_stock_basic_schema()

                return TushareDataTransformer.transform(
                    response, "stock_basic", STOCK_BASIC_MAPPING
                )

        # 批量模式：获取所有状态的股票
        logger.info(
            "Fetching Tushare stock basic info (all statuses)",
            event="tushare_stock_basic_fetch_start",
        )

        all_dfs: list[pl.DataFrame] = []

        # 分别获取三种上市状态的股票，然后合并
        for status in ("L", "D", "P"):
            with tushare_fetch_error_handler("stock_basic", f"stock_basic_{status}"):
                response = self._client.query(
                    api_name="stock_basic",
                    list_status=status,
                    fields="ts_code,symbol,name,exchange,list_date,delist_date,list_status",
                )
                if len(response) > 0:
                    all_dfs.append(response)

        if not all_dfs:
            return self._empty_stock_basic_schema()

        # 合并所有状态的股票
        combined = pl.concat(all_dfs)
        return TushareDataTransformer.transform(
            combined, "stock_basic", STOCK_BASIC_MAPPING
        )

    @staticmethod
    def _empty_stock_basic_schema() -> pl.DataFrame:
        """返回空的 stock_basic schema."""
        return pl.DataFrame(
            schema={
                "source_ticker": pl.String,
                "ticker": pl.String,
                "name": pl.String,
                "exchange": pl.String,
                "list_date": pl.Date,
                "delist_date": pl.Date,
                "list_status": pl.String,
            }
        )

    @traced("source.tushare.fetch_stock_daily")
    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取股票日线 OHLCV 数据.

        支持两种查询模式：
        - 按日期批量：指定 trade_date
        - 按股票+时间段：指定 source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). 与 source_ticker 互斥.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). 与 source_ticker 配合使用.
            end_date: End date (YYYY-MM-DD). 与 source_ticker 配合使用.

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: 参数组合无效.
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        # 参数校验
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")

        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")

        # 按日期批量查询
        if trade_date:
            return self._fetch_stock_daily_by_date(trade_date)

        # 按股票+时间段查询（此时 source_ticker 必定不为 None）
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按股票查询必须指定 source_ticker、start_date 和 end_date")

        return self._fetch_stock_daily_by_ticker(source_ticker, start_date, end_date)

    def _fetch_stock_daily_by_date(self, trade_date: str) -> pl.DataFrame:
        """按日期获取股票日线数据."""
        logger.info(
            "Fetching Tushare stock daily",
            event="tushare_stock_daily_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("stock_daily", "daily"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="daily",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "stock_daily",
            )

    def _fetch_stock_daily_by_ticker(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按股票+时间段获取日线数据（内部方法）."""
        if not start_date or not end_date:
            raise ValueError("必须指定 start_date 和 end_date")

        logger.info(
            "Fetching Tushare stock daily by ticker",
            event="tushare_stock_daily_ticker_fetch_start",
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("stock_daily", "daily"):
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            response = self._client.query(
                api_name="daily",
                ts_code=source_ticker,
                start_date=ts_start,
                end_date=ts_end,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "stock_daily",
            )

    @traced("source.tushare.fetch_adj_factor")
    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """
        获取股票复权因子.

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
            "Fetching Tushare adj factors",
            event="tushare_adj_factor_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("adj_factor", "adj_factor"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="adj_factor",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            return TushareDataTransformer.transform(
                response, "adj_factor", ADJ_FACTOR_MAPPING
            )

    @traced("source.tushare.fetch_stock_limit")
    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """
        获取股票涨跌停价格 (B.3).

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - up_limit: Float64 (涨停价)
            - down_limit: Float64 (跌停价)

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare stock limit prices",
            event="tushare_stock_limit_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("stock_limit", "stk_limit"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="stk_limit",
                trade_date=ts_date,
                fields="ts_code,trade_date,up_limit,down_limit",
            )

            return TushareDataTransformer.transform(
                response, "stock_limit", STOCK_LIMIT_MAPPING
            )

    @traced("source.tushare.fetch_stock_status")
    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """
        获取股票状态信息 (B.3).

        Combines data from multiple Tushare APIs:
        - suspend_d: 停牌信息
        - stock_st: ST状态
        - stock_basic: list_status

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - is_suspended: Boolean
            - suspend_timing: Utf8 (e.g., "09:30-10:00" or null)
            - is_st: Boolean
            - st_type: Utf8 (e.g., "ST" or null)
            - list_status: Utf8 (L=正常, D=退市, P=暂停)

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare stock status",
            event="tushare_stock_status_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("stock_status", "stock_status"):
            ts_date = trade_date.replace("-", "")

            # 1. Fetch suspension data from suspend_d API
            suspend_df = self._fetch_suspend_data(ts_date)

            # 2. Fetch ST status from stock_st API
            st_df = self._fetch_st_data()

            # 3. Fetch list_status from stock_basic API
            list_status_df = self._fetch_list_status_data()

            # 4. 使用 Processor 合并数据
            merger = StatusMerger()
            result = merger.merge_status_data(
                list_status_df, suspend_df, st_df, trade_date
            )

            row_count = len(result)
            logger.info(
                "Tushare stock status fetched",
                event="tushare_stock_status_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "stock_status", "status": "success"},
            )

            return result

    # ==================== Private Methods for Stock Status ====================

    def _fetch_suspend_data(self, ts_date: str) -> pl.DataFrame:
        """
        获取停牌数据（从 suspend_d API）.

        Args:
            ts_date: 交易日期 (YYYYMMDD 格式)

        Returns:
            DataFrame with columns: ts_code, suspend_timing
            如果获取失败返回空 DataFrame

        """
        suspend_df = pl.DataFrame(
            schema={"ts_code": pl.String, "suspend_timing": pl.String}
        )
        try:
            suspend_response = self._client.query(
                api_name="suspend_d",
                suspend_date=ts_date,
                fields="ts_code,suspend_timing",
            )
            if len(suspend_response) > 0:
                suspend_df = suspend_response
        except (
            SourceFetchError,
            SourceAuthenticationError,
            SourceRateLimitError,
        ) as e:
            logger.warning(
                "Failed to fetch suspend_d data",
                event="tushare_suspend_d_fetch_error",
                error=str(e),
            )
        return suspend_df

    def _fetch_st_data(self) -> pl.DataFrame:
        """
        获取 ST 状态数据（从 stock_st API）.

        Returns:
            DataFrame with columns: ts_code, name
            如果获取失败返回空 DataFrame

        Note:
            stock_st API 不需要日期参数，返回所有当前 ST 股票.

        """
        st_df = pl.DataFrame(schema={"ts_code": pl.String, "name": pl.String})
        try:
            st_response = self._client.query(
                api_name="stock_st",
                fields="ts_code,name",
            )
            if len(st_response) > 0:
                st_df = st_response
        except (
            SourceFetchError,
            SourceAuthenticationError,
            SourceRateLimitError,
        ) as e:
            logger.warning(
                "Failed to fetch stock_st data",
                event="tushare_stock_st_fetch_error",
                error=str(e),
            )
        return st_df

    def _fetch_list_status_data(self) -> pl.DataFrame:
        """
        获取上市状态数据（从 stock_basic API）.

        Returns:
            DataFrame with columns: ts_code, list_status
            如果获取失败返回空 DataFrame

        Note:
            stock_basic API 不需要日期参数，返回所有股票的上市状态.
            list_status: L=正常, D=退市, P=暂停.

        """
        list_status_df = pl.DataFrame(
            schema={"ts_code": pl.String, "list_status": pl.String}
        )
        try:
            basic_response = self._client.query(
                api_name="stock_basic",
                fields="ts_code,list_status",
            )
            if len(basic_response) > 0:
                list_status_df = basic_response
        except (
            SourceFetchError,
            SourceAuthenticationError,
            SourceRateLimitError,
        ) as e:
            logger.warning(
                "Failed to fetch stock_basic list_status",
                event="tushare_stock_basic_fetch_error",
                error=str(e),
            )
        return list_status_df
