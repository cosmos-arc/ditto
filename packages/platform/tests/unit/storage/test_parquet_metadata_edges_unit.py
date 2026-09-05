"""Empty and malformed filesystem edges for Parquet metadata helpers."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_platform.foundation.storage.parquet_metadata import (
    get_checksum,
    get_date_range,
    get_years,
    list_unique_values,
)


def test_metadata_helpers_return_empty_values_for_missing_inputs(
    tmp_path: Path,
) -> None:
    assert get_years(tmp_path, "missing") == []
    assert get_checksum(tmp_path / "missing.parquet") == ""
    assert get_date_range([], "date") == (None, None)
    assert list_unique_values([], "instrument") == []


def test_get_years_ignores_non_numeric_parquet_stems(tmp_path: Path) -> None:
    dataset = tmp_path / "events"
    dataset.mkdir()
    (dataset / "README.parquet").touch()
    (dataset / "2025.parquet").touch()

    assert get_years(tmp_path, "events") == [2025]


def test_get_date_range_returns_empty_for_a_schema_only_partition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "empty.parquet"
    pl.DataFrame(schema={"date": pl.Date}).write_parquet(path)

    assert get_date_range([path], "date") == (None, None)
