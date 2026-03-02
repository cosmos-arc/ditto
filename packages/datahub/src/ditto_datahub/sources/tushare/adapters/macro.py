"""Macro domain Tushare adapter implementation."""

from __future__ import annotations

from collections import defaultdict

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.sources.schemas.macro_schemas import empty_macro_dataframe
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.mappings.macro import (
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
    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch macro indicators for a trade date.

        当前实现接入 `shibor` 接口并标准化为统一 macro_indicators SourceSchema。
        """
        compact_date = trade_date.replace("-", "")
        logger.info(
            "Fetching Tushare macro indicators",
            event="tushare_macro_indicators_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("macro_indicators", "shibor"):
            response = self._client.query(
                api_name="shibor",
                fields="date,on",
                start_date=compact_date,
                end_date=compact_date,
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
                (pl.col("date") + pl.duration(days=1)).alias("knowledge_date"),
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
    def fetch_indicators(  # noqa: C901, PLR0912
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch multiple macro indicators from Tushare.

        Args:
            codes: List of unified indicator codes (e.g., ["CN_CPI_YOY", "CN_GDP_YOY"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

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

        # Filter valid indicators and group by API name for deduplication
        valid_indicators: list[TushareMacroIndicator] = []
        for code in codes:
            indicator = get_tushare_macro_indicator(code)
            if indicator is not None:
                valid_indicators.append(indicator)

        if not valid_indicators:
            return empty_macro_dataframe()

        # Group indicators by API name
        api_to_indicators: dict[str, list[TushareMacroIndicator]] = defaultdict(list)
        for indicator in valid_indicators:
            api_to_indicators[indicator.api_name].append(indicator)

        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")
        results: list[pl.DataFrame] = []

        # Fetch from each API
        for api_name, indicators in api_to_indicators.items():
            # Collect all fields needed for this API
            fields = list({ind.field for ind in indicators})
            # Determine date column based on frequency
            frequency = indicators[0].frequency
            if frequency == "daily":
                date_field = "date"
            elif frequency == "monthly":
                date_field = "month"
            elif frequency == "quarterly":
                date_field = "quarter"
            else:
                date_field = "date"

            all_fields = [date_field, *fields]

            with tushare_fetch_error_handler("macro_indicators", api_name):
                response = self._client.query(
                    api_name=api_name,
                    fields=",".join(all_fields),
                    start_date=compact_start,
                    end_date=compact_end,
                )

                if response.is_empty():
                    continue

                # Process each indicator
                for indicator in indicators:
                    if indicator.field not in response.columns:
                        continue

                    df = self._transform_to_schema(
                        response,
                        indicator,
                        date_field,
                    )
                    if df.height > 0:
                        results.append(df)

        if not results:
            return empty_macro_dataframe()

        result = pl.concat(results)
        logger.info(
            "Tushare macro indicators by codes fetched",
            event="tushare_macro_indicators_by_codes_complete",
            row_count=len(result),
        )
        return result

    def _transform_to_schema(
        self,
        response: pl.DataFrame,
        indicator: TushareMacroIndicator,
        date_field: str,
    ) -> pl.DataFrame:
        """
        Transform API response to MACRO_INDICATOR_SOURCE_SCHEMA.

        Args:
            response: Raw API response DataFrame.
            indicator: Indicator metadata.
            date_field: Name of the date column in response.

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

        # Add metadata columns and calculate knowledge_date
        result = df.with_columns(
            pl.lit(indicator.code).alias("indicator_code"),
            pl.lit(indicator.name).alias("indicator_name"),
            pl.lit(indicator.category).alias("category"),
            pl.lit(indicator.frequency).alias("frequency"),
            pl.lit(indicator.need_pit).alias("need_pit"),
            # knowledge_date = date + release_lag_days
            (pl.col("date") + pl.duration(days=indicator.release_lag_days)).alias(
                "knowledge_date"
            ),
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
