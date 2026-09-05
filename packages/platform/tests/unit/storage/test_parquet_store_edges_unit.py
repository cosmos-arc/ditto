"""Public error and empty-result edges for the generic Parquet store."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from ditto_platform.foundation.storage import ParquetStore


def test_write_rejects_invalid_payload_or_partition_identity(
    tmp_path: Path,
) -> None:
    store = ParquetStore(tmp_path)

    with pytest.raises(ValueError, match="polars DataFrame"):
        store.write("events", {"id": [1]}, year=2024)
    with pytest.raises(ValueError, match="year parameter is required"):
        store.write("events", pl.DataFrame({"id": [1]}))
    with pytest.raises(ValueError, match="year must be an integer"):
        store.write("events", pl.DataFrame({"id": [1]}), year="2024")


def test_empty_write_returns_zero_result_without_creating_a_partition(
    tmp_path: Path,
) -> None:
    store = ParquetStore(tmp_path)

    result = store.write("events", pl.DataFrame(schema={"id": pl.Int64}), year=2024)

    assert result.file_path == ""
    assert result.added == 0
    assert not (tmp_path / "events").exists()


def test_store_without_keys_writes_but_rejects_date_based_reads(
    tmp_path: Path,
) -> None:
    store = ParquetStore(tmp_path)
    written = store.write("events", pl.DataFrame({"id": [2, 1]}), year=2024)

    assert written.added == 2
    assert store.read("events")["id"].to_list() == [2, 1]
    assert store.get_date_range("events") == (None, None)
    with pytest.raises(ValueError, match="date_column is required"):
        store.read("events", start_date="2024-01-01")


def test_write_deduplicates_repeated_keys_within_one_batch(tmp_path: Path) -> None:
    store = ParquetStore(tmp_path, key_columns=("id",))

    result = store.write(
        "events",
        pl.DataFrame({"id": [1, 1, 2], "value": [10, 11, 20]}),
        year=2024,
    )

    assert result.added == 2
    assert store.read("events").to_dicts() == [
        {"id": 1, "value": 10},
        {"id": 2, "value": 20},
    ]


def test_delete_returns_zero_when_dataset_has_no_partitions(tmp_path: Path) -> None:
    store = ParquetStore(tmp_path, date_column="date")

    assert store.delete("missing", start_date="2024-01-01") == 0
