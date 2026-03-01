"""FRED macro data adapter."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.fred.adapters.base import BaseFredAdapter
from ditto_datahub.sources.fred.indicators import get_fred_indicator
from ditto_datahub.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA


class MacroFredAdapter(BaseFredAdapter):
    """
    Adapter for fetching macro indicators from FRED API.

    Normalizes FRED data to MACRO_INDICATOR_SOURCE_SCHEMA format.

    Note:
        FRED macro indicators typically have need_pit=False because:
        1. Historical macro data is rarely restated
        2. PIT semantics require passing realtime_start/realtime_end
           parameters to FRED API, which is not currently implemented

    """

    def fetch_indicators(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch multiple macro indicators from FRED.

        Args:
            codes: List of unified indicator codes (e.g., ["US_UNRATE", "US_GDP_QOQ"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns.
            Unknown codes are skipped.

        """
        results: list[pl.DataFrame] = []

        for code in codes:
            indicator = get_fred_indicator(code)
            if indicator is None:
                # Skip unknown codes
                continue

            # Fetch from FRED API
            df = self._client.get_series_observations(
                series_id=indicator.series_id,
                observation_start=start_date,
                observation_end=end_date,
            )

            if df.height == 0:
                continue

            # Transform to MACRO_INDICATOR_SOURCE_SCHEMA
            transformed = df.with_columns(
                pl.lit(code).alias("indicator_code"),
                pl.lit(indicator.name).alias("indicator_name"),
                pl.lit(indicator.category).alias("category"),
                pl.lit(indicator.frequency).alias("frequency"),
                pl.lit(indicator.need_pit).alias("need_pit"),
                # knowledge_date: use observation date as knowledge date
                # Note: For true PIT semantics, realtime_start/realtime_end
                # parameters need to be passed to FRED API, which is not
                # currently implemented. This assumes data is known on the
                # observation date itself.
                pl.col("date").alias("knowledge_date"),
                pl.lit("fred").alias("source"),
                pl.lit(indicator.unit).alias("unit"),
                pl.lit(indicator.description).alias("description"),
            ).select(
                "indicator_code",
                "indicator_name",
                "category",
                "frequency",
                "need_pit",
                "date",
                "value",
                "knowledge_date",
                "source",
                "unit",
                "description",
            )

            results.append(transformed)

        if not results:
            # Return empty DataFrame with correct schema
            return pl.DataFrame(schema=MACRO_INDICATOR_SOURCE_SCHEMA.schema)

        return pl.concat(results)


__all__ = ["MacroFredAdapter"]
