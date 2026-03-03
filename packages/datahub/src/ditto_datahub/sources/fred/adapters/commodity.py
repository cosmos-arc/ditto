"""FRED commodity data adapter."""

from __future__ import annotations

import polars as pl

from ditto_datahub.models.source_codes import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from ditto_datahub.sources.fred.adapters.base import BaseFredAdapter
from ditto_datahub.sources.fred.indicators import get_fred_indicator
from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA
from ditto_datahub.utils.timezone_utils import (
    get_fred_query_date,
)


class CommodityFredAdapter(BaseFredAdapter):
    """
    Adapter for fetching commodity prices and VIX from FRED API.

    Normalizes FRED data to COMMODITY_SOURCE_SCHEMA format.
    FRED only provides a single value per observation, so OHLC
    are all set to the same value (the close price).

    Note:
        此适配器同时处理商品数据（WTI、Brent、Gold、Silver）和 VIX 波动率指数。
        VIX 虽然属于"另类数据"类别，但与商品数据共享相同的数据结构和处理流程，
        因此统一在此适配器中处理。两者都使用 COMMODITY_SOURCE_SCHEMA。

    """

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch commodity prices and VIX from FRED.

        Args:
            codes: Codes to fetch (e.g., ["COMMOD_WTI", "VIX_30D"]).
                   Supports both commodity codes and VIX codes.
            start_date: Start date in Beijing time (YYYY-MM-DD).
            end_date: End date in Beijing time (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.
            Unknown codes or non-commodity/vix codes are skipped.

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

            # Look up instrument_id from either commodity or VIX mapping
            instrument_id = COMMODITY_CODE_TO_INSTRUMENT_ID.get(
                code
            ) or VIX_CODE_TO_INSTRUMENT_ID.get(code)
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


__all__ = [
    "COMMODITY_CODE_TO_INSTRUMENT_ID",
    "VIX_CODE_TO_INSTRUMENT_ID",
    "CommodityFredAdapter",
]
