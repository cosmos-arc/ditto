"""Tushare data source implementation."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.sources.base import DataSource, SourceFetchError
from ditto_datahub.sources.tushare.client import TushareClient


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
            token: API token (reads from TUSHARE_TOKEN env var if None).

        """
        self._client = TushareClient(token=token)
        logger.debug("TushareSource initialized", event="tushare_source_init")

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

        try:
            response = self._client.query(
                api_name="trade_cal",
                exchange="SSE",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                fields="cal_date,is_open",
            )

            # Tushare Pro API returns DataFrame directly
            if len(response) == 0:
                logger.info(
                    "Tushare calendar empty",
                    event="tushare_calendar_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={"trade_date": pl.Date, "is_open": pl.Boolean}
                )

            # Convert pandas DataFrame to polars and rename columns
            df = pl.from_pandas(response).rename({"cal_date": "trade_date"})

            # Transform types
            df = df.with_columns(
                pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
                pl.col("is_open").cast(pl.Int8) == 1,
            )

            row_count = len(df)
            logger.info(
                "Tushare calendar fetched",
                event="tushare_calendar_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "calendar", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare calendar fetch failed",
                event="tushare_calendar_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch calendar from Tushare",
                source="tushare",
                dataset="trade_cal",
                original_error=str(e),
            ) from e

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

        try:
            response = self._client.query(
                api_name="etf_basic",
                fields="ts_code,csname,exchange,list_date",
            )

            # Tushare Pro API returns DataFrame directly
            if len(response) == 0:
                logger.info(
                    "Tushare ETF basic empty",
                    event="tushare_etf_basic_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.String,
                        "symbol": pl.String,
                        "name": pl.String,
                        "exchange": pl.String,
                        "list_date": pl.Date,
                    }
                )

            # Convert pandas DataFrame to polars and rename columns
            df = pl.from_pandas(response).rename(
                {"ts_code": "src_code", "csname": "name"}
            )

            # Extract symbol (6-digit code from ts_code) and transform types
            df = df.with_columns(
                pl.col("src_code").str.replace(r"\.[A-Z]+$", "").alias("symbol"),
                pl.col("list_date").str.strptime(pl.Date, "%Y%m%d"),
            )

            # Select and reorder columns (exchange already in SSE/SZSE format)
            df = df.select("src_code", "symbol", "name", "exchange", "list_date")

            row_count = len(df)
            logger.info(
                "Tushare ETF basic fetched",
                event="tushare_etf_basic_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "etf_basic", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare ETF basic fetch failed",
                event="tushare_etf_basic_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch ETF basic from Tushare",
                source="tushare",
                dataset="etf_basic",
                original_error=str(e),
            ) from e

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

        try:
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_daily",
                ts_code="",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            # Tushare Pro API returns DataFrame directly
            if len(response) == 0:
                logger.info(
                    "Tushare ETF daily empty",
                    event="tushare_etf_daily_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.String,
                        "trade_date": pl.Date,
                        "open": pl.Float64,
                        "high": pl.Float64,
                        "low": pl.Float64,
                        "close": pl.Float64,
                        "pre_close": pl.Float64,
                        "volume": pl.Float64,
                        "amount": pl.Float64,
                        "pct_change": pl.Float64,
                    }
                )

            # Convert pandas DataFrame to polars and rename columns
            df = pl.from_pandas(response).rename(
                {
                    "ts_code": "src_code",
                    "vol": "volume",
                    "pct_chg": "pct_change",
                }
            )

            # Transform trade_date string to Date and ensure float types
            df = df.with_columns(
                pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("pre_close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
                pl.col("amount").cast(pl.Float64),
                pl.col("pct_change").cast(pl.Float64),
            )

            # Select required columns
            df = df.select(
                "src_code",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
                "amount",
                "pct_change",
            )

            row_count = len(df)
            logger.info(
                "Tushare ETF daily fetched",
                event="tushare_etf_daily_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "etf_daily", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare ETF daily fetch failed",
                event="tushare_etf_daily_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch ETF daily from Tushare",
                source="tushare",
                dataset="daily",
                original_error=str(e),
            ) from e

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

        try:
            response = self._client.query(
                api_name="stock_basic",
                list_status="L",
                fields="ts_code,symbol,name,exchange,list_date",
            )

            if len(response) == 0:
                logger.info(
                    "Tushare stock basic empty",
                    event="tushare_stock_basic_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.String,
                        "symbol": pl.String,
                        "name": pl.String,
                        "exchange": pl.String,
                        "list_date": pl.Date,
                    }
                )

            df = pl.from_pandas(response).rename({"ts_code": "src_code"})

            df = df.with_columns(
                pl.col("list_date").str.strptime(pl.Date, "%Y%m%d"),
            ).select("src_code", "symbol", "name", "exchange", "list_date")

            row_count = len(df)
            logger.info(
                "Tushare stock basic fetched",
                event="tushare_stock_basic_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "stock_basic", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare stock basic fetch failed",
                event="tushare_stock_basic_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch stock basic from Tushare",
                source="tushare",
                dataset="stock_basic",
                original_error=str(e),
            ) from e

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

        try:
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="daily",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            if len(response) == 0:
                logger.info(
                    "Tushare stock daily empty",
                    event="tushare_stock_daily_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.String,
                        "trade_date": pl.Date,
                        "open": pl.Float64,
                        "high": pl.Float64,
                        "low": pl.Float64,
                        "close": pl.Float64,
                        "pre_close": pl.Float64,
                        "volume": pl.Float64,
                        "amount": pl.Float64,
                        "pct_change": pl.Float64,
                    }
                )

            df = pl.from_pandas(response).rename(
                {
                    "ts_code": "src_code",
                    "vol": "volume",
                    "pct_chg": "pct_change",
                }
            )

            df = df.with_columns(
                pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("pre_close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
                pl.col("amount").cast(pl.Float64),
                pl.col("pct_change").cast(pl.Float64),
            )

            df = df.select(
                "src_code",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
                "amount",
                "pct_change",
            )

            row_count = len(df)
            logger.info(
                "Tushare stock daily fetched",
                event="tushare_stock_daily_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "stock_daily", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare stock daily fetch failed",
                event="tushare_stock_daily_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch stock daily from Tushare",
                source="tushare",
                dataset="daily",
                original_error=str(e),
            ) from e

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

        try:
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="adj_factor",
                trade_date=ts_date,
            )

            if len(response) == 0:
                logger.info(
                    "Tushare adj factor empty",
                    event="tushare_adj_factor_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.String,
                        "trade_date": pl.Date,
                        "knowledge_date": pl.Date,
                        "adj_factor": pl.Float64,
                    }
                )

            df = pl.from_pandas(response).rename({"ts_code": "src_code"})

            # 添加 knowledge_date 列（Tushare 当日数据，knowledge_date = trade_date）
            df = df.with_columns(
                pl.col("trade_date")
                .str.strptime(pl.Date, "%Y%m%d")
                .alias("trade_date"),
                pl.col("trade_date")
                .str.strptime(pl.Date, "%Y%m%d")
                .alias("knowledge_date"),
                pl.col("adj_factor").cast(pl.Float64),
            )

            df = df.select("src_code", "trade_date", "knowledge_date", "adj_factor")

            row_count = len(df)
            logger.info(
                "Tushare adj factor fetched",
                event="tushare_adj_factor_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "adj_factor", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare adj factor fetch failed",
                event="tushare_adj_factor_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch adj factor from Tushare",
                source="tushare",
                dataset="adj_factor",
                original_error=str(e),
            ) from e

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

        try:
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_adj",
                trade_date=ts_date,
            )

            if len(response) == 0:
                logger.info(
                    "Tushare fund adj empty",
                    event="tushare_fund_adj_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.String,
                        "trade_date": pl.Date,
                        "knowledge_date": pl.Date,
                        "adj_factor": pl.Float64,
                    }
                )

            df = pl.from_pandas(response).rename({"ts_code": "src_code"})

            # 添加 knowledge_date 列（Tushare 当日数据，knowledge_date = trade_date）
            df = df.with_columns(
                pl.col("trade_date")
                .str.strptime(pl.Date, "%Y%m%d")
                .alias("trade_date"),
                pl.col("trade_date")
                .str.strptime(pl.Date, "%Y%m%d")
                .alias("knowledge_date"),
                pl.col("adj_factor").cast(pl.Float64),
            )

            df = df.select("src_code", "trade_date", "knowledge_date", "adj_factor")

            row_count = len(df)
            logger.info(
                "Tushare fund adj fetched",
                event="tushare_fund_adj_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "fund_adj", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare fund adj fetch failed",
                event="tushare_fund_adj_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch fund adj from Tushare",
                source="tushare",
                dataset="fund_adj",
                original_error=str(e),
            ) from e

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

        try:
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="stk_limit",
                trade_date=ts_date,
                fields="ts_code,trade_date,up_limit,down_limit",
            )

            if len(response) == 0:
                logger.info(
                    "Tushare stock limit empty",
                    event="tushare_stock_limit_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={
                        "src_code": pl.Utf8,
                        "trade_date": pl.Date,
                        "up_limit": pl.Float64,
                        "down_limit": pl.Float64,
                    }
                )

            df = pl.from_pandas(response).rename({"ts_code": "src_code"})

            df = df.with_columns(
                pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
                pl.col("up_limit").cast(pl.Float64),
                pl.col("down_limit").cast(pl.Float64),
            )

            df = df.select("src_code", "trade_date", "up_limit", "down_limit")

            row_count = len(df)
            logger.info(
                "Tushare stock limit fetched",
                event="tushare_stock_limit_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "stock_limit", "status": "success"},
            )

            return df

        except Exception as e:
            logger.error(
                "Tushare stock limit fetch failed",
                event="tushare_stock_limit_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch stock limit from Tushare",
                source="tushare",
                dataset="stk_limit",
                original_error=str(e),
            ) from e

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

        try:
            ts_date = trade_date.replace("-", "")

            # 1. Fetch suspension data from suspend_d API
            suspend_df = pl.DataFrame(
                schema={
                    "ts_code": pl.Utf8,
                    "suspend_timing": pl.Utf8,
                }
            )
            try:
                suspend_response = self._client.query(
                    api_name="suspend_d",
                    suspend_date=ts_date,
                    fields="ts_code,suspend_timing",
                )
                if len(suspend_response) > 0:
                    suspend_df = pl.from_pandas(suspend_response)
            except Exception as e:
                logger.warning(
                    "Failed to fetch suspend_d data",
                    event="tushare_suspend_d_fetch_error",
                    error=str(e),
                )

            # 2. Fetch ST status from stock_st API
            st_df = pl.DataFrame(schema={"ts_code": pl.Utf8, "name": pl.Utf8})
            try:
                st_response = self._client.query(
                    api_name="stock_st",
                    fields="ts_code,name",
                )
                if len(st_response) > 0:
                    st_df = pl.from_pandas(st_response)
            except Exception as e:
                logger.warning(
                    "Failed to fetch stock_st data",
                    event="tushare_stock_st_fetch_error",
                    error=str(e),
                )

            # 3. Fetch list_status from stock_basic API
            list_status_df = pl.DataFrame(
                schema={"ts_code": pl.Utf8, "list_status": pl.Utf8}
            )
            try:
                basic_response = self._client.query(
                    api_name="stock_basic",
                    fields="ts_code,list_status",
                )
                if len(basic_response) > 0:
                    list_status_df = pl.from_pandas(basic_response)
            except Exception as e:
                logger.warning(
                    "Failed to fetch stock_basic list_status",
                    event="tushare_stock_basic_fetch_error",
                    error=str(e),
                )

            # 4. Merge all data sources
            # Start with all stock codes from stock_basic (as reference)
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
                pl.lit(trade_date).str.strptime(pl.Date, "%Y-%m-%d").alias("trade_date")
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

            row_count = len(result)
            logger.info(
                "Tushare stock status fetched",
                event="tushare_stock_status_fetch_complete",
                row_count=row_count,
            )
            M.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "stock_status", "status": "success"},
            )

            return result

        except Exception as e:
            logger.error(
                "Tushare stock status fetch failed",
                event="tushare_stock_status_fetch_error",
                error=str(e),
            )
            raise SourceFetchError(
                message="Failed to fetch stock status from Tushare",
                source="tushare",
                dataset="stock_status",
                original_error=str(e),
            ) from e
