"""Integration tests for BarsStore (Parquet seam)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.stores.bars_store import BarsStore
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestBarsStoreIntegration:
    """Tests for BarsStore integration with Parquet files."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def pool(self) -> SQLitePool:
        """Create in-memory SQLite pool (required by infrastructure)."""
        return SQLitePool(db_path=":memory:")

    @pytest.fixture
    def store(self, data_root: Path, pool: SQLitePool) -> BarsStore:
        """Create BarsStore instance."""
        return BarsStore(data_root=data_root)

    @pytest.fixture
    def sample_bars_df(self) -> pl.DataFrame:
        """Create sample bars DataFrame."""
        return pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_001],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "open": [10.0, 10.5, 11.0],
                "high": [10.5, 11.0, 11.5],
                "low": [9.5, 10.0, 10.5],
                "close": [10.0, 10.5, 11.0],
                "volume": [1000, 1500, 2000],
                "amount": [10000.0, 15000.0, 20000.0],
            }
        )

    def test_write_creates_parquet_file(
        self, store: BarsStore, data_root: Path, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test that write creates Parquet file."""
        result = store.write("stock_daily", sample_bars_df, year=2024)

        # Verify file was created
        file_path = data_root / "stock_daily" / "2024.parquet"
        assert file_path.exists()

        # Verify result
        assert result.added == 3
        assert result.updated == 0
        assert result.file_path == str(file_path)
        assert len(result.checksum) > 0

    def test_write_read_roundtrip(
        self, store: BarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write and read roundtrip."""
        # Write
        store.write("stock_daily", sample_bars_df, year=2024)

        # Read
        result = store.read("stock_daily")

        # Sort by trade_date for consistent ordering (Parquet doesn't guarantee order)
        result = result.sort("trade_date")

        assert len(result) == 3
        assert result["sid"].to_list() == [1_000_001, 1_000_001, 1_000_001]
        assert result["close"].to_list() == [10.0, 10.5, 11.0]

    def test_read_with_sid_filter(
        self, store: BarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test reading with SID filter."""
        # Create DataFrame with multiple SIDs
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_002, 1_000_003],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                ],
                "open": [10.0, 20.0, 30.0],
                "high": [10.5, 20.5, 30.5],
                "low": [9.5, 19.5, 29.5],
                "close": [10.0, 20.0, 30.0],
                "volume": [1000, 1000, 1000],
                "amount": [10000.0, 20000.0, 30000.0],
            }
        )

        store.write("stock_daily", df, year=2024)

        # Read with SID filter
        result = store.read("stock_daily", sids=[1_000_001, 1_000_002])

        assert len(result) == 2
        assert set(result["sid"].to_list()) == {1_000_001, 1_000_002}

    def test_read_with_date_filter(
        self, store: BarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test reading with date filter."""
        store.write("stock_daily", sample_bars_df, year=2024)

        # Read with date range
        result = store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-02"
        )

        assert len(result) == 2
        assert result["trade_date"].max() == date(2024, 1, 2)

    def test_read_empty_dataset(self, store: BarsStore) -> None:
        """Test reading from non-existent dataset."""
        result = store.read("nonexistent_dataset")
        assert result.is_empty()

    def test_write_with_keep_last_duplicate_strategy(self, store: BarsStore) -> None:
        """Test write with OnDuplicate.KEEP_LAST."""
        # First write
        df1 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.5],
                "close": [10.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )
        store.write("stock_daily", df1, year=2024)

        # Second write with KEEP_LAST (should overwrite)
        df2 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.5],  # Different value
                "high": [11.0],
                "low": [10.0],
                "close": [10.5],
                "volume": [1500],
                "amount": [15000.0],
            }
        )
        result = store.write(
            "stock_daily", df2, year=2024, on_duplicate=OnDuplicate.KEEP_LAST
        )

        assert result.added == 0
        assert result.updated == 1

        # Verify new value is kept
        read_result = store.read("stock_daily")
        assert read_result["open"][0] == 10.5

    def test_write_with_error_duplicate_strategy_raises(self, store: BarsStore) -> None:
        """Test write with OnDuplicate.ERROR raises on duplicate."""
        # First write
        df1 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.5],
                "close": [10.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )
        store.write("stock_daily", df1, year=2024)

        # Second write with ERROR (should raise)
        df2 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.5],
                "high": [11.0],
                "low": [10.0],
                "close": [10.5],
                "volume": [1500],
                "amount": [15000.0],
            }
        )

        with pytest.raises(ValueError) as exc_info:
            store.write("stock_daily", df2, year=2024, on_duplicate=OnDuplicate.ERROR)

        assert "Duplicate data" in str(exc_info.value)

    def test_write_multiple_datasets(self, store: BarsStore) -> None:
        """Test writing to multiple datasets."""
        stock_df = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.5],
                "close": [10.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )

        etf_df = pl.DataFrame(
            {
                "sid": [2_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [5.0],
                "high": [5.5],
                "low": [4.5],
                "close": [5.0],
                "volume": [500],
                "amount": [5000.0],
            }
        )

        store.write("stock_daily", stock_df, year=2024)
        store.write("etf_daily", etf_df, year=2024)

        # Verify both datasets exist
        stock_result = store.read("stock_daily")
        etf_result = store.read("etf_daily")

        assert len(stock_result) == 1
        assert len(etf_result) == 1
        assert stock_result["sid"][0] == 1_000_001
        assert etf_result["sid"][0] == 2_000_001

    def test_write_string_date_columns(
        self, store: BarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test that string date columns are converted to Date type."""
        # Convert date to string
        df = sample_bars_df.with_columns(pl.col("trade_date").cast(pl.String))

        store.write("stock_daily", df, year=2024)

        # Read back - dates should be Date type
        result = store.read("stock_daily")
        assert result["trade_date"].dtype == pl.Date

    def test_read_preserves_sort_order(
        self, store: BarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test that data can be sorted by trade_date and sid after read."""
        # Create unsorted data
        df = pl.DataFrame(
            {
                "sid": [1_000_002, 1_000_001, 1_000_002, 1_000_001],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                ],
                "open": [20.0, 10.5, 20.0, 10.0],
                "high": [20.5, 11.0, 20.5, 10.5],
                "low": [19.5, 10.0, 19.5, 9.5],
                "close": [20.0, 10.5, 20.0, 10.0],
                "volume": [1000, 1500, 1000, 1000],
                "amount": [20000.0, 15000.0, 20000.0, 10000.0],
            }
        )

        store.write("stock_daily", df, year=2024)

        # Read data and sort by trade_date, sid for consistent ordering
        result = store.read("stock_daily").sort(["trade_date", "sid"])

        # Verify sorting
        assert result[0, "sid"] == 1_000_001
        assert result[0, "trade_date"] == date(2024, 1, 1)
        assert result[1, "sid"] == 1_000_002
        assert result[1, "trade_date"] == date(2024, 1, 1)

    def test_get_years(self, store: BarsStore) -> None:
        """Test getting available years."""
        for year in [2022, 2023, 2024]:
            df = pl.DataFrame(
                {
                    "sid": [1_000_001],
                    "trade_date": [date(year, 1, 1)],
                    "open": [10.0],
                    "high": [10.5],
                    "low": [9.5],
                    "close": [10.0],
                    "volume": [1000],
                    "amount": [10000.0],
                }
            )
            store.write("stock_daily", df, year=year)

        years = store.get_years("stock_daily")
        assert years == [2022, 2023, 2024]

    def test_count(self, store: BarsStore, sample_bars_df: pl.DataFrame) -> None:
        """Test counting records."""
        store.write("stock_daily", sample_bars_df, year=2024)

        # Count all
        count = store.count("stock_daily")
        assert count == 3

        # Count with date filter
        count_filtered = store.count(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-02"
        )
        assert count_filtered == 2

    def test_list_sids(self, store: BarsStore) -> None:
        """Test listing unique SIDs."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_002, 1_000_002],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "open": [10.0, 10.5, 20.0, 20.5],
                "high": [10.5, 11.0, 20.5, 21.0],
                "low": [9.5, 10.0, 19.5, 20.0],
                "close": [10.0, 10.5, 20.0, 20.5],
                "volume": [1000, 1500, 1000, 1500],
                "amount": [10000.0, 15000.0, 20000.0, 25000.0],
            }
        )

        store.write("stock_daily", df, year=2024)

        sids = store.list_sids("stock_daily")
        assert sids == [1_000_001, 1_000_002]

    def test_delete(self, store: BarsStore, data_root: Path) -> None:
        """Test deleting year partition."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.5],
                "close": [10.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )

        store.write("stock_daily", df, year=2024)

        # Delete
        deleted = store.delete("stock_daily", 2024)
        assert deleted is True

        # Verify file is gone
        file_path = data_root / "stock_daily" / "2024.parquet"
        assert not file_path.exists()

    def test_read_multiple_years(self, store: BarsStore) -> None:
        """Test reading across multiple year partitions."""
        # Write data across 2 years
        for year in [2023, 2024]:
            df = pl.DataFrame(
                {
                    "sid": [1_000_001],
                    "trade_date": [date(year, 6, 1)],
                    "open": [10.0],
                    "high": [10.5],
                    "low": [9.5],
                    "close": [10.0],
                    "volume": [1000],
                    "amount": [10000.0],
                }
            )
            store.write("stock_daily", df, year=year)

        # Read across both years
        result = store.read(
            "stock_daily", start_date="2023-01-01", end_date="2024-12-31"
        )

        assert len(result) == 2

    def test_get_date_range(
        self, store: BarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test getting date range."""
        store.write("stock_daily", sample_bars_df, year=2024)

        start_date, end_date = store.get_date_range("stock_daily")
        assert start_date == "2024-01-01"
        assert end_date == "2024-01-03"

    def test_write_etf_dataset(self, store: BarsStore) -> None:
        """Test writing ETF dataset."""
        df = pl.DataFrame(
            {
                "sid": [2_000_001, 2_000_001],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [5.0, 5.1],
                "high": [5.1, 5.2],
                "low": [4.9, 5.0],
                "close": [5.0, 5.1],
                "volume": [1000, 1500],
                "amount": [5000.0, 7500.0],
            }
        )

        store.write("etf_daily", df, year=2024)

        # Read back
        result = store.read("etf_daily")
        assert len(result) == 2
        assert result["sid"][0] == 2_000_001

    def test_merge_preserves_all_columns(self, store: BarsStore) -> None:
        """Test that merge preserves all DataFrame columns."""
        # First write with some columns
        df1 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.5],
                "close": [10.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )
        store.write("stock_daily", df1, year=2024)

        # Add new record with same columns
        df2 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.5],
                "high": [11.0],
                "low": [10.0],
                "close": [10.5],
                "volume": [1500],
                "amount": [15000.0],
            }
        )
        store.write("stock_daily", df2, year=2024)

        # Read back - all columns should exist
        result = store.read("stock_daily")
        assert len(result) == 2
        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns
        assert "amount" in result.columns

    def test_read_corrupted_parquet_file_raises_error(
        self, store: BarsStore, data_root: Path
    ) -> None:
        """Test reading corrupted parquet file raises exception."""
        # Create dataset directory
        dataset_dir = data_root / "stock_daily"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        # Write invalid/corrupted parquet file
        corrupted_file = dataset_dir / "2024.parquet"
        corrupted_file.write_text("This is not a valid parquet file")

        # Reading should raise an exception
        # polars.ParquetError or similar for corrupted parquet files
        with pytest.raises(  # noqa: B017
            Exception
        ):  # Could be more specific but polars doesn't expose specific error types
            store.read("stock_daily")
