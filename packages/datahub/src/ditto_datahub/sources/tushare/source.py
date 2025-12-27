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
        raise NotImplementedError("fetch_etf_basic not yet implemented")

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
        raise NotImplementedError("fetch_etf_daily not yet implemented")
