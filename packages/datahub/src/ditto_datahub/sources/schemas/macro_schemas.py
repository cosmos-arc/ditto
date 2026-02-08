"""Macro SourceSchema definitions."""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = ["MACRO_INDICATOR_SOURCE_SCHEMA"]

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
