"""Macro SourceSchema definitions."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["MACRO_INDICATOR_SOURCE_SCHEMA", "empty_macro_dataframe"]

MACRO_INDICATOR_SOURCE_SCHEMA = SourceSchema(
    dataset="macro_indicators",
    key_columns=("indicator_code", "date", "knowledge_date"),
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
    },
    pit_columns=("knowledge_date",),
)


def empty_macro_dataframe() -> pl.DataFrame:
    """Return empty DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA."""
    return pl.DataFrame(schema=MACRO_INDICATOR_SOURCE_SCHEMA.schema)
