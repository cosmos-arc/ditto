"""Strict value adapters shared by the frozen research data feed."""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot

from ditto_application.processes.experiments.research_data_artifacts import (
    BOOLEAN_COLUMNS,
    DATE_COLUMNS,
    NUMERIC_COLUMNS,
    STRING_COLUMNS,
    research_data_error,
)


def market_snapshot(
    trade_date: str,
    instrument_id: InstrumentId,
    row: dict[str, Any],
) -> MarketSnapshot:
    """Map one exact frozen bar row to the existing backtest market type."""
    return MarketSnapshot(
        trade_date=trade_date,
        instrument_id=instrument_id,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        prev_close=float(row["prev_close"]),
        volume=float(row["volume"]),
        amount=float(row["amount"]),
        is_suspended=bool(row["is_suspended"]),
        limit_up=float(row["limit_up"]) if row["limit_up"] is not None else None,
        limit_down=(
            float(row["limit_down"]) if row["limit_down"] is not None else None
        ),
        avg_volume_20d=(
            float(row["avg_volume_20d"]) if row["avg_volume_20d"] is not None else None
        ),
    )


def date_expr(frame: pl.DataFrame, column: str) -> pl.Expr:
    """Return a strict Date expression for one validated date-like column."""
    dtype = frame.schema[column]
    if dtype == pl.String:
        return pl.col(column).str.to_date(strict=True)
    if dtype == pl.Date:
        return pl.col(column)
    return pl.col(column).dt.date()


def valid_column_dtype(column: str, dtype: pl.DataType) -> bool:
    """Return whether a required runtime column has its strict type family."""
    if column == "instrument_id":
        valid = dtype.is_integer()
    elif column in NUMERIC_COLUMNS:
        valid = dtype.is_numeric()
    elif column in BOOLEAN_COLUMNS:
        valid = dtype == pl.Boolean
    elif column in STRING_COLUMNS:
        valid = dtype == pl.String
    elif column in DATE_COLUMNS:
        valid = dtype == pl.String
        if not valid:
            valid = dtype == pl.Date
        if not valid:
            valid = dtype.base_type() == pl.Datetime
    else:
        valid = True
    return valid


def iso_date_expr(frame: pl.DataFrame, column: str) -> pl.Expr:
    """Return one canonical daily ISO-8601 expression."""
    return date_expr(frame, column).dt.strftime("%Y-%m-%d")


def exact_iso_date(value: object, field_name: str) -> str:
    """Validate an exact ``YYYY-MM-DD`` execution boundary."""
    if type(value) is str:
        try:
            if date.fromisoformat(value).isoformat() == value:
                return value
        except ValueError:
            pass
    raise research_data_error(
        f"{field_name} must be an exact ISO date",
        "invalid_execution_window",
        field=field_name,
    )
