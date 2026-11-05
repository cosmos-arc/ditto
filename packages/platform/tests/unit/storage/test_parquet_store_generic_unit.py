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


def test_identical_retry_recovers_partial_payload_and_rejects_revision(tmp_path):
    store = ParquetStore(data_root=tmp_path, key_columns=("id",))
    original = pl.DataFrame({"id": [1, 2], "value": [10, 20]})
    store.write("retry", original.head(1), year=2026)
    recovered = store.write(
        "retry", original, on_duplicate="verify_identical", year=2026
    )
    repeated = store.write(
        "retry", original, on_duplicate="verify_identical", year=2026
    )
    assert (recovered.added, recovered.updated, recovered.skipped) == (1, 0, 1)
    assert (repeated.added, repeated.updated, repeated.skipped) == (0, 0, 2)
    assert store.read("retry").equals(original)
    with pytest.raises(ValueError, match="conflict"):
        store.write(
            "retry",
            pl.DataFrame({"id": [1], "value": [999]}),
            on_duplicate="verify_identical",
            year=2026,
        )
    assert store.read("retry").equals(original)


class TestParquetStoreTransientCorrectionFlag:
    """瞬态修正标记列的入口剥离与非 FLAGGED 策略安全(#613 G F1/F5)。"""

    @staticmethod
    def _store(tmp_path):
        return ParquetStore(
            data_root=tmp_path,
            key_columns=("id",),
            date_column="date",
        )

    def test_force_keep_last_strips_flag_on_new_partition(self, tmp_path):
        """force 首写新分区不得把标记列持久化(分区毒化修复)。"""
        store = self._store(tmp_path)
        store.write(
            "fina",
            pl.DataFrame(
                {
                    "id": [1],
                    "date": [date(2026, 1, 1)],
                    "value": [10],
                    "is_provider_correction": [True],
                }
            ),
            year=2026,
            on_duplicate="keep_last",
        )
        stored = store.read("fina")
        assert "is_provider_correction" not in stored.columns

    def test_force_keep_last_strips_flag_on_existing_partition(self, tmp_path):
        """force 覆写已有分区不再因列宽不齐 ShapeError。"""
        store = self._store(tmp_path)
        store.write(
            "fina",
            pl.DataFrame({"id": [1], "date": [date(2026, 1, 1)], "value": [10]}),
            year=2026,
        )
        store.write(
            "fina",
            pl.DataFrame(
                {
                    "id": [1],
                    "date": [date(2026, 1, 1)],
                    "value": [99],
                    "is_provider_correction": [True],
                }
            ),
            year=2026,
            on_duplicate="keep_last",
        )
        assert store.read("fina")["value"].to_list() == [99]
        assert "is_provider_correction" not in store.read("fina").columns

    def test_flagged_strategy_without_key_columns_raises(self) -> None:
        existing = pl.DataFrame({"id": [1], "value": [1]})
        from ditto_platform.foundation.storage.parquet_write import merge_with_existing
        from ditto_platform.foundation.storage.types import OnDuplicate

        with pytest.raises(ValueError, match="key columns"):
            merge_with_existing(
                pl.DataFrame(
                    {"id": [2], "value": [2], "is_provider_correction": [True]}
                ),
                existing,
                [],
                OnDuplicate.KEEP_LAST_FLAGGED,
            )

    def test_batch_internal_dedup_flagged_row_wins(self, tmp_path):
        """同键混合 flag 批次:批内预去重保留修正行。"""
        store = self._store(tmp_path)
        store.write(
            "fina",
            pl.DataFrame(
                {
                    "id": [1, 1],
                    "date": [date(2026, 1, 1), date(2026, 1, 1)],
                    "value": [10, 99],
                    "is_provider_correction": [False, True],
                }
            ),
            year=2026,
            on_duplicate="keep_last_flagged",
        )
        assert store.read("fina")["value"].to_list() == [99]

    def test_flagged_first_write_to_new_partition_strips_flag(self, tmp_path):
        """审计 #684 批B #5：首写新分区无 merge 可消费标记列——schema 无
        is_provider_correction，且第二次 FLAGGED 写（merge 路径）成功升级。"""
        store = self._store(tmp_path)
        store.write(
            "fina",
            pl.DataFrame(
                {
                    "id": [1, 2],
                    "date": [date(2026, 1, 1), date(2026, 1, 2)],
                    "value": [10, 20],
                    "is_provider_correction": [False, False],
                }
            ),
            year=2026,
            on_duplicate="keep_last_flagged",
        )

        stored = store.read("fina")
        assert "is_provider_correction" not in stored.columns
        assert stored["value"].to_list() == [10, 20]

        # 第二次 FLAGGED 写走 merge 路径，修正行正常升级
        result = store.write(
            "fina",
            pl.DataFrame(
                {
                    "id": [1],
                    "date": [date(2026, 1, 1)],
                    "value": [99],
                    "is_provider_correction": [True],
                }
            ),
            year=2026,
            on_duplicate="keep_last_flagged",
        )
        assert (result.added, result.updated) == (0, 1)
        assert store.read("fina")["value"].sort().to_list() == [20, 99]
        assert "is_provider_correction" not in store.read("fina").columns

    def test_verify_identical_batch_dup_ignores_transient_flag(self, tmp_path):
        """#684 批B correctness F2：仅 is_provider_correction 不同的同键行
        在 VERIFY_IDENTICAL 批内去重不算 changed values（与剥离前语义一致）。"""
        store = self._store(tmp_path)
        store.write(
            "fina",
            pl.DataFrame(
                {
                    "id": [1, 1],
                    "date": [date(2026, 1, 1), date(2026, 1, 1)],
                    "value": [10, 10],
                    "is_provider_correction": [False, True],
                }
            ),
            year=2026,
            on_duplicate="verify_identical",
        )
        assert store.read("fina")["value"].to_list() == [10]
        assert "is_provider_correction" not in store.read("fina").columns
