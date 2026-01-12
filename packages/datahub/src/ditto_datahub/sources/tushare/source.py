"""Tushare data source implementation."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.meta.schemas import (
    TUSHARE_LIST_STATUS_SCHEMA,
    TUSHARE_ST_SCHEMA,
    TUSHARE_SUSPEND_SCHEMA,
)
from ditto_datahub.sources.base import (
    DataSource,
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.client import TushareClient
from ditto_datahub.sources.tushare.transformer import (
    ADJ_FACTOR_MAPPING,
    CALENDAR_MAPPING,
    ETF_BASIC_MAPPING,
    FUND_ADJ_MAPPING,
    STOCK_BASIC_MAPPING,
    STOCK_LIMIT_MAPPING,
    TushareDataTransformer,
)


def _record_metrics(row_count: int, dataset: str) -> None:
    """
    安全地记录数据指标。

    如果 observability 未初始化，静默跳过。

    Args:
        row_count: 数据行数
        dataset: 数据集名称

    """
    try:
        M.data_records.add(
            row_count,
            {"source": "tushare", "dataset": dataset, "status": "success"},
        )
    except (AttributeError, TypeError):
        # Observability 未初始化，静默跳过
        pass


class TushareSource(DataSource):
    """
    Tushare Pro data source.

    Fetches market data from Tushare API and transforms to Ditto schema.

    Attributes:
        _client: Tushare API client.

    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize Tushare source.

        Args:
            token: API token. Reads from keyring or ~/.ditto/secrets.toml if None.

        """
        self._client = TushareClient(token=token)
        logger.debug("TushareSource initialized", event="tushare_source_init")

    @contextmanager
    def _tushare_fetch_error_handler(
        self,
        dataset: str,
        api_name: str,
    ) -> Generator[None, None, None]:
        """
        统一的 Tushare fetch 错误处理上下文管理器。

        Args:
            dataset: 数据集名称（用于日志和错误消息）
            api_name: API 名称（用于错误消息）

        Yields:
            None

        Raises:
            SourceAuthenticationError: 认证错误直接抛出
            SourceRateLimitError: 限流错误直接抛出
            SourceFetchError: 其他异常包装为 SourceFetchError

        """
        try:
            yield
        except SourceAuthenticationError:
            raise
        except SourceRateLimitError:
            raise
        except Exception as e:
            logger.error(
                f"Tushare {dataset} fetch failed",
                event=f"tushare_{dataset}_fetch_error",
                error=str(e),
                api_name=api_name,
            )
            raise SourceFetchError(
                message=f"Failed to fetch {dataset} from Tushare",
                source="tushare",
                dataset=api_name,
                original_error=str(e),
            ) from e

    @traced("source.tushare.fetch_calendar")
    def fetch_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch trading calendar.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - trade_date: Date
            - is_open: Boolean

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare calendar",
            event="tushare_calendar_fetch_start",
            start_date=start_date,
            end_date=end_date,
        )

        with self._tushare_fetch_error_handler("calendar", "trade_cal"):
            response = self._client.query(
                api_name="trade_cal",
                exchange="SSE",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                fields="cal_date,is_open",
            )

            return TushareDataTransformer.transform(
                response, "calendar", CALENDAR_MAPPING
            )

    @traced("source.tushare.fetch_etf_basic")
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        Fetch ETF basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "510300.SH")
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

        with self._tushare_fetch_error_handler("etf_basic", "fund_basic"):
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
        Fetch ETF daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - src_code: Source code
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

        with self._tushare_fetch_error_handler("etf_daily", "fund_daily"):
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

    @traced("source.tushare.fetch_stock_basic")
    def fetch_stock_basic(self) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - symbol: Display symbol (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare stock basic info",
            event="tushare_stock_basic_fetch_start",
        )

        with self._tushare_fetch_error_handler("stock_basic", "stock_basic"):
            response = self._client.query(
                api_name="stock_basic",
                list_status="L",
                fields="ts_code,symbol,name,exchange,list_date",
            )

            return TushareDataTransformer.transform(
                response, "stock_basic", STOCK_BASIC_MAPPING
            )

    @traced("source.tushare.fetch_stock_daily")
    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        logger.info(
            "Fetching Tushare stock daily",
            event="tushare_stock_daily_fetch_start",
            trade_date=trade_date,
        )

        with self._tushare_fetch_error_handler("stock_daily", "daily"):
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

    @traced("source.tushare.fetch_adj_factor")
    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
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

        with self._tushare_fetch_error_handler("adj_factor", "adj_factor"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="adj_factor",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            return TushareDataTransformer.transform(
                response, "adj_factor", ADJ_FACTOR_MAPPING
            )

    @traced("source.tushare.fetch_fund_adj")
    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF/fund adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
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

        with self._tushare_fetch_error_handler("fund_adj", "fund_adj"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_adj",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            return TushareDataTransformer.transform(
                response, "fund_adj", FUND_ADJ_MAPPING
            )

    def _fetch_suspend_data(self, ts_date: str) -> pl.DataFrame:
        """
        获取停牌数据（从 suspend_d API）

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

    def _fetch_st_data(self) -> pl.DataFrame:
        """
        获取 ST 状态数据（从 stock_st API）

        Returns:
            DataFrame with columns: ts_code, name
            如果获取失败返回空 DataFrame

        Note:
            stock_st API 不需要日期参数，返回所有当前 ST 股票

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

    def _fetch_list_status_data(self) -> pl.DataFrame:
        """
        获取上市状态数据（从 stock_basic API）

        Returns:
            DataFrame with columns: ts_code, list_status
            如果获取失败返回空 DataFrame

        Note:
            stock_basic API 不需要日期参数，返回所有股票的上市状态
            list_status: L=正常, D=退市, P=暂停

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

    def _merge_status_data(
        self,
        list_status_df: pl.DataFrame,
        suspend_df: pl.DataFrame,
        st_df: pl.DataFrame,
        trade_date: str,
    ) -> pl.DataFrame:
        """
        合并状态数据（list_status + suspend + ST）

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

    @traced("source.tushare.fetch_stock_limit")
    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock limit up/down prices (B.3).

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
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

        with self._tushare_fetch_error_handler("stock_limit", "stk_limit"):
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
        Fetch stock status information (B.3).

        Combines data from multiple Tushare APIs:
        - suspend_d: 停牌信息
        - stock_st: ST状态
        - stock_basic: list_status

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
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

        with self._tushare_fetch_error_handler("stock_status", "stock_status"):
            ts_date = trade_date.replace("-", "")

            # 1. Fetch suspension data from suspend_d API
            suspend_df = self._fetch_suspend_data(ts_date)

            # 2. Fetch ST status from stock_st API
            st_df = self._fetch_st_data()

            # 3. Fetch list_status from stock_basic API
            list_status_df = self._fetch_list_status_data()

            # 4. Merge all data sources
            result = self._merge_status_data(
                list_status_df, suspend_df, st_df, trade_date
            )

            row_count = len(result)
            logger.info(
                "Tushare stock status fetched",
                event="tushare_stock_status_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "stock_status")

            return result
