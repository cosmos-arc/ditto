"""Stable result schemas for unified derived queries."""

from __future__ import annotations

import polars as pl

type SchemaDef = tuple[tuple[str, type[pl.DataType] | pl.DataType], ...]

LATEST_RESULT_SCHEMA: SchemaDef = (
    ("derived_id", pl.String),
    ("instrument_id", pl.Int64),
    ("value", pl.Float64),
    ("trade_date", pl.Date),
    ("bar_time", pl.Time),
    ("asof_ts", pl.Datetime),
    ("version", pl.Int64),
)
SERIES_RESULT_SCHEMA: SchemaDef = (
    ("derived_id", pl.String),
    ("instrument_id", pl.Int64),
    ("trade_date", pl.Date),
    ("bar_time", pl.Time),
    ("value", pl.Float64),
    ("asof_ts", pl.Datetime),
    ("version", pl.Int64),
)
COMPARE_RESULT_SCHEMA: SchemaDef = (
    ("derived_id", pl.String),
    ("instrument_id", pl.Int64),
    ("trade_date", pl.Date),
    ("serving_value", pl.Float64),
    ("offline_value", pl.Float64),
    ("diff", pl.Float64),
)

LATEST_RESULT_COLUMNS = tuple(column for column, _ in LATEST_RESULT_SCHEMA)
SERIES_RESULT_COLUMNS = tuple(column for column, _ in SERIES_RESULT_SCHEMA)
COMPARE_RESULT_COLUMNS = tuple(column for column, _ in COMPARE_RESULT_SCHEMA)

__all__ = [
    "COMPARE_RESULT_COLUMNS",
    "LATEST_RESULT_COLUMNS",
    "SERIES_RESULT_COLUMNS",
    "empty_compare_result",
    "empty_latest_result",
    "empty_series_result",
]


def _empty_frame(schema: SchemaDef) -> pl.DataFrame:
    """Create an empty dataframe with a stable schema."""
    return pl.DataFrame(
        {
            column: pl.Series(name=column, values=[], dtype=dtype)
            for column, dtype in schema
        }
    )


def empty_latest_result() -> pl.DataFrame:
    """Create an empty latest result frame."""
    return _empty_frame(LATEST_RESULT_SCHEMA)


def empty_series_result() -> pl.DataFrame:
    """Create an empty series result frame."""
    return _empty_frame(SERIES_RESULT_SCHEMA)


def empty_compare_result() -> pl.DataFrame:
    """Create an empty compare result frame."""
    return _empty_frame(COMPARE_RESULT_SCHEMA)
