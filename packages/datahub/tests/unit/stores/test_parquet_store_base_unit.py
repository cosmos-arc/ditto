"""Tests for ParquetStoreBase."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_datahub.stores.parquet_store_base import ParquetStoreBase
from ditto_datahub.types import OnDuplicate
from ditto_datahub.types import WriteResultStore as WriteResult

# ============ Mock Implementation ============


class MockStore(ParquetStoreBase):
    """Mock implementation of ParquetStoreBase for testing."""

    def _get_key_columns(self) -> list[str]:
        """返回键列名."""
        return ["sid", "trade_date"]

    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Mock read implementation - reads from actual parquet files.

        Args:
            dataset: Dataset name.
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        # Collect all paths for the dataset
        paths = self._collect_paths(dataset, 1970, 2100)
        if not paths:
            # Return empty DataFrame with schema to avoid coverage recursion
            return pl.DataFrame(
                schema={"sid": pl.Int32, "trade_date": pl.Date, "close": pl.Float64}
            )

        # Read all parquet files
        df = pl.read_parquet([str(p) for p in paths])

        # Apply filters if provided
        if sids is not None:
            df = df.filter(pl.col("sid").is_in(sids))

        if start_date is not None:
            df = df.filter(pl.col("trade_date") >= pl.lit(start_date).cast(pl.Date))

        if end_date is not None:
            df = df.filter(pl.col("trade_date") <= pl.lit(end_date).cast(pl.Date))

        return df


# ============ Fixtures ============


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Create sample test data with required columns."""
    data: dict[str, list[Any]] = {
        "sid": [1000001, 1000001, 1000002, 1000002],
        "trade_date": [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 2),
            date(2024, 1, 4),
        ],
        "close": [10.0, 11.0, 20.0, 21.0],
    }
    return pl.DataFrame(data)


@pytest.fixture
def store(data_root: Path) -> MockStore:
    """Create MockStore instance."""
    return MockStore(data_root)


@pytest.fixture
def store_with_data(data_root: Path) -> MockStore:
    """Create MockStore with sample data written."""
    store = MockStore(data_root)
    # Create sample data inline to avoid fixture recursion with coverage
    # pragma: no cover
    data: dict[str, list[Any]] = {  # pragma: no cover
        "sid": [1000001, 1000001, 1000002, 1000002],  # pragma: no cover
        "trade_date": [  # pragma: no cover
            date(2024, 1, 2),  # pragma: no cover
            date(2024, 1, 3),  # pragma: no cover
            date(2024, 1, 2),  # pragma: no cover
            date(2024, 1, 4),  # pragma: no cover
        ],  # pragma: no cover
        "close": [10.0, 11.0, 20.0, 21.0],  # pragma: no cover
    }  # pragma: no cover
    sample_df = pl.DataFrame(data)  # pragma: no cover
    # Write sample data for multiple years
    store.write("test_dataset", sample_df, 2023)  # pragma: no cover
    store.write("test_dataset", sample_df, 2024)  # pragma: no cover
    return store


# ============ _get_path tests ============


class TestGetPath:
    """Tests for _get_path method."""

    @pytest.mark.parametrize(
        ("dataset", "year", "expected_dataset", "expected_year"),
        [
            ("test_dataset", 2024, "test_dataset", 2024),
            ("stock_daily", 2023, "stock_daily", 2023),
            ("adj_factor", 2024, "adj_factor", 2024),
        ],
    )
    def test_get_path_generates_correct_path(
        self,
        store: MockStore,
        dataset: str,
        year: int,
        expected_dataset: str,
        expected_year: int,
    ) -> None:
        """Test _get_path generates correct file path for various datasets and years."""
        path = store._get_path(dataset, year)
        expected = store._data_root / expected_dataset / f"{expected_year}.parquet"
        assert path == expected


# ============ _collect_paths tests ============


class TestCollectPaths:
    """Tests for _collect_paths method."""

    def test_collect_paths_empty_dataset(self, store: MockStore) -> None:
        """Test _collect_paths with non-existent dataset."""
        paths = store._collect_paths("nonexistent", 2020, 2024)
        assert paths == []

    def test_collect_paths_all_years_exist(self, store_with_data: MockStore) -> None:
        """Test _collect_paths when all years exist."""
        paths = store_with_data._collect_paths("test_dataset", 2023, 2024)
        assert len(paths) == 2
        years = [int(p.stem) for p in paths]
        assert sorted(years) == [2023, 2024]

    def test_collect_paths_partial_years_exist(
        self, store_with_data: MockStore, tmp_path: Path
    ) -> None:
        """Test _collect_paths with some years missing."""
        # Create additional year files
        data_root = tmp_path / "data" / "test_dataset"
        (data_root / "2021.parquet").touch()
        (data_root / "2025.parquet").touch()

        paths = store_with_data._collect_paths("test_dataset", 2020, 2025)
        # Should have 2021, 2023, 2024, 2025 (2020 and 2022 don't exist)
        years = [int(p.stem) for p in paths]
        assert sorted(years) == [2021, 2023, 2024, 2025]

    def test_collect_paths_single_year(self, store_with_data: MockStore) -> None:
        """Test _collect_paths with single year range."""
        paths = store_with_data._collect_paths("test_dataset", 2024, 2024)
        assert len(paths) == 1
        assert int(paths[0].stem) == 2024

    def test_collect_paths_empty_range(self, store_with_data: MockStore) -> None:
        """Test _collect_paths with no matching years in range."""
        paths = store_with_data._collect_paths("test_dataset", 2020, 2021)
        assert paths == []


# ============ get_years tests ============


class TestGetYears:
    """Tests for get_years method."""

    def test_get_years_empty(self, store: MockStore) -> None:
        """Test get_years with no data."""
        years = store.get_years("test_dataset")
        assert years == []

    def test_get_years_returns_sorted_list(self, store_with_data: MockStore) -> None:
        """Test get_years returns sorted list of available years."""
        years = store_with_data.get_years("test_dataset")
        assert years == [2023, 2024]

    def test_get_years_with_invalid_filenames(
        self, store: MockStore, tmp_path: Path
    ) -> None:
        """Test get_years ignores non-year files."""
        data_root = tmp_path / "data" / "test_dataset"
        data_root.mkdir(parents=True)

        # Create mix of valid and invalid files
        (data_root / "2020.parquet").touch()
        (data_root / "2021.parquet").touch()
        (data_root / "README.md").touch()
        (data_root / "backup.parquet").touch()
        (data_root / "data.csv").touch()

        years = store.get_years("test_dataset")
        assert years == [2020, 2021]

    def test_get_years_single_year(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test get_years with single year."""
        store.write("test_dataset", sample_df, 2024)
        years = store.get_years("test_dataset")
        assert years == [2024]


# ============ delete tests ============


class TestDelete:
    """Tests for delete method."""

    def test_delete_existing_year(
        self, store: MockStore, sample_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test delete removes existing year partition."""
        store.write("test_dataset", sample_df, 2024)

        file_path = tmp_path / "data" / "test_dataset" / "2024.parquet"
        assert file_path.exists()

        result = store.delete("test_dataset", 2024)
        assert result is True
        assert not file_path.exists()

    @pytest.mark.parametrize(
        ("dataset", "year"),
        [
            ("test_dataset", 2024),
            ("nonexistent", 2024),
        ],
    )
    def test_delete_nonexistent(
        self, store: MockStore, dataset: str, year: int
    ) -> None:
        """Test delete with non-existent year or dataset."""
        result = store.delete(dataset, year)
        assert result is False

    def test_delete_leaves_other_years_intact(
        self, store_with_data: MockStore, tmp_path: Path
    ) -> None:
        """Test delete leaves other years intact."""
        result = store_with_data.delete("test_dataset", 2023)
        assert result is True

        file_2024 = tmp_path / "data" / "test_dataset" / "2024.parquet"
        assert file_2024.exists()

        file_2023 = tmp_path / "data" / "test_dataset" / "2023.parquet"
        assert not file_2023.exists()
        file_2023 = tmp_path / "data" / "test_dataset" / "2023.parquet"
        assert not file_2023.exists()


# ============ get_checksum tests ============


class TestGetChecksum:
    """Tests for get_checksum method."""

    def test_get_checksum_existing_file(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test get_checksum returns MD5 hash."""
        store.write("test_dataset", sample_df, 2024)

        checksum = store.get_checksum("test_dataset", 2024)
        # Verify it's a valid MD5 hash (32 hex characters)
        assert len(checksum) == 32
        int(checksum, 16)  # Verify it's valid hex

    def test_get_checksum_nonexistent_file(self, store: MockStore) -> None:
        """Test get_checksum with missing file (non-existent year or dataset)."""
        checksum = store.get_checksum("test_dataset", 2024)
        assert checksum == ""

        # Test with non-existent dataset
        checksum = store.get_checksum("nonexistent", 2024)
        assert checksum == ""


# ============ count tests ============


class TestCount:
    """Tests for count method."""

    def test_count_empty(self, store: MockStore) -> None:
        """Test count with no data."""
        count = store.count("test_dataset")
        assert count == 0

    def test_count_all_records(self, store_with_data: MockStore) -> None:
        """Test count returns total records."""
        # store_with_data has 8 records (4 in 2023, 4 in 2024)
        count = store_with_data.count("test_dataset")
        assert count == 8

    def test_count_filter_by_sids(self, store_with_data: MockStore) -> None:
        """Test count with SID filter."""
        count = store_with_data.count("test_dataset", sids=[1000001])
        assert count == 4  # 2 records per year

    def test_count_filter_by_date_range(self, store_with_data: MockStore) -> None:
        """Test count with date range filter."""
        count = store_with_data.count(
            "test_dataset", start_date="2024-01-02", end_date="2024-01-03"
        )
        # Both 2023 and 2024 partitions have the same dates
        # Each partition has 3 records matching the date range (2 on 01-02, 1 on 01-03)
        # Total: 6 records (3 from 2023 + 3 from 2024)
        assert count == 6

    def test_count_combined_filters(self, store_with_data: MockStore) -> None:
        """Test count with both SID and date filters."""
        count = store_with_data.count(
            "test_dataset",
            sids=[1000001],
            start_date="2024-01-02",
            end_date="2024-01-02",
        )
        assert count == 2  # 1 record in 2023 + 1 in 2024


# ============ get_date_range tests ============


class TestGetDateRange:
    """Tests for get_date_range method."""

    def test_get_date_range_empty(self, store: MockStore) -> None:
        """Test get_date_range with no data."""
        start, end = store.get_date_range("test_dataset")
        assert start is None
        assert end is None

    def test_get_date_range_single_year(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test get_date_range with single year."""
        store.write("test_dataset", sample_df, 2024)
        start, end = store.get_date_range("test_dataset")
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    def test_get_date_range_multiple_years(self, store_with_data: MockStore) -> None:
        """Test get_date_range across multiple partitions."""
        start, end = store_with_data.get_date_range("test_dataset")
        # Both years have same date range in sample data
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    def test_get_date_range_missing_trade_date_column(
        self, store: MockStore, tmp_path: Path
    ) -> None:
        """Test get_date_range when trade_date column is missing."""
        # Create parquet file without trade_date column
        data_root = tmp_path / "data" / "test_dataset"
        data_root.mkdir(parents=True)
        df_no_date = pl.DataFrame({"sid": [1, 2, 3], "close": [10.0, 11.0, 12.0]})
        df_no_date.write_parquet(data_root / "2024.parquet")

        # Should raise ColumnNotFoundError when trade_date column is missing
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            store.get_date_range("test_dataset")


# ============ list_sids tests ============


class TestListSids:
    """Tests for list_sids method."""

    def test_list_sids_empty(self, store: MockStore) -> None:
        """Test list_sids with no data."""
        sids = store.list_sids("test_dataset")
        assert sids == []

    def test_list_sids_returns_unique_sorted(self, store_with_data: MockStore) -> None:
        """Test list_sids returns sorted unique SIDs across all years."""
        sids = store_with_data.list_sids("test_dataset")
        assert sids == [1000001, 1000002]

    def test_list_sids_single_sid(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test list_sids with single security."""
        single_sid_df = sample_df.filter(pl.col("sid") == 1000001)
        store.write("test_dataset", single_sid_df, 2024)
        sids = store.list_sids("test_dataset")
        assert sids == [1000001]

    def test_list_sids_nonexistent_dataset(self, store: MockStore) -> None:
        """Test list_sids with non-existent dataset."""
        sids = store.list_sids("nonexistent")
        assert sids == []


# ============ Edge Cases and Integration Tests ============


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_data_root(self, tmp_path: Path) -> None:
        """Test behavior with empty data root."""
        empty_root = tmp_path / "empty"
        empty_root.mkdir()
        store = MockStore(empty_root)

        assert store.get_years("test") == []
        assert store.delete("test", 2024) is False
        assert store.get_checksum("test", 2024) == ""
        assert store.count("test") == 0
        assert store.get_date_range("test") == (None, None)
        assert store.list_sids("test") == []

    def test_path_operations_dont_create_files(
        self, store: MockStore, tmp_path: Path
    ) -> None:
        """Test that path operations don't create files."""
        data_root = tmp_path / "data"
        initial_files = list(data_root.rglob("*")) if data_root.exists() else []

        # These operations should not create files
        store._get_path("test", 2024)
        store._collect_paths("test", 2020, 2024)
        store.get_years("test")
        store.get_checksum("test", 2024)

        final_files = list(data_root.rglob("*")) if data_root.exists() else []
        assert len(final_files) == len(initial_files)


# ============ WriteResult tests ============


class TestWriteResult:
    """Tests for WriteResult dataclass."""

    def test_write_result_creation(self) -> None:
        """Test WriteResult can be created with all fields."""
        result = WriteResult(
            file_path="/data/test/2024.parquet",
            checksum="abc123",
            added=100,
            updated=50,
            skipped=10,
            is_merge=True,
        )
        assert result.file_path == "/data/test/2024.parquet"
        assert result.checksum == "abc123"
        assert result.added == 100
        assert result.updated == 50
        assert result.skipped == 10
        assert result.is_merge is True

    def test_write_result_with_zero_values(self) -> None:
        """Test WriteResult with zero values for new file."""
        result = WriteResult(
            file_path="/data/test/2024.parquet",
            checksum="def456",
            added=0,
            updated=0,
            skipped=0,
            is_merge=False,
        )
        assert result.added == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.is_merge is False

    def test_write_result_is_frozen(self) -> None:
        """Test WriteResult is frozen (immutable)."""
        result = WriteResult(
            file_path="/data/test/2024.parquet",
            checksum="abc123",
            added=100,
            updated=50,
            skipped=10,
            is_merge=True,
        )
        # frozen=True makes the dataclass immutable
        with pytest.raises(FrozenInstanceError):
            result.added = 200  # type: ignore[misc]


# ============ write tests ============


class TestWrite:
    """Tests for write method statistics."""

    def test_write_new_file_no_merge(self, store: MockStore) -> None:
        """Test write to new file (no merge)."""
        data: dict[str, list[Any]] = {
            "sid": [1000001, 1000002],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "close": [10.0, 11.0],
        }
        df = pl.DataFrame(data)

        result = store.write("test_dataset", df, 2024)

        assert result.is_merge is False
        assert result.added == 2
        assert result.updated == 0
        assert result.skipped == 0

    def test_write_merge_keep_first_no_overlap(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test write with KEEP_FIRST, no overlapping keys."""
        # Initial write
        store.write("test_dataset", sample_df, 2024)

        # New data with different keys
        new_data: dict[str, list[Any]] = {
            "sid": [1000003, 1000004],
            "trade_date": [date(2024, 1, 5), date(2024, 1, 6)],
            "close": [30.0, 31.0],
        }
        new_df = pl.DataFrame(new_data)

        result = store.write("test_dataset", new_df, 2024, OnDuplicate.KEEP_FIRST)

        assert result.is_merge is True
        assert result.added == 2  # 2 new rows added
        assert result.updated == 0
        assert result.skipped == 0

    def test_write_merge_keep_first_with_overlap(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test write with KEEP_FIRST, with overlapping keys."""
        # Initial write
        store.write("test_dataset", sample_df, 2024)

        # New data with overlapping keys
        new_data: dict[str, list[Any]] = {
            "sid": [1000001, 1000003],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 5)],
            "close": [99.0, 30.0],  # 1000001/2024-01-02 overlaps, should be skipped
        }
        new_df = pl.DataFrame(new_data)

        result = store.write("test_dataset", new_df, 2024, OnDuplicate.KEEP_FIRST)

        assert result.is_merge is True
        assert result.added == 1  # Only 1000003 added
        assert result.updated == 0
        assert result.skipped == 0

    def test_write_merge_keep_last_with_overlap(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test write with KEEP_LAST, with overlapping keys."""
        # Initial write
        store.write("test_dataset", sample_df, 2024)

        # New data with overlapping keys
        new_data: dict[str, list[Any]] = {
            "sid": [1000001, 1000003],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 5)],
            "close": [99.0, 30.0],  # 1000001/2024-01-02 overlaps, should update
        }
        new_df = pl.DataFrame(new_data)

        result = store.write("test_dataset", new_df, 2024, OnDuplicate.KEEP_LAST)

        assert result.is_merge is True
        assert result.added == 1  # Only 1000003 added
        assert result.updated == 1  # 1000001 updated
        assert result.skipped == 0

    def test_write_merge_keep_last_with_batch_duplicates(
        self, store: MockStore, sample_df: pl.DataFrame
    ) -> None:
        """Test write with KEEP_LAST, batch has internal duplicates."""
        # Initial write
        store.write("test_dataset", sample_df, 2024)

        # New data with internal duplicates
        new_data: dict[str, list[Any]] = {
            "sid": [1000001, 1000001, 1000003],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 2),
                date(2024, 1, 5),
            ],  # 1000001/2024-01-02 duplicated
            "close": [99.0, 88.0, 30.0],
        }
        new_df = pl.DataFrame(new_data)

        result = store.write("test_dataset", new_df, 2024, OnDuplicate.KEEP_LAST)

        assert result.is_merge is True
        assert result.added == 1  # Only 1000003 added
        assert result.updated == 1  # 1000001 updated (batch dedup keeps first)
        assert result.skipped == 0

    def test_write_empty_dataframe(self, store: MockStore) -> None:
        """Test write with empty DataFrame."""
        empty_df = pl.DataFrame(
            schema={"sid": pl.Int32, "trade_date": pl.Date, "close": pl.Float64}
        )

        result = store.write("test_dataset", empty_df, 2024)

        assert result.file_path == ""
        assert result.checksum == ""
        assert result.added == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.is_merge is False
