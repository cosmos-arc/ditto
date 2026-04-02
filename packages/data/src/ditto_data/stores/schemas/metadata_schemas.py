"""Metadata 域的 StoreSchema 定义."""

from __future__ import annotations

import polars as pl

from ditto_data.stores.schemas.store_schema import StoreSchema

__all__ = [
    "INDEX_WEIGHT_STORE_SCHEMA",
    "UNIVERSE_CONSTITUENT_STORE_SCHEMA",
]

INDEX_WEIGHT_STORE_SCHEMA = StoreSchema(
    dataset="metadata/index/weight",
    key_columns=("index_instrument_id", "constituent_instrument_id", "trade_date"),
    schema={
        "index_instrument_id": pl.Int64,
        "constituent_instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "weight": pl.Float64,
        "source": pl.Utf8,
        "index_code": pl.Utf8,
        "con_code": pl.Utf8,
    },
)

UNIVERSE_CONSTITUENT_STORE_SCHEMA = StoreSchema(
    dataset="metadata/universe/constituent",
    key_columns=("universe_id", "instrument_id", "effective_from"),
    schema={
        "universe_id": pl.Utf8,
        "instrument_id": pl.Int64,
        "source": pl.Utf8,
        "source_ticker": pl.Utf8,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "weight": pl.Float64,
    },
)
