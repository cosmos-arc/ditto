"""FRED commodity data adapter."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.fred.client import FredClient
from ditto_datahub.sources.fred.indicators import get_fred_indicator
from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA
from ditto_datahub.utils.timezone_utils import (
    get_fred_query_date,
)

# Commodity code to instrument_id mapping
# Using 5M range (5,000,000 - 5,999,999) for commodities
COMMODITY_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "COMMOD_WTI": 5_000_001,
    "COMMOD_BRENT": 5_000_002,
    "COMMOD_GOLD": 5_000_003,
    "COMMOD_SILVER": 5_000_004,
    "VIX_30D": 5_000_100,
    "VIX_9D": 5_000_101,
}


class CommodityFredAdapter:
    """
    Adapter for fetching commodity prices from FRED API.

    Normalizes FRED data to COMMODITY_SOURCE_SCHEMA format.
    FRED only provides a single value per observation, so OHLC
    are all set to the same value (the close price).

    Attributes:
        _client: FredClient instance for API calls.

    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize CommodityFredAdapter.

        Args:
            api_key: FRED API key. If None, reads from FRED_API_KEY env var.

        """
        self._client = FredClient(api_key=api_key)

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch commodity prices from FRED.

        Args:
            codes: Commodity codes (e.g., ["COMMOD_WTI", "COMMOD_GOLD"]).
            start_date: Start date in Beijing time (YYYY-MM-DD).
            end_date: End date in Beijing time (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.
            Unknown codes or non-commodity codes are skipped.

        """
        # Convert Beijing time dates to FRED query dates (US Eastern time)
        fred_start = get_fred_query_date(start_date)
        fred_end = get_fred_query_date(end_date)

        results: list[pl.DataFrame] = []

        for code in codes:
            indicator = get_fred_indicator(code)
            if indicator is None or indicator.category not in ("commodity", "vix"):
                # Skip unknown codes or non-commodity/vix indicators
                continue

            instrument_id = COMMODITY_CODE_TO_INSTRUMENT_ID.get(code)
            if instrument_id is None:
                continue

            # Fetch from FRED API using converted dates
            df = self._client.get_series_observations(
                series_id=indicator.series_id,
                observation_start=fred_start,
                observation_end=fred_end,
            )

            if df.height == 0:
                continue

            # Transform to COMMODITY_SOURCE_SCHEMA
            # FRED only provides a single value, so OHLC are all same
            # Use Polars native expressions for timezone-aware UTC conversion
            transformed = df.with_columns(
                pl.lit(instrument_id).alias("instrument_id"),
                pl.col("date").alias("trade_date"),
                # FRED dates are in US Eastern time, convert to UTC midnight
                # 1. Combine date with midnight time
                # 2. Set timezone to America/New_York (FRED timezone)
                # 3. Convert to UTC
                pl.col("date")
                .dt.combine(time=pl.time(0, 0, 0))
                .dt.replace_time_zone("America/New_York", ambiguous="earliest")
                .dt.convert_time_zone("UTC")
                .alias("trade_date_utc"),
                pl.col("value").alias("open"),
                pl.col("value").alias("high"),
                pl.col("value").alias("low"),
                pl.col("value").alias("close"),
            ).select(
                "instrument_id",
                "trade_date",
                "trade_date_utc",
                "open",
                "high",
                "low",
                "close",
            )

            results.append(transformed)

        if not results:
            # Return empty DataFrame with correct schema
            return pl.DataFrame(schema=COMMODITY_SOURCE_SCHEMA.schema)

        return pl.concat(results)

    def close(self) -> None:
        """Close underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> CommodityFredAdapter:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()


__all__ = ["COMMODITY_CODE_TO_INSTRUMENT_ID", "CommodityFredAdapter"]
