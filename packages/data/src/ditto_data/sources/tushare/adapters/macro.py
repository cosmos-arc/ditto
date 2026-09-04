"""Macro domain Tushare adapter implementation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.sources.schemas.macro_schemas import empty_macro_dataframe
from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings.macro import (
    TushareMacroIndicator,
    get_tushare_macro_indicator,
)


def _parse_date_str(date_str: str, fmt: str) -> pl.Date | None:
    """Parse date string with given format."""
    result = pl.Series([date_str]).str.to_date(format=fmt, strict=False)
    return result[0] if len(result) > 0 else None


def _parse_date_by_frequency(date_str: str, frequency: str) -> pl.Date | None:
    """
    Parse date string based on frequency.

    Args:
        date_str: Date string from API response.
        frequency: Data frequency (daily, monthly, quarterly).

    Returns:
        Parsed date or None if parsing fails.

    """
    if not date_str:
        return None

    try:
        if frequency == "daily":
            # YYYYMMDD format
            return _parse_date_str(date_str, "%Y%m%d")
        elif frequency == "monthly":
            # YYYYMM format -> first day of month
            return _parse_date_str(date_str + "01", "%Y%m%d")
        elif frequency == "quarterly":
            # YYYYQq format (e.g., 2024Q1) -> first day of quarter
            year = int(date_str[:4])
            quarter = int(date_str[-1])
            month = (quarter - 1) * 3 + 1
            return _parse_date_str(f"{year}{month:02d}01", "%Y%m%d")
    except (ValueError, IndexError):
        return None

    return None


class MacroTushareAdapter(BaseTushareAdapter):
    """Tushare adapter for macro indicator datasets."""

    @traced("source.tushare.fetch_macro_indicators")
    def fetch_macro_indicators(
        self,
        trade_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        """
        Fetch macro indicators for a trade date.

        当前实现接入 `shibor` 接口并标准化为统一 macro_indicators SourceSchema。
        """
        return self.fetch_macro_indicators_range(
            trade_date,
            trade_date,
            observed_on=observed_on,
        )

    @traced("source.tushare.fetch_macro_indicators_range")
    def fetch_macro_indicators_range(
        self,
        start_date: str,
        end_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        """Fetch the normalized SHIBOR series with one bounded request."""
        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")
        logger.info(
            "Fetching Tushare macro indicators",
            event="tushare_macro_indicators_fetch_start",
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("macro_indicators", "shibor"):
            response = self._client.query(
                api_name="shibor",
                fields="date,on",
                start_date=compact_start,
                end_date=compact_end,
            )
            if response.is_empty():
                return empty_macro_dataframe()

            required_columns = {"date", "on"}
            missing = required_columns - set(response.columns)
            if missing:
                missing_text = sorted(missing)
                msg = f"Missing required columns from shibor response: {missing_text}"
                raise ValueError(msg)

            normalized = response.with_columns(
                pl.col("date")
                .cast(pl.String)
                .str.to_date(format="%Y%m%d", strict=False)
                .alias("date"),
                pl.col("on").cast(pl.Float64).alias("value"),
            )
            if normalized["date"].null_count() > 0:
                msg = "Failed to parse shibor date column into Date type"
                raise ValueError(msg)

            result = normalized.select(
                pl.lit("SHIBOR_ON").alias("indicator_code"),
                pl.lit("隔夜Shibor").alias("indicator_name"),
                pl.lit("interest_rate").alias("category"),
                pl.lit("daily").alias("frequency"),
                pl.lit(False).alias("need_pit"),
                pl.col("date"),
                pl.col("value"),
                pl.lit(observed_on or date.today()).alias("knowledge_date"),
                pl.lit("tushare").alias("source"),
                pl.lit("%").alias("unit"),
                pl.lit("Shanghai interbank offered rate overnight").alias(
                    "description"
                ),
            )

            logger.info(
                "Tushare macro indicators fetched",
                event="tushare_macro_indicators_fetch_complete",
                row_count=len(result),
            )
            return result

    @traced("source.tushare.fetch_indicators")
    def fetch_indicators(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        """
        Fetch multiple macro indicators from Tushare.

        Args:
            codes: List of unified indicator codes (e.g., ["CN_CPI_YOY", "CN_GDP_YOY"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            observed_on: Actual provider observation date; defaults to today.

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns.
            Unknown codes are skipped.

        """
        logger.info(
            "Fetching Tushare macro indicators by codes",
            event="tushare_macro_indicators_by_codes_start",
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

        api_to_indicators = self._resolve_indicators_by_api(codes)
        if not api_to_indicators:
            return empty_macro_dataframe()

        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")
        results = self._fetch_all_api_groups(
            api_to_indicators,
            compact_start,
            compact_end,
            observed_on or date.today(),
        )

        if not results:
            return empty_macro_dataframe()

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        result = pl.concat(results).filter(pl.col("date").is_between(start, end))
        logger.info(
            "Tushare macro indicators by codes fetched",
            event="tushare_macro_indicators_by_codes_complete",
            row_count=len(result),
        )
        return result

    @staticmethod
    def _resolve_indicators_by_api(
        codes: list[str],
    ) -> dict[str, list[TushareMacroIndicator]]:
        """
        Resolve indicator codes to valid indicators grouped by API name.

        Args:
            codes: List of unified indicator codes.

        Returns:
            Mapping from API name to list of indicators. Empty dict if no valid codes.

        """
        valid_indicators: list[TushareMacroIndicator] = []
        for code in codes:
            indicator = get_tushare_macro_indicator(code)
            if indicator is not None:
                valid_indicators.append(indicator)

        if not valid_indicators:
            return {}

        api_to_indicators: dict[str, list[TushareMacroIndicator]] = defaultdict(list)
        for indicator in valid_indicators:
            api_to_indicators[indicator.api_name].append(indicator)
        return dict(api_to_indicators)

    def _fetch_all_api_groups(
        self,
        api_to_indicators: dict[str, list[TushareMacroIndicator]],
        compact_start: str,
        compact_end: str,
        observed_on: date,
    ) -> list[pl.DataFrame]:
        """
        Fetch and transform indicators from each API group.

        Args:
            api_to_indicators: Mapping from API name to indicators.
            compact_start: Compact start date (YYYYMMDD).
            compact_end: Compact end date (YYYYMMDD).
            observed_on: Actual provider observation date.

        Returns:
            List of non-empty transformed DataFrames.

        """
        results: list[pl.DataFrame] = []

        for api_name, indicators in api_to_indicators.items():
            dfs = self._fetch_single_api(
                api_name,
                indicators,
                compact_start,
                compact_end,
                observed_on,
            )
            results.extend(dfs)

        return results

    def _fetch_single_api(
        self,
        api_name: str,
        indicators: list[TushareMacroIndicator],
        compact_start: str,
        compact_end: str,
        observed_on: date,
    ) -> list[pl.DataFrame]:
        """
        Fetch indicators from a single API and transform results.

        Args:
            api_name: Tushare API name.
            indicators: Indicators to fetch from this API.
            compact_start: Compact start date (YYYYMMDD).
            compact_end: Compact end date (YYYYMMDD).
            observed_on: Actual provider observation date.

        Returns:
            List of non-empty transformed DataFrames for this API.

        """
        fields = list({ind.field for ind in indicators})
        date_field = self._resolve_date_field(indicators[0])
        all_fields = [date_field, *fields]

        with tushare_fetch_error_handler("macro_indicators", api_name):
            response = self._client.query(
                api_name=api_name,
                fields=",".join(all_fields),
                start_date=compact_start,
                end_date=compact_end,
            )

            if response.is_empty():
                return []

            results: list[pl.DataFrame] = []
            for indicator in indicators:
                if indicator.field not in response.columns:
                    continue
                df = self._transform_to_schema(
                    response,
                    indicator,
                    date_field,
                    observed_on,
                )
                if df.height > 0:
                    results.append(df)
            return results

    @staticmethod
    def _resolve_date_field(indicator: TushareMacroIndicator) -> str:
        """
        Map indicator frequency to the Tushare date column name.

        Args:
            indicator: Metadata containing provider date-field and frequency rules.

        Returns:
            Column name used by Tushare for dates.

        """
        if indicator.date_field is not None:
            return indicator.date_field
        return {
            "daily": "date",
            "monthly": "month",
            "quarterly": "quarter",
        }.get(indicator.frequency, "date")

    def _transform_to_schema(
        self,
        response: pl.DataFrame,
        indicator: TushareMacroIndicator,
        date_field: str,
        observed_on: date,
    ) -> pl.DataFrame:
        """
        Transform API response to MACRO_INDICATOR_SOURCE_SCHEMA.

        Args:
            response: Raw API response DataFrame.
            indicator: Indicator metadata.
            date_field: Name of the date column in response.
            observed_on: Actual provider observation date used as knowledge date.

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns.

        """
        if response.height == 0:
            return empty_macro_dataframe()

        # Select and transform columns
        df = response.select(
            pl.col(date_field).alias("_date_str"),
            pl.col(indicator.field).cast(pl.Float64).alias("value"),
        ).filter(pl.col("value").is_not_null())

        if df.height == 0:
            return empty_macro_dataframe()

        # Parse date based on frequency
        df = df.with_columns(
            pl.col("_date_str")
            .map_elements(
                lambda x: _parse_date_by_frequency(x, indicator.frequency),
                return_dtype=pl.Date,
            )
            .alias("date"),
        ).drop("_date_str")

        # Filter out rows where date parsing failed
        df = df.filter(pl.col("date").is_not_null())

        if df.height == 0:
            return empty_macro_dataframe()

        # Tushare's China macro endpoints expose current values without a
        # historical publication/vintage timestamp. Historical bootstrap is
        # therefore visible only from the actual retrieval date. Fixed lag
        # estimates are metadata hints, never PIT evidence.
        result = df.with_columns(
            pl.lit(indicator.code).alias("indicator_code"),
            pl.lit(indicator.name).alias("indicator_name"),
            pl.lit(indicator.category).alias("category"),
            pl.lit(indicator.frequency).alias("frequency"),
            pl.lit(indicator.need_pit).alias("need_pit"),
            pl.lit(observed_on).alias("knowledge_date"),
            pl.lit("tushare").alias("source"),
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

        return result
