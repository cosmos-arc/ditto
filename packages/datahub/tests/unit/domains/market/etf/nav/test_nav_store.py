"""Tests for EtfNavStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.market.etf.nav import EtfNavStore
from ditto_datahub.models import OnDuplicate


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> EtfNavStore:
    """Create EtfNavStore instance."""
    return EtfNavStore(data_root)


@pytest.fixture
def sample_nav_df() -> pl.DataFrame:
    """Create sample ETF NAV DataFrame."""
    return pl.DataFrame(
        {
            "sid": [1500001, 1500001, 1500001, 1500002],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "unit_nav": [3.505, 3.525, 3.555, 2.805],
            "accum_nav": [1.205, 1.215, 1.225, 0.985],
        }
    )


class TestEtfNavStore:
    """Test suite for EtfNavStore."""

    # ============ read tests ============

    def test_read_empty(self, store: EtfNavStore) -> None:
        """Test read with no data."""
        df = store.read()
        assert len(df) == 0

    def test_read_no_filters(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test read without filters."""
        store.write(sample_nav_df, year=2024)
        df = store.read()
        assert len(df) == 4
        assert "sid" in df.columns
        assert "trade_date" in df.columns
        assert "unit_nav" in df.columns
        assert "accum_nav" in df.columns

    def test_read_filter_by_sids(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test read filtered by security IDs."""
        store.write(sample_nav_df, year=2024)
        df = store.read(sids=[1500001])
        assert len(df) == 3
        assert df["sid"].unique().to_list() == [1500001]

    def test_read_filter_by_date_range(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test read filtered by date range."""
        store.write(sample_nav_df, year=2024)
        df = store.read(start_date="2024-01-02", end_date="2024-01-03")
        # 2024-01-02 has 2 records, 2024-01-03 has 1 record = 3 total
        assert len(df) == 3

    def test_read_multiple_years(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test read spanning multiple year partitions."""
        # Create data with 2023 dates for the 2023 partition
        df_2023 = sample_nav_df.with_columns(
            pl.col("trade_date").map_elements(
                lambda d: d.replace(year=2023), return_dtype=pl.Date
            )
        )
        store.write(df_2023, year=2023)
        store.write(sample_nav_df, year=2024)

        df = store.read(start_date="2023-01-01", end_date="2024-12-31")
        assert len(df) == 8  # 4 records per year

    # ============ write tests ============

    def test_write_new_file(
        self,
        store: EtfNavStore,
        sample_nav_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates new file."""
        result = store.write(sample_nav_df, year=2024)

        assert result.file_path == str(
            tmp_path / "data" / "market" / "etf" / "nav" / "2024.parquet"
        )
        assert Path(result.file_path).exists()
        assert len(result.checksum) == 32  # MD5 hex string

    def test_write_merge_with_existing(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test write merges with existing data."""
        # Write initial data
        store.write(sample_nav_df, year=2024)

        # Write overlapping new data
        new_data = pl.DataFrame(
            {
                "sid": [1500001, 1500003],
                "trade_date": [date(2024, 1, 4), date(2024, 1, 5)],
                "unit_nav": [3.560, 2.905],
                "accum_nav": [1.230, 0.995],
            }
        )
        store.write(new_data, 2024, on_duplicate=OnDuplicate.KEEP_LAST)

        # Verify deduplication (new data overwrites)
        df = store.read()
        assert len(df) == 5  # 4 original + 1 new (1500001/2024-01-04 updated)

        # Verify new value was applied
        record = df.filter(
            (pl.col("sid") == 1500001) & (pl.col("trade_date") == date(2024, 1, 4))
        )
        assert record["unit_nav"][0] == 3.560

    def test_write_overwrite_existing(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test write overwrites existing records with same key."""
        store.write(sample_nav_df, year=2024)

        # Write same date/sid with different NAV
        updated = pl.DataFrame(
            {
                "sid": [1500001],
                "trade_date": [date(2024, 1, 3)],
                "unit_nav": [3.530],
                "accum_nav": [1.220],
            }
        )
        store.write(updated, 2024, on_duplicate=OnDuplicate.KEEP_LAST)

        df = store.read(sids=[1500001])
        record = df.filter(pl.col("trade_date") == date(2024, 1, 3))
        assert record["unit_nav"][0] == 3.530

    def test_write_creates_directory(
        self,
        store: EtfNavStore,
        sample_nav_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "market" / "etf" / "nav"
        assert not dataset_dir.exists()

        store.write(sample_nav_df, year=2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    # ============ get_years tests ============

    def test_get_years_empty(self, store: EtfNavStore) -> None:
        """Test get_years with no data."""
        years = store.get_years()
        assert years == []

    def test_get_years(self, store: EtfNavStore, sample_nav_df: pl.DataFrame) -> None:
        """Test get_years returns available years."""
        store.write(sample_nav_df, year=2022)
        store.write(sample_nav_df, year=2024)
        store.write(sample_nav_df, year=2023)

        years = store.get_years()
        assert years == [2022, 2023, 2024]

    # ============ delete tests ============

    def test_delete_year(
        self,
        store: EtfNavStore,
        sample_nav_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test delete removes year partition."""
        store.write(sample_nav_df, year=2024)

        result = store.delete_partition("2024")
        assert result is True

        file_path = tmp_path / "data" / "market" / "etf" / "nav" / "2024.parquet"
        assert not file_path.exists()

    def test_delete_nonexistent_year(self, store: EtfNavStore) -> None:
        """Test delete with non-existent year."""
        result = store.delete_partition("2024")
        assert result is False

    # ============ get_checksum tests ============

    def test_get_checksum(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test get_checksum returns MD5 hash."""
        store.write(sample_nav_df, year=2024)

        checksum = store.get_checksum(2024)
        assert len(checksum) == 32
        # Verify it's a valid hex string
        int(checksum, 16)

    def test_get_checksum_missing_file(self, store: EtfNavStore) -> None:
        """Test get_checksum with missing file."""
        checksum = store.get_checksum(2024)
        assert checksum == ""

    # ============ count tests ============

    def test_count_empty(self, store: EtfNavStore) -> None:
        """Test count with no data."""
        count = store.count()
        assert count == 0

    def test_count(self, store: EtfNavStore, sample_nav_df: pl.DataFrame) -> None:
        """Test count returns total records."""
        store.write(sample_nav_df, year=2024)
        count = store.count()
        assert count == 4

    def test_count_with_filters(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test count with filters applied."""
        store.write(sample_nav_df, year=2024)
        count = store.count(sids=[1500001])
        assert count == 3

    # ============ get_date_range tests ============

    def test_get_date_range_empty(self, store: EtfNavStore) -> None:
        """Test get_date_range with no data."""
        start, end = store.get_date_range()
        assert start is None
        assert end is None

    def test_get_date_range(
        self, store: EtfNavStore, sample_nav_df: pl.DataFrame
    ) -> None:
        """Test get_date_range returns min/max dates."""
        store.write(sample_nav_df, year=2024)
        start, end = store.get_date_range()
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    # ============ list_sids tests ============

    def test_list_sids_empty(self, store: EtfNavStore) -> None:
        """Test list_sids with no data."""
        sids = store.list_sids()
        assert sids == []

    def test_list_sids(self, store: EtfNavStore, sample_nav_df: pl.DataFrame) -> None:
        """Test list_sids returns unique security IDs."""
        store.write(sample_nav_df, year=2024)
        sids = store.list_sids()
        assert sids == [1500001, 1500002]
