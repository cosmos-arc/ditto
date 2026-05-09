"""Metadata helpers for ParquetStore — years, checksum, count, date range."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from ditto_platform.foundation.util.io import file_md5


def get_years(data_root: Path, dataset: str) -> list[int]:
    """Return sorted list of available years for a dataset."""
    dataset_dir = data_root / dataset
    if not dataset_dir.exists():
        return []

    years: list[int] = []
    for f in dataset_dir.glob("*.parquet"):
        try:
            years.append(int(f.stem))
        except ValueError:
            continue
    return sorted(years)


def get_checksum(path: Path) -> str:
    """MD5 checksum of a parquet file, or empty string if missing."""
    if path.exists():
        result: str = file_md5(path)
        return result
    return ""


def get_date_range(
    paths: list[Path],
    date_column: str,
) -> tuple[str | None, str | None]:
    """Return (min_date, max_date) across all partitions, or (None, None)."""
    if not paths:
        return None, None

    lf = pl.scan_parquet([str(p) for p in paths])
    min_max = lf.select(
        [
            pl.col(date_column).min().alias("min"),
            pl.col(date_column).max().alias("max"),
        ]
    ).collect()

    if len(min_max) == 0 or min_max["min"][0] is None:
        return None, None

    return str(min_max["min"][0]), str(min_max["max"][0])


def list_unique_values(paths: list[Path], column: str) -> list[Any]:
    """Return sorted unique values from a column across partitions."""
    if not paths:
        return []

    lf = pl.scan_parquet([str(p) for p in paths])
    result = lf.select(pl.col(column).unique().sort()).collect()
    values: list[Any] = result[column].to_list()
    return values
