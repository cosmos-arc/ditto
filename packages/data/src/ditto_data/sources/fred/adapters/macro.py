"""FRED macro data adapter."""

from __future__ import annotations

import datetime

import polars as pl

from ditto_data.sources.fred.adapters.base import BaseFredAdapter
from ditto_data.sources.fred.indicators import get_fred_indicator
from ditto_data.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA

__all__ = ["MacroFredAdapter"]


def _take_latest_vintage_as_of(
    observations: pl.DataFrame,
    as_of: datetime.date,
) -> pl.DataFrame:
    """
    Collapse ALFRED revisions to the latest vintage known by ``as_of``.

    FRED ALFRED returns one row per published revision; each row's
    ``realtime_start`` is the date that vintage became public. For a
    point-in-time query anchored at ``as_of``, the value actually known is
    the vintage with the greatest ``realtime_start`` on or before ``as_of``.

    """
    if observations.height == 0 or "realtime_start" not in observations.columns:
        return observations
    return (
        observations.filter(pl.col("realtime_start") <= as_of)
        .sort("realtime_start")
        .unique(subset=["date"], keep="last")
    )


class MacroFredAdapter(BaseFredAdapter):
    """
    Adapter for fetching macro indicators from FRED API.

    Normalizes FRED data to MACRO_INDICATOR_SOURCE_SCHEMA format.

    PIT semantics:
        ``need_pit`` indicators (GDP/CPI/PCE, etc. — subject to revision)
        become true point-in-time when ``realtime_end`` is supplied: the FRED
        API receives the ALFRED realtime window, revisions are collapsed to
        the latest vintage known by ``realtime_end``, and ``knowledge_date``
        is set to ``realtime_end``. Indicators with ``need_pit=False``
        (rarely restated, e.g. UNRATE) keep ``knowledge_date`` equal to the
        observation date regardless of the realtime anchor.

    """

    def fetch_indicators(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch multiple macro indicators from FRED.

        Args:
            codes: List of unified indicator codes (e.g., ["US_UNRATE", "US_GDP_QOQ"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            realtime_start: Optional ALFRED realtime window start (YYYY-MM-DD).
                Applied only to ``need_pit`` indicators together with
                ``realtime_end``; defaults to ``start_date`` when omitted.
            realtime_end: Optional ALFRED realtime PIT anchor (YYYY-MM-DD).
                When set on a ``need_pit`` indicator, the FRED API receives
                the realtime window, revisions collapse to the latest vintage
                known by this date, and ``knowledge_date`` is set to it. Non-PIT
                indicators ignore both parameters.

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

            # Bind to a local so the None-check narrows ``realtime_end`` to
            # ``str`` within the branch (a captured bool would not propagate).
            realtime_end_str = realtime_end
            if realtime_end_str is not None and indicator.need_pit:
                as_of = datetime.date.fromisoformat(realtime_end_str)
                # Fetch ALFRED vintage observations known by realtime_end
                df = self._client.get_series_observations(
                    series_id=indicator.series_id,
                    observation_start=start_date,
                    observation_end=end_date,
                    realtime_start=realtime_start or start_date,
                    realtime_end=realtime_end_str,
                )
                # Collapse revisions to the latest vintage known at as_of
                df = _take_latest_vintage_as_of(df, as_of)
                knowledge_date_expr = pl.lit(as_of)
            else:
                # Current-vintage observations; non-PIT data is known on the
                # observation date itself
                df = self._client.get_series_observations(
                    series_id=indicator.series_id,
                    observation_start=start_date,
                    observation_end=end_date,
                )
                knowledge_date_expr = pl.col("date")

            if df.height == 0:
                continue

            # Transform to MACRO_INDICATOR_SOURCE_SCHEMA
            transformed = df.with_columns(
                pl.lit(code).alias("indicator_code"),
                pl.lit(indicator.name).alias("indicator_name"),
                pl.lit(indicator.category).alias("category"),
                pl.lit(indicator.frequency).alias("frequency"),
                pl.lit(indicator.need_pit).alias("need_pit"),
                knowledge_date_expr.alias("knowledge_date"),
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
