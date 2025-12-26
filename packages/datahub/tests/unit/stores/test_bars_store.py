"""Tests for BarsStore."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from ditto_datahub.stores.bars_store import BarsStore


class TestBarsStore:
    """Test cases for BarsStore."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_read_returns_empty_dataframe_for_nonexistent_dataset(self) -> None:
        """Test read returns empty DataFrame when dataset doesn't exist."""
        result = self.store.read(
            "nonexistent", start_date="2020-01-01", end_date="2020-12-31"
        )
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    def test_write_and_read_bars(self) -> None:
        """Test write and read operations."""
        # Create test data
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        # Write data
        file_path, checksum = self.store.write("market_daily", test_df, 2024)

        assert file_path is not None
        assert checksum is not None
        assert Path(file_path).exists()

        # Read data back
        result = self.store.read(
            "market_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        assert set(result["sid"].to_list()) == {100000001, 100000002}

    def test_write_merge_with_existing_data(self) -> None:
        """Test write merges with existing data."""
        # Initial data
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        self.store.write("market_daily", df1, 2024)

        # Additional data with overlap
        df2 = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.5, 11.0],
                "high": [12.5, 13.0],
                "low": [9.5, 10.0],
                "close": [11.5, 12.0],
                "volume": [1500, 2000],
            }
        )

        self.store.write("market_daily", df2, 2024)

        # Read back - should have unique sid/date pairs
        result = self.store.read(
            "market_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        # The overlapped record should be updated with new data
        record_100000001 = result.filter(pl.col("sid") == 100000001)
        assert len(record_100000001) == 1
        assert record_100000001["close"][0] == 11.5  # Updated value

    def test_get_years_returns_empty_list_for_nonexistent_dataset(self) -> None:
        """Test get_years returns empty list when dataset doesn't exist."""
        years = self.store.get_years("nonexistent")
        assert years == []

    def test_get_years_returns_available_years(self) -> None:
        """Test get_years returns list of available years."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        self.store.write("market_daily", test_df, 2024)
        self.store.write("market_daily", test_df, 2023)

        years = self.store.get_years("market_daily")
        assert years == [2023, 2024]

    def test_count_returns_zero_for_nonexistent_dataset(self) -> None:
        """Test count returns zero when dataset doesn't exist."""
        count = self.store.count("nonexistent")
        assert count == 0

    def test_count_returns_record_count(self) -> None:
        """Test count returns correct record count."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002, 100000003],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [1000, 2000, 3000],
            }
        )

        self.store.write("market_daily", test_df, 2024)

        count = self.store.count("market_daily")
        assert count == 3

    def test_read_filters_by_sids(self) -> None:
        """Test read filters by security IDs."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002, 100000003],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 1)],
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [1000, 2000, 3000],
            }
        )

        self.store.write("market_daily", test_df, 2024)

        result = self.store.read("market_daily", sids=[100000001, 100000002])
        assert len(result) == 2
        assert set(result["sid"].to_list()) == {100000001, 100000002}

    def test_delete_removes_year_partition(self) -> None:
        """Test delete removes year partition file."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        self.store.write("market_daily", test_df, 2024)

        # Delete existing partition
        result = self.store.delete("market_daily", 2024)
        assert result is True

        # Try to delete non-existent partition
        result = self.store.delete("market_daily", 2024)
        assert result is False


class TestBarsStoreRefactoredHelpers:
    """Tests for refactored helper methods in BarsStore."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_ensure_dataset_dir_creates_directory(self) -> None:
        """Test _ensure_dataset_dir creates dataset directory."""
        dataset = "test_dataset"
        result_path = self.store._ensure_dataset_dir(dataset)

        assert result_path == Path(self.temp_dir.name) / dataset
        assert result_path.exists()
        assert result_path.is_dir()

    def test_ensure_dataset_dir_is_idempotent(self) -> None:
        """Test _ensure_dataset_dir can be called multiple times safely."""
        dataset = "test_dataset"
        path1 = self.store._ensure_dataset_dir(dataset)
        path2 = self.store._ensure_dataset_dir(dataset)

        assert path1 == path2
        assert path1.exists()

    def test_merge_with_existing_returns_new_data_when_no_file(self) -> None:
        """Test _merge_with_existing returns new data when file doesn't exist."""
        new_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        non_existent_path = Path(self.temp_dir.name) / "nonexistent.parquet"

        result = self.store._merge_with_existing(new_df, non_existent_path)

        # Should return new data as-is
        assert len(result) == 1
        assert result["sid"][0] == 100000001

    def test_merge_with_existing_merges_when_file_exists(self) -> None:
        """Test _merge_with_existing merges data when file exists."""
        # First write initial data
        initial_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("market_daily", initial_df, 2024)

        # Create new data with overlap
        new_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.5, 11.0],
                "high": [12.5, 13.0],
                "low": [9.5, 10.0],
                "close": [11.5, 12.0],
                "volume": [1500, 2000],
            }
        )

        file_path = self.store._get_path("market_daily", 2024)
        result = self.store._merge_with_existing(new_df, file_path)

        # Should have 2 unique records
        assert len(result) == 2
        # The overlapped record should be updated
        record = result.filter(pl.col("sid") == 100000001)
        assert record["close"][0] == 11.5

    def test_prepare_for_write_normalizes_dates(self) -> None:
        """Test _prepare_for_write normalizes date types."""
        # Create DataFrame with string dates
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        result = self.store._prepare_for_write(df)

        # Dates should be Date type
        assert result["trade_date"].dtype == pl.Date
        # Data should be sorted by trade_date, sid
        # Use row() or proper indexing for single row access
        first_row = result.row(0)
        assert first_row[1] == date(2024, 1, 1)

    def test_prepare_for_write_sorts_data(self) -> None:
        """Test _prepare_for_write sorts data correctly."""
        # Create intentionally unsorted data
        df = pl.DataFrame(
            {
                "sid": [100000002, 100000001, 100000002],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 1), date(2024, 1, 1)],
                "open": [11.0, 10.0, 11.0],
                "high": [13.0, 12.0, 13.0],
                "low": [10.0, 9.0, 10.0],
                "close": [12.0, 11.0, 12.0],
                "volume": [2000, 1000, 2000],
            }
        )

        result = self.store._prepare_for_write(df)

        # Should be sorted by trade_date, then sid
        # First row should be 2024-01-01, sid=100000001
        first_row = result.row(0)
        assert first_row[1] == date(2024, 1, 1)
        assert first_row[0] == 100000001
        # Last row should be 2024-01-02, sid=100000002
        last_row = result.row(2)
        assert last_row[1] == date(2024, 1, 2)
        assert last_row[0] == 100000002
