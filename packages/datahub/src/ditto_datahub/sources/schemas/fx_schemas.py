"""FX (Foreign Exchange) SourceSchema definitions."""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["FX_SOURCE_SCHEMA"]

FX_SOURCE_SCHEMA = SourceSchema(
    dataset="fx_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 汇率数据不需要 PIT
)
