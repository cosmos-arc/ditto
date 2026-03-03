"""Commodity SourceSchema definitions."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["COMMODITY_SOURCE_SCHEMA"]

COMMODITY_SOURCE_SCHEMA = SourceSchema(
    dataset="commodity_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "trade_date_utc": pl.Datetime("ms"),  # UTC 午夜时间戳
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
    pit_columns=(),  # 商品价格不需要 PIT
)
