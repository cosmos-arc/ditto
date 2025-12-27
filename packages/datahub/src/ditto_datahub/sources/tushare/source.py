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

            # Transform response to DataFrame
            items = response.get("items", [])
            if not items:
                logger.info(
                    "Tushare calendar empty",
                    event="tushare_calendar_fetch_complete",
                    row_count=0,
                )
                return pl.DataFrame(
                    schema={"trade_date": pl.Date, "is_open": pl.Boolean}
                )

            df = pl.DataFrame(
                {
                    "trade_date": [item[0] for item in items],
                    "is_open": [item[1] for item in items],
                }
            )

            # Transform types
            df = df.with_columns(
                pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
                pl.col("is_open") == pl.lit("1"),
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
                fields="ts_code,etf_name,exchange,list_date",
            )

            items = response.get("items", [])
            if not items:
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

            df = pl.DataFrame(
                {
                    "src_code": [item[0] for item in items],
                    "name": [item[1] for item in items],
                    "exchange_raw": [item[2] for item in items],
                    "list_date": [item[3] for item in items],
                }
            )

            # Extract symbol (6-digit code from ts_code)
            df = df.with_columns(
                pl.col("src_code").str.replace(".[A-Z]+$", "").alias("symbol"),
                pl.col("list_date").str.strptime(pl.Date, "%Y%m%d"),
                pl.when(pl.col("exchange_raw") == "上交所")
                .then(pl.lit("SSE"))
                .when(pl.col("exchange_raw") == "深交所")
                .then(pl.lit("SZSE"))
                .otherwise(pl.col("exchange_raw"))
                .alias("exchange"),
            )

            # Select and reorder columns
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
                api_name="daily",
                ts_code="",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amt,pct_chg",
            )

            items = response.get("items", [])
            if not items:
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

            df = pl.DataFrame(
                {
                    "src_code": [item[0] for item in items],
                    "trade_date": [item[1] for item in items],
                    "open": [float(item[2]) for item in items],
                    "high": [float(item[3]) for item in items],
                    "low": [float(item[4]) for item in items],
                    "close": [float(item[5]) for item in items],
                    "pre_close": [float(item[6]) for item in items],
                    "volume": [float(item[7]) for item in items],
                    "amount": [float(item[8]) for item in items],
                    "pct_change": [float(item[9]) for item in items],
                }
            )

            # Transform trade_date string to Date
            df = df.with_columns(pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"))

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
