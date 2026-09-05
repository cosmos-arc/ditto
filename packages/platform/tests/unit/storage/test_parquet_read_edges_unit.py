"""Date-boundary and no-transform edges for Parquet scans."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_platform.foundation.storage.parquet_read import scan_parquet


def _write_dates(tmp_path: Path) -> Path:
    path = tmp_path / "dates.parquet"
    pl.DataFrame(
        {
            "id": [1, 2, 3],
            "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
        }
    ).write_parquet(path)
    return path


def test_date_filtered_scan_requires_an_explicit_date_column(tmp_path: Path) -> None:
    path = _write_dates(tmp_path)

    with pytest.raises(ValueError, match="date_column is required"):
        scan_parquet(
            [str(path)],
            [],
            "2024-01-01",
            None,
            None,
            [],
            [],
        )


def test_scan_supports_start_only_without_sort_or_dedup(tmp_path: Path) -> None:
    path = _write_dates(tmp_path)

    result = scan_parquet(
        [str(path)],
        [],
        "2024-01-02",
        None,
        "date",
        [],
        [],
    )

    assert result["id"].to_list() == [2, 3]


def test_scan_supports_end_only_without_sort_or_dedup(tmp_path: Path) -> None:
    path = _write_dates(tmp_path)

    result = scan_parquet(
        [str(path)],
        [],
        None,
        "2024-01-02",
        "date",
        [],
        [],
    )

    assert result["id"].to_list() == [1, 2]
