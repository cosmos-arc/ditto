"""Macro domain Tushare adapter implementation."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.sources.schemas.macro_schemas import (
    MACRO_INDICATOR_SOURCE_SCHEMA,
)
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)


def _empty_macro_dataframe() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "indicator_code": pl.String,
            "indicator_name": pl.String,
            "category": pl.String,
            "frequency": pl.String,
            "need_pit": pl.Boolean,
            "date": pl.Date,
            "value": pl.Float64,
            "knowledge_date": pl.Date,
            "source": pl.String,
            "unit": pl.String,
            "description": pl.String,
        }
    )


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
                return _empty_macro_dataframe()

            required_columns = {"date", "on"}
            missing = required_columns - set(response.columns)
            if missing:
                missing_text = sorted(missing)
                msg = f"Missing required columns from shibor response: {missing_text}"
                raise ValueError(msg)

            normalized = response.with_columns(
                pl.col("date").cast(pl.String).str.to_date(strict=False).alias("date"),
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

            MACRO_INDICATOR_SOURCE_SCHEMA.validate(result)
            logger.info(
                "Tushare macro indicators fetched",
                event="tushare_macro_indicators_fetch_complete",
                row_count=len(result),
            )
            return result
