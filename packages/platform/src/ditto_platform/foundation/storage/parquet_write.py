"""Write helpers for ParquetStore — prepare, merge, dedup, and delete logic."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from ditto_platform.foundation.storage.types import OnDuplicate
from ditto_platform.foundation.util.io import atomic_write


@dataclass(frozen=True)
class MergeResult:
    """Merge result."""

    df: pl.DataFrame
    added: int
    updated: int


def prepare_for_write(
    df: pl.DataFrame,
    date_column: str | None,
    sort_columns: list[str],
) -> pl.DataFrame:
    """Normalize date columns and sort before writing."""
    if date_column is not None and date_column in df.columns:
        if df[date_column].dtype == pl.String:
            df = df.with_columns(pl.col(date_column).str.strptime(pl.Date, "%Y-%m-%d"))
        elif df[date_column].dtype != pl.Date:
            df = df.with_columns(pl.col(date_column).cast(pl.Date))

    if not sort_columns:
        return df
    return df.sort(sort_columns)


# -- merge strategy helpers --------------------------------------------------


def _merge_error(
    _df: pl.DataFrame,
    _existing: pl.DataFrame,
    _key_columns: list[str],
    overlap_count: int,
) -> MergeResult:
    """ERROR 策略 — 检测到重复键时抛出 ValueError。"""
    msg = (
        f"Duplicate data: {overlap_count} overlapping key pairs. "
        "Use OnDuplicate.KEEP_FIRST to preserve, or "
        "OnDuplicate.KEEP_LAST to overwrite."
    )
    raise ValueError(msg)


def _merge_keep_first(
    df: pl.DataFrame,
    existing: pl.DataFrame,
    key_columns: list[str],
    _overlap_count: int,
) -> MergeResult:
    """KEEP_FIRST 策略 — 保留已有数据，丢弃新数据中的重复行。"""
    existing_keys = existing.select(key_columns)
    new_keys = df.select(key_columns)
    non_overlapping = new_keys.join(existing_keys, on=key_columns, how="anti")
    df = df.join(non_overlapping, on=key_columns, how="inner")
    combined = pl.concat([existing, df])
    return MergeResult(df=combined, added=len(df), updated=0)


def _merge_keep_last(
    df: pl.DataFrame,
    existing: pl.DataFrame,
    key_columns: list[str],
    overlap_count: int,
) -> MergeResult:
    """KEEP_LAST 策略 — 用新数据覆盖已有数据（Last-Write-Wins）。"""
    combined = pl.concat([existing, df])
    combined = combined.unique(subset=key_columns, keep="last")
    added = len(df) - overlap_count
    return MergeResult(df=combined, added=added, updated=overlap_count)


_MERGE_STRATEGIES: dict[OnDuplicate, Callable[..., MergeResult]] = {
    OnDuplicate.ERROR: _merge_error,
    OnDuplicate.KEEP_FIRST: _merge_keep_first,
    OnDuplicate.KEEP_LAST: _merge_keep_last,
}


def merge_with_existing(
    df: pl.DataFrame,
    existing: pl.DataFrame,
    key_columns: list[str],
    on_duplicate: OnDuplicate,
) -> MergeResult:
    """
    Merge *df* into *existing* using the given dedup strategy.

    Raises:
        ValueError: If ``on_duplicate=ERROR`` and duplicates are found.

    """
    if not key_columns:
        combined = pl.concat([existing, df])
        return MergeResult(df=combined, added=len(df), updated=0)

    existing_keys = existing.select(key_columns)
    new_keys = df.select(key_columns)

    merged_keys = existing_keys.join(new_keys, on=key_columns, how="inner")
    overlap_count = len(merged_keys)

    if merged_keys.is_empty():
        combined = pl.concat([existing, df])
        return MergeResult(df=combined, added=len(df), updated=0)

    strategy = _MERGE_STRATEGIES.get(on_duplicate)
    if strategy is None:
        msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
        raise ValueError(msg)
    return strategy(df, existing, key_columns, overlap_count)


def delete_from_partition(
    path: Path,
    filters: list[pl.Expr],
    date_col: str,
    start_date: str | None,
    end_date: str | None,
) -> int:
    """
    Delete matching rows from a single partition file.

    Returns the number of deleted rows.  Removes the file entirely if
    no rows remain.
    """
    df = pl.read_parquet(path)
    original_count = len(df)

    delete_mask: pl.Expr | None = None

    for expr in filters:
        delete_mask = expr if delete_mask is None else delete_mask & expr

    if start_date and end_date:
        in_range = (
            pl.col(date_col) >= pl.lit(start_date).str.strptime(pl.Date, "%Y-%m-%d")
        ) & (pl.col(date_col) <= pl.lit(end_date).str.strptime(pl.Date, "%Y-%m-%d"))
        delete_mask = in_range if delete_mask is None else delete_mask & in_range
    elif start_date:
        in_range = pl.col(date_col) >= pl.lit(start_date).str.strptime(
            pl.Date, "%Y-%m-%d"
        )
        delete_mask = in_range if delete_mask is None else delete_mask & in_range
    elif end_date:
        in_range = pl.col(date_col) <= pl.lit(end_date).str.strptime(
            pl.Date, "%Y-%m-%d"
        )
        delete_mask = in_range if delete_mask is None else delete_mask & in_range

    if delete_mask is None:
        return 0

    df = df.filter(~delete_mask)
    deleted_count = original_count - len(df)

    if len(df) > 0:
        atomic_write(df, path)
    else:
        path.unlink()

    return deleted_count
