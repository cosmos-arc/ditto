"""Tests for AdjFactorStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_datahub.stores.adj_factor_store import AdjFactorStore


class TestAdjFactorStore:
    """Test suite for AdjFactorStore."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def store(self, data_root: Path) -> AdjFactorStore:
        """Create AdjFactorStore instance."""
        return AdjFactorStore(data_root)

    @pytest.fixture
    def sample_df(self) -> pl.DataFrame:
        """Create sample adjustment factor data."""
        data: dict[str, list[Any]] = {
            "sid": [100000001, 100000001, 100000001, 100000002],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "adj_factor": [1.0, 1.0, 0.95, 1.0],
        }
        return pl.DataFrame(data)

    # ============ _get_path tests ============

    def test_get_path(self, store: AdjFactorStore) -> None:
        """Test _get_path generates correct file path."""
        path = store._get_path("adj_factor", 2024)
        expected = store._data_root / "adj_factor" / "2024.parquet"
        assert path == expected

    # ============ _collect_paths tests ============

    def test_collect_paths_empty(self, store: AdjFactorStore) -> None:
        """Test _collect_paths with non-existent dataset."""
        paths = store._collect_paths("adj_factor", 2020, 2024)
        assert paths == []

    def test_collect_paths_partial(self, store: AdjFactorStore, tmp_path: Path) -> None:
        """Test _collect_paths with some years missing."""
        data_root = tmp_path / "data" / "adj_factor"
        data_root.mkdir(parents=True)

        # Create only 2021, 2023, 2024 files
        (data_root / "2021.parquet").touch()
        (data_root / "2023.parquet").touch()
        (data_root / "2024.parquet").touch()

        paths = store._collect_paths("adj_factor", 2020, 2024)
        assert len(paths) == 3
        # Extract years from path stems
        years = [int(p.stem) for p in paths]
        assert years == [2021, 2023, 2024]

    # ============ read tests ============

    def test_read_empty(self, store: AdjFactorStore) -> None:
        """Test read with no data."""
        df = store.read("adj_factor")
        assert len(df) == 0

    def test_read_no_filters(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test read without filters."""
        store.write("adj_factor", sample_df, 2024)
        df = store.read("adj_factor")
        assert len(df) == 4
        assert "sid" in df.columns
        assert "trade_date" in df.columns
        assert "adj_factor" in df.columns

    def test_read_filter_by_sids(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test read filtered by security IDs."""
        store.write("adj_factor", sample_df, 2024)
        df = store.read("adj_factor", sids=[100000001])
        assert len(df) == 3
        assert df["sid"].unique().to_list() == [100000001]

    def test_read_filter_by_date_range(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test read filtered by date range."""
        store.write("adj_factor", sample_df, 2024)
        df = store.read("adj_factor", start_date="2024-01-02", end_date="2024-01-03")
        # 2024-01-02 has 2 records, 2024-01-03 has 1 record = 3 total
        assert len(df) == 3

    def test_read_multiple_years(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test read spanning multiple year partitions."""
        # Create data with 2023 dates for the 2023 partition
        df_2023 = sample_df.with_columns(
            pl.col("trade_date").map_elements(
                lambda d: d.replace(year=2023), return_dtype=pl.Date
            )
        )
        store.write("adj_factor", df_2023, 2023)
        store.write("adj_factor", sample_df, 2024)

        df = store.read("adj_factor", start_date="2023-01-01", end_date="2024-12-31")
        assert len(df) == 8  # 4 records per year

    # ============ write tests ============

    def test_write_new_file(
        self, store: AdjFactorStore, sample_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test write creates new file."""
        file_path, checksum = store.write("adj_factor", sample_df, 2024)

        assert file_path == str(tmp_path / "data" / "adj_factor" / "2024.parquet")
        assert Path(file_path).exists()
        assert len(checksum) == 32  # MD5 hex string

    def test_write_merge_with_existing(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test write merges with existing data."""
        # Write initial data
        store.write("adj_factor", sample_df, 2024)

        # Write overlapping new data
        new_data = pl.DataFrame(
            {
                "sid": [100000001, 100000003],
                "trade_date": [date(2024, 1, 4), date(2024, 1, 5)],
                "adj_factor": [0.92, 1.0],
            }
        )
        store.write("adj_factor", new_data, 2024)

        # Verify deduplication (new adj_factor overwrites)
        df = store.read("adj_factor")
        assert len(df) == 5  # 4 original + 1 new (100000001/2024-01-04 updated)

        # Verify new value was applied
        record = df.filter(
            (pl.col("sid") == 100000001) & (pl.col("trade_date") == date(2024, 1, 4))
        )
        assert record["adj_factor"][0] == 0.92

    def test_write_overwrite_existing(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test write overwrites existing records with same key."""
        store.write("adj_factor", sample_df, 2024)

        # Write same date/sid with different adj_factor
        updated = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 3)],
                "adj_factor": [0.85],
            }
        )
        store.write("adj_factor", updated, 2024)

        df = store.read("adj_factor", sids=[100000001])
        record = df.filter(pl.col("trade_date") == date(2024, 1, 3))
        assert record["adj_factor"][0] == 0.85

    def test_write_creates_directory(
        self, store: AdjFactorStore, sample_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "adj_factor"
        assert not dataset_dir.exists()

        store.write("adj_factor", sample_df, 2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    # ============ get_years tests ============

    def test_get_years_empty(self, store: AdjFactorStore) -> None:
        """Test get_years with no data."""
        years = store.get_years("adj_factor")
        assert years == []

    def test_get_years(self, store: AdjFactorStore, sample_df: pl.DataFrame) -> None:
        """Test get_years returns available years."""
        store.write("adj_factor", sample_df, 2022)
        store.write("adj_factor", sample_df, 2024)
        store.write("adj_factor", sample_df, 2023)

        years = store.get_years("adj_factor")
        assert years == [2022, 2023, 2024]

    def test_get_years_ignores_invalid_files(
        self, store: AdjFactorStore, tmp_path: Path
    ) -> None:
        """Test get_years ignores non-year files."""
        data_root = tmp_path / "data" / "adj_factor"
        data_root.mkdir(parents=True)

        (data_root / "2020.parquet").touch()
        (data_root / "2021.parquet").touch()
        (data_root / "README.md").touch()
        (data_root / "backup.parquet").touch()

        years = store.get_years("adj_factor")
        assert years == [2020, 2021]

    # ============ delete tests ============

    def test_delete_year(
        self, store: AdjFactorStore, sample_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test delete removes year partition."""
        store.write("adj_factor", sample_df, 2024)

        result = store.delete("adj_factor", 2024)
        assert result is True

        file_path = tmp_path / "data" / "adj_factor" / "2024.parquet"
        assert not file_path.exists()

    def test_delete_nonexistent_year(self, store: AdjFactorStore) -> None:
        """Test delete with non-existent year."""
        result = store.delete("adj_factor", 2024)
        assert result is False

    # ============ get_checksum tests ============

    def test_get_checksum(self, store: AdjFactorStore, sample_df: pl.DataFrame) -> None:
        """Test get_checksum returns MD5 hash."""
        store.write("adj_factor", sample_df, 2024)

        checksum = store.get_checksum("adj_factor", 2024)
        assert len(checksum) == 32
        # Verify it's a valid hex string
        int(checksum, 16)

    def test_get_checksum_missing_file(self, store: AdjFactorStore) -> None:
        """Test get_checksum with missing file."""
        checksum = store.get_checksum("adj_factor", 2024)
        assert checksum == ""

    # ============ count tests ============

    def test_count_empty(self, store: AdjFactorStore) -> None:
        """Test count with no data."""
        count = store.count("adj_factor")
        assert count == 0

    def test_count(self, store: AdjFactorStore, sample_df: pl.DataFrame) -> None:
        """Test count returns total records."""
        store.write("adj_factor", sample_df, 2024)
        count = store.count("adj_factor")
        assert count == 4

    def test_count_with_filters(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test count with filters applied."""
        store.write("adj_factor", sample_df, 2024)
        count = store.count("adj_factor", sids=[100000001])
        assert count == 3

    # ============ get_date_range tests ============

    def test_get_date_range_empty(self, store: AdjFactorStore) -> None:
        """Test get_date_range with no data."""
        start, end = store.get_date_range("adj_factor")
        assert start is None
        assert end is None

    def test_get_date_range(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test get_date_range returns min/max dates."""
        store.write("adj_factor", sample_df, 2024)
        start, end = store.get_date_range("adj_factor")
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    def test_get_date_range_multiple_years(
        self, store: AdjFactorStore, sample_df: pl.DataFrame
    ) -> None:
        """Test get_date_range across multiple partitions."""
        store.write("adj_factor", sample_df, 2023)
        store.write("adj_factor", sample_df, 2024)

        start, end = store.get_date_range("adj_factor")
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    # ============ list_sids tests ============

    def test_list_sids_empty(self, store: AdjFactorStore) -> None:
        """Test list_sids with no data."""
        sids = store.list_sids("adj_factor")
        assert sids == []

    def test_list_sids(self, store: AdjFactorStore, sample_df: pl.DataFrame) -> None:
        """Test list_sids returns unique security IDs."""
        store.write("adj_factor", sample_df, 2024)
        sids = store.list_sids("adj_factor")
        assert sids == [100000001, 100000002]

    def test_write_maintains_sid_and_date_sorting(
        self, store: AdjFactorStore, tmp_path: Path
    ) -> None:
        """Test that write ensures data is sorted by sid and trade_date."""
        # Arrange: Create intentionally unsorted data
        unsorted_df = pl.DataFrame(
            {
                "sid": [100000002, 100000001, 100000002, 100000001],
                "trade_date": [
                    date(2024, 1, 5),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "adj_factor": [1.0, 1.0, 0.95, 1.0],
            }
        )

        # Act: Write the data
        store.write("adj_factor", unsorted_df, 2024)

        # Assert: Read back and verify it's sorted by (sid, trade_date)
        result = store.read("adj_factor")

        # Check that rows are in the correct order
        for i in range(len(result) - 1):
            current_sid = result["sid"][i]
            next_sid = result["sid"][i + 1]
            current_date = result["trade_date"][i]
            next_date = result["trade_date"][i + 1]

            # Either current sid < next sid, or same sid with current date <= next date
            assert current_sid < next_sid or (
                current_sid == next_sid and current_date <= next_date
            ), (
                f"Row {i} not sorted: ({current_sid}, {current_date}) "
                f"before ({next_sid}, {next_date})"
            )


class TestDateNormalization:
    """Tests for date type normalization in write."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def store(self, data_root: Path) -> AdjFactorStore:
        """Create AdjFactorStore instance."""
        return AdjFactorStore(data_root)

    def test_write_with_string_trade_date(self, store: AdjFactorStore) -> None:
        """Test write normalizes string trade_date to Date type."""
        # Create DataFrame with string trade_date
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000001],
                "trade_date": ["2024-01-02", "2024-01-03"],
                "adj_factor": [1.0, 0.95],
            }
        )

        # Write should normalize string dates to Date type
        _file_path, _checksum = store.write("adj_factor", df, 2024)

        # Read back and verify dates are Date type
        result = store.read("adj_factor")
        assert result["trade_date"].dtype == pl.Date
        assert len(result) == 2

    def test_write_with_date_trade_date(self, store: AdjFactorStore) -> None:
        """Test write preserves Date type trade_date."""
        # Create DataFrame with Date trade_date
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000001],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "adj_factor": [1.0, 0.95],
            }
        )

        # Write should preserve Date type
        _file_path, _checksum = store.write("adj_factor", df, 2024)

        # Read back and verify dates are Date type
        result = store.read("adj_factor")
        assert result["trade_date"].dtype == pl.Date
        assert len(result) == 2

    def test_write_with_invalid_date_format_raises_error(
        self, store: AdjFactorStore
    ) -> None:
        """Test write raises error for invalid date format."""
        # Create DataFrame with invalid date format
        df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": ["not-a-date"],
                "adj_factor": [1.0],
            }
        )

        # Should raise InvalidOperationError for invalid date format
        with pytest.raises(pl.InvalidOperationError):
            store.write("adj_factor", df, 2024)


class TestSortingEnhanced:
    """排序验证增强测试."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def store(self, data_root: Path) -> AdjFactorStore:
        """Create AdjFactorStore instance."""
        return AdjFactorStore(data_root)

    def test_sorting_across_year_partitions(self, store: AdjFactorStore) -> None:
        """跨年分区数据的排序正确性."""
        # Write 2023 data
        dates_2023 = [date(2023, 12, 31), date(2023, 12, 29), date(2023, 12, 30)]
        df_2023 = pl.DataFrame(
            {
                "sid": [100000002, 100000001, 100000001],
                "trade_date": dates_2023,
                "adj_factor": [1.0, 1.0, 0.98],
            }
        )
        store.write("adj_factor", df_2023, 2023)

        # Write 2024 data
        dates_2024 = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 1)]
        df_2024 = pl.DataFrame(
            {
                "sid": [100000001, 100000001, 100000002],
                "trade_date": dates_2024,
                "adj_factor": [0.95, 0.95, 1.0],
            }
        )
        store.write("adj_factor", df_2024, 2024)

        # Read across both years
        result = store.read(
            "adj_factor",
            start_date="2023-12-29",
            end_date="2024-01-03",
        )

        # Verify sorting: (sid, trade_date)
        assert len(result) == 6
        # Expected order:
        # 100000001, 2023-12-29
        # 100000001, 2023-12-30
        # 100000001, 2024-01-02
        # 100000001, 2024-01-03
        # 100000002, 2023-12-31
        # 100000002, 2024-01-01
        for i in range(len(result) - 1):
            current_sid = result["sid"][i]
            next_sid = result["sid"][i + 1]
            current_date = result["trade_date"][i]
            next_date = result["trade_date"][i + 1]

            # Verify sorting order
            assert current_sid < next_sid or (
                current_sid == next_sid and current_date <= next_date
            ), (
                f"Row {i} not sorted: ({current_sid}, {current_date}) before "
                f"({next_sid}, {next_date})"
            )

    def test_sorting_with_duplicate_keys_uses_last(self, store: AdjFactorStore) -> None:
        """重复键的正确处理（keep="last"）。"""
        # Write initial data
        df1 = pl.DataFrame(
            {
                "sid": [100000001, 100000001, 100000002],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 2)],
                "adj_factor": [1.0, 0.95, 1.0],
            }
        )
        store.write("adj_factor", df1, 2024)

        # Write overlapping data with updated values
        df2 = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 3), date(2024, 1, 2)],
                "adj_factor": [0.92, 0.88],  # Updated values
            }
        )
        store.write("adj_factor", df2, 2024)

        # Read back and verify keep="last" behavior
        result = store.read("adj_factor")

        # Check that 100000001/2024-01-03 uses the last value (0.92, not 0.95)
        record = result.filter(
            (pl.col("sid") == 100000001) & (pl.col("trade_date") == date(2024, 1, 3))
        )
        assert len(record) == 1
        assert record["adj_factor"][0] == 0.92

        # Check that 100000002/2024-01-02 uses the last value (0.88, not 1.0)
        record = result.filter(
            (pl.col("sid") == 100000002) & (pl.col("trade_date") == date(2024, 1, 2))
        )
        assert len(record) == 1
        assert record["adj_factor"][0] == 0.88

    def test_sorting_order_is_stable_after_merge(self, store: AdjFactorStore) -> None:
        """合并后排序顺序的稳定性."""
        # Write first batch
        df1 = pl.DataFrame(
            {
                "sid": [100000001, 100000002, 100000003],
                "trade_date": [date(2024, 1, 5), date(2024, 1, 3), date(2024, 1, 1)],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )
        store.write("adj_factor", df1, 2024)

        # Write second batch (overlap and new)
        df2 = pl.DataFrame(
            {
                "sid": [100000002, 100000003, 100000004],
                "trade_date": [date(2024, 1, 3), date(2024, 1, 2), date(2024, 1, 4)],
                "adj_factor": [0.95, 0.95, 1.0],
            }
        )
        store.write("adj_factor", df2, 2024)

        # Read back and verify stable sorting
        result = store.read("adj_factor")

        # Expected sorted order:
        # 100000001, 2024-01-05, 1.0
        # 100000002, 2024-01-03, 0.95 (updated)
        # 100000003, 2024-01-01, 1.0
        # 100000003, 2024-01-02, 0.95 (new)
        # 100000004, 2024-01-04, 1.0 (new)
        expected_pairs = [
            (100000001, date(2024, 1, 5)),
            (100000002, date(2024, 1, 3)),
            (100000003, date(2024, 1, 1)),
            (100000003, date(2024, 1, 2)),
            (100000004, date(2024, 1, 4)),
        ]

        assert len(result) == len(expected_pairs)
        for i, (expected_sid, expected_date) in enumerate(expected_pairs):
            assert result["sid"][i] == expected_sid
            assert result["trade_date"][i] == expected_date
