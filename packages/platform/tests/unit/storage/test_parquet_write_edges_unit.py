"""Merge rejection and single-bound deletion edges for Parquet writes."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from ditto_platform.foundation.storage.parquet_write import (
    delete_from_partition,
    merge_with_existing,
)
from ditto_platform.foundation.storage.types import OnDuplicate


def _write_dates(path: Path) -> None:
    pl.DataFrame(
        {
            "id": [1, 2, 3],
            "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
        }
    ).write_parquet(path)


def test_merge_rejects_an_unknown_duplicate_strategy() -> None:
    existing = pl.DataFrame({"id": [1], "value": [10]})
    incoming = pl.DataFrame({"id": [1], "value": [11]})

    with pytest.raises(ValueError, match="Unknown OnDuplicate strategy"):
        merge_with_existing(
            incoming,
            existing,
            ["id"],
            cast(OnDuplicate, "replace_all"),
        )


def test_delete_supports_a_start_date_without_an_end_date(tmp_path: Path) -> None:
    path = tmp_path / "start.parquet"
    _write_dates(path)

    deleted = delete_from_partition(path, [], "date", "2024-01-02", None)

    assert deleted == 2
    assert pl.read_parquet(path)["id"].to_list() == [1]


def test_delete_supports_an_end_date_without_a_start_date(tmp_path: Path) -> None:
    path = tmp_path / "end.parquet"
    _write_dates(path)

    deleted = delete_from_partition(path, [], "date", None, "2024-01-02")

    assert deleted == 2
    assert pl.read_parquet(path)["id"].to_list() == [3]


def test_delete_unlinks_partition_when_every_row_matches(tmp_path: Path) -> None:
    path = tmp_path / "all.parquet"
    _write_dates(path)

    deleted = delete_from_partition(path, [pl.lit(True)], "", None, None)

    assert deleted == 3
    assert not path.exists()
