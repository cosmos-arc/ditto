"""Read helpers for ParquetStore — scan, filter, and dedup logic."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import polars as pl


def normalize_filters(
    filters: pl.Expr | Sequence[pl.Expr] | None,
) -> list[pl.Expr]:
    """Normalize an optional expression collection to a list."""
    if filters is None:
        return []
    if isinstance(filters, pl.Expr):
        return [filters]
    return list(filters)


def scan_parquet(
    paths: list[str],
    filters: list[pl.Expr],
    start_date: str | None,
    end_date: str | None,
    date_column: str | None,
    sort_columns: list[str],
    key_columns: list[str],
) -> pl.DataFrame:
    """
    Scan parquet files with optional date range and dedup.

    Args:
        paths: Parquet file paths to scan.
        filters: Polars filter expressions.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        date_column: Date column for range filtering; must be non-None if
            *start_date* or *end_date* is provided.
        sort_columns: Columns for result ordering.
        key_columns: Columns for dedup (unique subset).

    Returns:
        Filtered, deduped, sorted DataFrame.

    """
    lf = pl.scan_parquet(paths)

    for expr in filters:
        lf = lf.filter(expr)

    if start_date or end_date:
        if date_column is None:
            msg = "date_column is required for date-based operations"
            raise ValueError(msg)

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col(date_column) >= pl.lit(start_dt))

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col(date_column) <= pl.lit(end_dt))

    if sort_columns:
        lf = lf.sort(sort_columns)
    if key_columns:
        lf = lf.unique(subset=key_columns, keep="last")
    if sort_columns:
        lf = lf.sort(sort_columns)

    return lf.collect()
