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
