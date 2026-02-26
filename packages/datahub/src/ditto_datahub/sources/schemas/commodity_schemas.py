"""Commodity SourceSchema definitions."""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["COMMODITY_SOURCE_SCHEMA"]

COMMODITY_SOURCE_SCHEMA = SourceSchema(
    dataset="commodity_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 商品价格不需要 PIT
)
