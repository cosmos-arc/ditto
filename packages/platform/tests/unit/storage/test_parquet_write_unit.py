"""Unit tests for parquet_write helpers -- prepare_for_write / merge_with_existing."""

from __future__ import annotations

import datetime

import polars as pl
import pytest
from ditto_platform.foundation.storage.parquet_write import (
    MergeResult,
    merge_with_existing,
    prepare_for_write,
)
from ditto_platform.foundation.storage.types import OnDuplicate

# ---------------------------------------------------------------------------
# prepare_for_write
# ---------------------------------------------------------------------------


class TestPrepareForWrite:
    """Tests for prepare_for_write normalization and sorting."""

    def test_prepare_for_write_no_date_column(self) -> None:
        """Without date_column, only sorting is applied."""
        df = pl.DataFrame({"id": [3, 1, 2], "value": [10, 20, 30]})
        result = prepare_for_write(df, date_column=None, sort_columns=["id"])
        assert result["id"].to_list() == [1, 2, 3]

    def test_prepare_for_write_string_date_column(self) -> None:
        """String date_column is parsed to Date type."""
        df = pl.DataFrame(
            {"id": [1, 2], "date": ["2024-01-02", "2024-01-01"], "value": [10, 20]}
        )
        result = prepare_for_write(df, date_column="date", sort_columns=["date"])
        assert result["date"].dtype == pl.Date
        assert result["date"].to_list() == [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ]

    def test_prepare_for_write_date_column_already_date_type(self) -> None:
        """Date-typed column passes through without conversion."""
        df = pl.DataFrame(
            {
                "id": [1, 2],
                "date": [datetime.date(2024, 1, 2), datetime.date(2024, 1, 1)],
                "value": [10, 20],
            }
        )
        result = prepare_for_write(df, date_column="date", sort_columns=["date"])
        assert result["date"].dtype == pl.Date
        assert result["date"].to_list() == [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ]

    def test_prepare_for_write_datetime_column_cast_to_date(self) -> None:
        """Datetime-typed date_column is cast to Date."""
        df = pl.DataFrame(
            {
                "id": [1],
                "date": pl.Series(
                    "date",
                    [datetime.datetime(2024, 1, 1, 12, 0)],
                    dtype=pl.Datetime("us"),
                ),
                "value": [10],
            }
        )
        result = prepare_for_write(df, date_column="date", sort_columns=[])
        assert result["date"].dtype == pl.Date
        assert result["date"].to_list() == [datetime.date(2024, 1, 1)]

    def test_prepare_for_write_empty_sort_columns(self) -> None:
        """Empty sort_columns returns df unchanged (aside from date normalization)."""
        df = pl.DataFrame({"id": [3, 1, 2], "value": [10, 20, 30]})
        result = prepare_for_write(df, date_column=None, sort_columns=[])
        assert result["id"].to_list() == [3, 1, 2]

    def test_prepare_for_write_date_column_not_in_df(self) -> None:
        """date_column specified but not present in df -- no error, just sort."""
        df = pl.DataFrame({"id": [2, 1], "value": [20, 10]})
        result = prepare_for_write(df, date_column="missing_col", sort_columns=["id"])
        assert result["id"].to_list() == [1, 2]


# ---------------------------------------------------------------------------
# merge_with_existing
# ---------------------------------------------------------------------------


def _df_from_data(data: dict) -> pl.DataFrame:
    """Build a DataFrame from a dict, ensuring consistent types."""
    return pl.DataFrame(data)


class TestMergeWithExisting:
    """Tests for merge_with_existing dedup strategies."""

    def test_merge_no_overlap(self) -> None:
        """No overlapping keys -- simple concat."""
        existing = _df_from_data({"id": [1, 2], "value": [10, 20]})
        incoming = _df_from_data({"id": [3, 4], "value": [30, 40]})
        result = merge_with_existing(incoming, existing, ["id"], OnDuplicate.ERROR)
        assert isinstance(result, MergeResult)
        assert result.added == 2
        assert result.updated == 0
        assert len(result.df) == 4

    def test_merge_error_strategy_raises_on_overlap(self) -> None:
        """ERROR strategy raises ValueError when keys overlap."""
        existing = _df_from_data({"id": [1, 2], "value": [10, 20]})
        incoming = _df_from_data({"id": [2, 3], "value": [25, 30]})
        with pytest.raises(ValueError, match="Duplicate data"):
            merge_with_existing(incoming, existing, ["id"], OnDuplicate.ERROR)

    def test_merge_keep_first_preserves_existing(self) -> None:
        """KEEP_FIRST: existing rows are kept, new duplicates are discarded."""
        existing = _df_from_data({"id": [1, 2], "value": [10, 20]})
        incoming = _df_from_data({"id": [2, 3], "value": [99, 30]})
        result = merge_with_existing(incoming, existing, ["id"], OnDuplicate.KEEP_FIRST)
        assert result.updated == 0
        assert result.added == 1
        # id=2 should keep value=20 from existing
        row_for_id_2 = result.df.filter(pl.col("id") == 2)
        assert row_for_id_2["value"].to_list() == [20]
        # id=3 should be added
        row_for_id_3 = result.df.filter(pl.col("id") == 3)
        assert row_for_id_3["value"].to_list() == [30]

    def test_merge_keep_last_overwrites_existing(self) -> None:
        """KEEP_LAST: new data overwrites existing for overlapping keys."""
        existing = _df_from_data({"id": [1, 2], "value": [10, 20]})
        incoming = _df_from_data({"id": [2, 3], "value": [99, 30]})
        result = merge_with_existing(incoming, existing, ["id"], OnDuplicate.KEEP_LAST)
        assert result.updated == 1
        assert result.added == 1
        # id=2 should have value=99 from incoming
        row_for_id_2 = result.df.filter(pl.col("id") == 2)
        assert row_for_id_2["value"].to_list() == [99]

    def test_merge_empty_key_columns(self) -> None:
        """Empty key_columns -- simple concat, no dedup."""
        existing = _df_from_data({"id": [1], "value": [10]})
        incoming = _df_from_data({"id": [1], "value": [20]})
        result = merge_with_existing(incoming, existing, [], OnDuplicate.ERROR)
        assert result.added == 1
        assert result.updated == 0
        assert len(result.df) == 2

    def test_merge_error_strategy_no_overlap_succeeds(self) -> None:
        """ERROR strategy succeeds when there is no key overlap."""
        existing = _df_from_data({"id": [1], "value": [10]})
        incoming = _df_from_data({"id": [2], "value": [20]})
        result = merge_with_existing(incoming, existing, ["id"], OnDuplicate.ERROR)
        assert result.added == 1
        assert len(result.df) == 2

    def test_verify_identical_ignores_source_ticker_alias_flip(self) -> None:
        """#599 F2：同键同值、仅别名出处列翻转 → 重试通过，保已存行."""
        existing = _df_from_data(
            {"id": [1], "source_ticker": ["920018.BJ"], "value": [10.5]}
        )
        incoming = _df_from_data(
            {"id": [1], "source_ticker": ["430018.BJ"], "value": [10.5]}
        )
        result = merge_with_existing(
            incoming, existing, ["id"], OnDuplicate.VERIFY_IDENTICAL
        )
        assert result.updated == 0
        kept = result.df.filter(pl.col("id") == 1)
        assert kept["value"].to_list() == [10.5]
        assert kept["source_ticker"].to_list() == ["920018.BJ"]

    def test_verify_identical_rejects_value_change_under_alias_flip(self) -> None:
        """#599 F2：出处列翻转不能掩护事实值变化——仍 fail-closed."""
        existing = _df_from_data(
            {"id": [1], "source_ticker": ["920017.BJ"], "value": [None]}
        )
        incoming = _df_from_data(
            {"id": [1], "source_ticker": ["430017.BJ"], "value": [-112842757.96]}
        )
        with pytest.raises(ValueError, match="changed values"):
            merge_with_existing(
                incoming, existing, ["id"], OnDuplicate.VERIFY_IDENTICAL
            )

    def test_verify_identical_rejects_schema_drift(self) -> None:
        """列集差异（schema 漂移）照旧先拒——出处列忽略不放宽漂移检测."""
        existing = _df_from_data({"id": [1], "source_ticker": ["a"], "value": [1.0]})
        incoming = _df_from_data(
            {"id": [1], "source_ticker": ["a"], "value": [1.0], "extra": ["x"]}
        )
        with pytest.raises(ValueError, match="changed values"):
            merge_with_existing(
                incoming, existing, ["id"], OnDuplicate.VERIFY_IDENTICAL
            )


class TestMergeKeepLastFlagged:
    """KEEP_LAST_FLAGGED: 修正行单调升级、非修正行只插新键。"""

    @staticmethod
    def _flagged(id_: int, value: int, flag: bool) -> pl.DataFrame:
        return pl.DataFrame(
            {"id": [id_], "value": [value], "is_provider_correction": [flag]}
        )

    def test_flagged_row_upgrades_existing(self) -> None:
        existing = pl.DataFrame({"id": [1], "value": [10]})
        result = merge_with_existing(
            self._flagged(1, 99, True),
            existing,
            ["id"],
            OnDuplicate.KEEP_LAST_FLAGGED,
        )
        assert result.df.filter(pl.col("id") == 1)["value"].to_list() == [99]
        assert result.updated == 1
        assert "is_provider_correction" not in result.df.columns

    def test_unflagged_conflict_keeps_existing(self) -> None:
        """未标记行不得降级存量(数据源旧代快照回写防护)。"""
        existing = pl.DataFrame({"id": [1], "value": [99]})
        result = merge_with_existing(
            self._flagged(1, 10, False),
            existing,
            ["id"],
            OnDuplicate.KEEP_LAST_FLAGGED,
        )
        assert result.df.filter(pl.col("id") == 1)["value"].to_list() == [99]
        assert result.updated == 0
        assert result.added == 0

    def test_new_key_inserts_regardless_of_flag(self) -> None:
        existing = pl.DataFrame({"id": [1], "value": [10]})
        result = merge_with_existing(
            pl.concat([self._flagged(2, 20, False), self._flagged(3, 30, True)]),
            existing,
            ["id"],
            OnDuplicate.KEEP_LAST_FLAGGED,
        )
        assert result.df["id"].to_list() == [1, 2, 3]
        assert result.added == 2

    def test_missing_flag_column_raises(self) -> None:
        existing = pl.DataFrame({"id": [1], "value": [10]})
        incoming = pl.DataFrame({"id": [2], "value": [20]})
        with pytest.raises(ValueError, match="KEEP_LAST_FLAGGED"):
            merge_with_existing(
                incoming, existing, ["id"], OnDuplicate.KEEP_LAST_FLAGGED
            )

    def test_existing_with_flag_column_raises(self) -> None:
        existing = pl.DataFrame(
            {"id": [1], "value": [10], "is_provider_correction": [True]}
        )
        with pytest.raises(ValueError, match="existing frame"):
            merge_with_existing(
                self._flagged(1, 99, True),
                existing,
                ["id"],
                OnDuplicate.KEEP_LAST_FLAGGED,
            )
