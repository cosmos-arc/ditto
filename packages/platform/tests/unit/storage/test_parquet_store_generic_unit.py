"""Unit tests for generic ParquetStore behavior."""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
import pytest
from ditto_platform.foundation.storage import ParquetStore


def test_parquet_store_uses_explicit_key_and_date_columns(tmp_path):
    store = ParquetStore(
        data_root=tmp_path,
        key_columns=("id", "date"),
        date_column="date",
    )

    assert store._get_key_columns() == ["id", "date"]
    assert store._get_date_column() == "date"


def test_parquet_store_has_no_implicit_key_or_date_columns(tmp_path):
    store = ParquetStore(data_root=tmp_path)

    assert store._get_key_columns() == []
    assert store._get_date_column() is None


def test_parquet_store_rejects_removed_domain_specific_kwargs(tmp_path):
    store = ParquetStore(data_root=tmp_path)

    with pytest.raises(TypeError):
        store.read("dataset", instrument_ids=[1])  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        store.delete("dataset", instrument_ids=[1])  # type: ignore[call-arg]


def test_delete_combines_filters_and_date_range_as_intersection(tmp_path):
    store = ParquetStore(
        data_root=tmp_path,
        key_columns=("id", "date"),
        date_column="date",
    )
    dataset = "generic"
    store.write(
        dataset,
        pl.DataFrame(
            {
                "id": [1, 1, 2, 2],
                "date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "value": [10, 11, 20, 21],
            }
        ),
        year=2024,
    )

    deleted = store.delete(
        dataset,
        filters=pl.col("id") == 1,
        start_date="2024-01-01",
        end_date="2024-01-01",
    )
    remaining = store.read(dataset)

    assert deleted == 1
    assert sorted(_records(remaining), key=lambda item: (item["id"], item["date"])) == [
        {"id": 1, "date": date(2024, 1, 2), "value": 11},
        {"id": 2, "date": date(2024, 1, 1), "value": 20},
        {"id": 2, "date": date(2024, 1, 2), "value": 21},
    ]


def test_delete_without_filters_or_date_range_is_noop(tmp_path):
    store = ParquetStore(
        data_root=tmp_path,
        key_columns=("id", "date"),
        date_column="date",
    )
    dataset = "generic"
    store.write(
        dataset,
        pl.DataFrame(
            {
                "id": [1, 2],
                "date": [date(2024, 1, 1), date(2024, 1, 2)],
                "value": [10, 20],
            }
        ),
        year=2024,
    )

    deleted = store.delete(dataset)
    remaining = store.read(dataset)

    assert deleted == 0
    assert sorted(_records(remaining), key=lambda item: (item["id"], item["date"])) == [
        {"id": 1, "date": date(2024, 1, 1), "value": 10},
        {"id": 2, "date": date(2024, 1, 2), "value": 20},
    ]


def _records(df: pl.DataFrame) -> list[dict[str, Any]]:
    return df.select("id", "date", "value").to_dicts()
