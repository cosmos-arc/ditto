"""Tests for IndexBarsStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.stores.market.index.bars import IndexBarsStore


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> IndexBarsStore:
    """Create IndexBarsStore instance."""
    return IndexBarsStore(data_root)


@pytest.fixture
def sample_bars_df() -> pl.DataFrame:
    """Create sample Index daily bars DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1600001, 1600001, 1600001, 1600002],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "open": [3500.0, 3520.0, 3550.0, 2800.0],
            "high": [3550.0, 3580.0, 3600.0, 2850.0],
            "low": [3480.0, 3500.0, 3520.0, 2780.0],
            "close": [3520.0, 3550.0, 3580.0, 2820.0],
            "volume": [100000000, 120000000, 90000000, 80000000],
            "amount": [352000000000, 426000000000, 322200000000, 225600000000],
        }
    )


class TestIndexBarsStore:
    """Test suite for IndexBarsStore."""

    # ============ read tests ============

    def test_read_empty(self, store: IndexBarsStore) -> None:
        """Test read with no data."""
        df = store.read()
        assert len(df) == 0

    def test_read_no_filters(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test read without filters."""
        store.write(sample_bars_df, year=2024)
        df = store.read()
        assert len(df) == 4
        assert "instrument_id" in df.columns
        assert "trade_date" in df.columns
        assert "open" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns

    def test_read_filter_by_sids(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test read filtered by instrument IDs."""
        store.write(sample_bars_df, year=2024)
        df = store.read(instrument_ids=[1600001])
        assert len(df) == 3
        assert df["instrument_id"].unique().to_list() == [1600001]

    def test_read_filter_by_date_range(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test read filtered by date range."""
        store.write(sample_bars_df, year=2024)
        df = store.read(start_date="2024-01-02", end_date="2024-01-03")
        # 2024-01-02 has 2 records, 2024-01-03 has 1 record = 3 total
        assert len(df) == 3

    def test_read_multiple_years(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test read spanning multiple year partitions."""
        # Create data with 2023 dates for the 2023 partition
        df_2023 = sample_bars_df.with_columns(
            pl.col("trade_date").map_elements(
                lambda d: d.replace(year=2023), return_dtype=pl.Date
            )
        )
        store.write(df_2023, year=2023)
        store.write(sample_bars_df, year=2024)

        df = store.read(start_date="2023-01-01", end_date="2024-12-31")
        assert len(df) == 8  # 4 records per year

    # ============ write tests ============

    def test_write_new_file(
        self,
        store: IndexBarsStore,
        sample_bars_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates new file."""
        result = store.write(sample_bars_df, year=2024)

        assert result.file_path == str(
            tmp_path / "data" / "market" / "index" / "bars" / "2024.parquet"
        )
        assert Path(result.file_path).exists()
        assert len(result.checksum) == 32  # MD5 hex string

    def test_write_merge_with_existing(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write merges with existing data."""
        # Write initial data
        store.write(sample_bars_df, year=2024)

        # Write overlapping new data
        new_data = pl.DataFrame(
            {
                "instrument_id": [1600001, 1600003],
                "trade_date": [date(2024, 1, 4), date(2024, 1, 5)],
                "open": [3560.0, 2900.0],
                "high": [3620.0, 2950.0],
                "low": [3540.0, 2880.0],
                "close": [3600.0, 2920.0],
                "volume": [95000000, 85000000],
                "amount": [342000000000, 248200000000],
            }
        )
        store.write(new_data, 2024, on_duplicate=OnDuplicate.KEEP_LAST)

        # Verify deduplication (new data overwrites)
        df = store.read()
        assert len(df) == 5  # 4 original + 1 new (1600001/2024-01-04 updated)

        # Verify new value was applied
        record = df.filter(
            (pl.col("instrument_id") == 1600001)
            & (pl.col("trade_date") == date(2024, 1, 4))
        )
        assert record["close"][0] == 3600.0

    def test_write_overwrite_existing(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write overwrites existing records with same key."""
        store.write(sample_bars_df, year=2024)

        # Write same date/instrument_id with different close price
        updated = pl.DataFrame(
            {
                "instrument_id": [1600001],
                "trade_date": [date(2024, 1, 3)],
                "open": [3530.0],
                "high": [3590.0],
                "low": [3510.0],
                "close": [3570.0],
                "volume": [125000000],
                "amount": [446250000000],
            }
        )
        store.write(updated, 2024, on_duplicate=OnDuplicate.KEEP_LAST)

        df = store.read(instrument_ids=[1600001])
        record = df.filter(pl.col("trade_date") == date(2024, 1, 3))
        assert record["close"][0] == 3570.0

    def test_write_creates_directory(
        self,
        store: IndexBarsStore,
        sample_bars_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "market" / "index" / "bars"
        assert not dataset_dir.exists()

        store.write(sample_bars_df, year=2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    # ============ get_years tests ============

    def test_get_years_empty(self, store: IndexBarsStore) -> None:
        """Test get_years with no data."""
        years = store.get_years()
        assert years == []

    def test_get_years(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test get_years returns available years."""
        store.write(sample_bars_df, year=2022)
        store.write(sample_bars_df, year=2024)
        store.write(sample_bars_df, year=2023)

        years = store.get_years()
        assert years == [2022, 2023, 2024]

    # ============ delete tests ============

    def test_delete_year(
        self,
        store: IndexBarsStore,
        sample_bars_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test delete removes year partition."""
        store.write(sample_bars_df, year=2024)

        result = store.delete_partition("2024")
        assert result is True

        file_path = tmp_path / "data" / "market" / "index" / "bars" / "2024.parquet"
        assert not file_path.exists()

    def test_delete_nonexistent_year(self, store: IndexBarsStore) -> None:
        """Test delete with non-existent year."""
        result = store.delete_partition("2024")
        assert result is False

    # ============ get_checksum tests ============

    def test_get_checksum(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test get_checksum returns MD5 hash."""
        store.write(sample_bars_df, year=2024)

        checksum = store.get_checksum(2024)
        assert len(checksum) == 32
        # Verify it's a valid hex string
        int(checksum, 16)

    def test_get_checksum_missing_file(self, store: IndexBarsStore) -> None:
        """Test get_checksum with missing file."""
        checksum = store.get_checksum(2024)
        assert checksum == ""

    # ============ count tests ============

    def test_count_empty(self, store: IndexBarsStore) -> None:
        """Test count with no data."""
        count = store.count()
        assert count == 0

    def test_count(self, store: IndexBarsStore, sample_bars_df: pl.DataFrame) -> None:
        """Test count returns total records."""
        store.write(sample_bars_df, year=2024)
        count = store.count()
        assert count == 4

    def test_count_with_filters(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test count with filters applied."""
        store.write(sample_bars_df, year=2024)
        count = store.count(instrument_ids=[1600001])
        assert count == 3

    # ============ get_date_range tests ============

    def test_get_date_range_empty(self, store: IndexBarsStore) -> None:
        """Test get_date_range with no data."""
        start, end = store.get_date_range()
        assert start is None
        assert end is None

    def test_get_date_range(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test get_date_range returns min/max dates."""
        store.write(sample_bars_df, year=2024)
        start, end = store.get_date_range()
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    # ============ list_instrument_ids tests ============

    def test_list_sids_empty(self, store: IndexBarsStore) -> None:
        """Test list_instrument_ids with no data."""
        instrument_ids = store.list_instrument_ids()
        assert instrument_ids == []

    def test_list_sids(
        self, store: IndexBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test list_instrument_ids returns unique instrument IDs."""
        store.write(sample_bars_df, year=2024)
        instrument_ids = store.list_instrument_ids()
        assert instrument_ids == [1600001, 1600002]
