"""Tests for EtfStatusStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_datahub.stores.market.etf.status import EtfStatusStore


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> EtfStatusStore:
    """Create EtfStatusStore instance."""
    return EtfStatusStore(data_root)


@pytest.fixture
def sample_status_df() -> pl.DataFrame:
    """Create sample ETF status DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1500001, 1500001, 1500001, 1500002],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "list_status": ["L", "L", "L", "L"],
            "is_suspended": [False, False, False, False],
            "is_st": [False, False, False, False],
        }
    )


class TestEtfStatusStore:
    """Test suite for EtfStatusStore."""

    # ============ read tests ============

    def test_read_empty(self, store: EtfStatusStore) -> None:
        """Test read with no data."""
        df = store.read()
        assert len(df) == 0

    def test_read_no_filters(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test read without filters."""
        store.write(sample_status_df, year=2024)
        df = store.read()
        assert len(df) == 4
        assert "instrument_id" in df.columns
        assert "trade_date" in df.columns
        assert "list_status" in df.columns
        assert "is_suspended" in df.columns
        assert "is_st" in df.columns

    def test_read_filter_by_sids(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test read filtered by instrument IDs."""
        store.write(sample_status_df, year=2024)
        df = store.read(instrument_ids=[1500001])
        assert len(df) == 3
        assert df["instrument_id"].unique().to_list() == [1500001]

    def test_read_filter_by_date_range(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test read filtered by date range."""
        store.write(sample_status_df, year=2024)
        df = store.read(start_date="2024-01-02", end_date="2024-01-03")
        # 2024-01-02 has 2 records, 2024-01-03 has 1 record = 3 total
        assert len(df) == 3

    # ============ write tests ============

    def test_write_new_file(
        self,
        store: EtfStatusStore,
        sample_status_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates new file."""
        result = store.write(sample_status_df, year=2024)

        assert result.file_path == str(
            tmp_path / "data" / "market" / "etf" / "status" / "2024.parquet"
        )
        assert Path(result.file_path).exists()
        assert len(result.checksum) == 32  # MD5 hex string

    def test_write_creates_directory(
        self,
        store: EtfStatusStore,
        sample_status_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "market" / "etf" / "status"
        assert not dataset_dir.exists()

        store.write(sample_status_df, year=2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    # ============ get_years tests ============

    def test_get_years_empty(self, store: EtfStatusStore) -> None:
        """Test get_years with no data."""
        years = store.get_years()
        assert years == []

    def test_get_years(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test get_years returns available years."""
        store.write(sample_status_df, year=2022)
        store.write(sample_status_df, year=2024)
        store.write(sample_status_df, year=2023)

        years = store.get_years()
        assert years == [2022, 2023, 2024]

    # ============ delete tests ============

    def test_delete_year(
        self,
        store: EtfStatusStore,
        sample_status_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test delete removes year partition."""
        store.write(sample_status_df, year=2024)

        result = store.delete_partition("2024")
        assert result is True

        file_path = tmp_path / "data" / "market" / "etf" / "status" / "2024.parquet"
        assert not file_path.exists()

    def test_delete_nonexistent_year(self, store: EtfStatusStore) -> None:
        """Test delete with non-existent year."""
        result = store.delete_partition("2024")
        assert result is False

    # ============ get_checksum tests ============

    def test_get_checksum(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test get_checksum returns MD5 hash."""
        store.write(sample_status_df, year=2024)

        checksum = store.get_checksum(2024)
        assert len(checksum) == 32
        # Verify it's a valid hex string
        int(checksum, 16)

    def test_get_checksum_missing_file(self, store: EtfStatusStore) -> None:
        """Test get_checksum with missing file."""
        checksum = store.get_checksum(2024)
        assert checksum == ""

    # ============ count tests ============

    def test_count_empty(self, store: EtfStatusStore) -> None:
        """Test count with no data."""
        count = store.count()
        assert count == 0

    def test_count(self, store: EtfStatusStore, sample_status_df: pl.DataFrame) -> None:
        """Test count returns total records."""
        store.write(sample_status_df, year=2024)
        count = store.count()
        assert count == 4

    def test_count_with_filters(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test count with filters applied."""
        store.write(sample_status_df, year=2024)
        count = store.count(instrument_ids=[1500001])
        assert count == 3

    # ============ get_date_range tests ============

    def test_get_date_range_empty(self, store: EtfStatusStore) -> None:
        """Test get_date_range with no data."""
        start, end = store.get_date_range()
        assert start is None
        assert end is None

    def test_get_date_range(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test get_date_range returns min/max dates."""
        store.write(sample_status_df, year=2024)
        start, end = store.get_date_range()
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    # ============ list_instrument_ids tests ============

    def test_list_sids_empty(self, store: EtfStatusStore) -> None:
        """Test list_instrument_ids with no data."""
        instrument_ids = store.list_instrument_ids()
        assert instrument_ids == []

    def test_list_sids(
        self, store: EtfStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test list_instrument_ids returns unique instrument IDs."""
        store.write(sample_status_df, year=2024)
        instrument_ids = store.list_instrument_ids()
        assert instrument_ids == [1500001, 1500002]


class TestEtfStatusRiskControlFields:
    """Tests for risk control fields."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def store(self, data_root: Path) -> EtfStatusStore:
        """Create EtfStatusStore instance."""
        return EtfStatusStore(data_root)

    @pytest.fixture
    def status_df(self) -> pl.DataFrame:
        """Create test data with status information."""
        data: dict[str, list[Any]] = {
            "instrument_id": [1500001, 1500002, 1500003],
            "trade_date": [
                date(2024, 1, 5),
                date(2024, 1, 5),
                date(2024, 1, 5),
            ],
            "is_suspended": [False, True, False],
            "is_st": [False, False, True],
            "list_status": ["L", "L", "D"],
        }
        return pl.DataFrame(data)

    def test_suspension_fields(
        self, store: EtfStatusStore, status_df: pl.DataFrame
    ) -> None:
        """Test suspension status fields are correctly stored and retrieved."""
        store.write(status_df, year=2024)
        result = store.read(instrument_ids=[1500002])

        assert len(result) == 1
        assert result["is_suspended"][0] is True

    def test_list_status_field(
        self, store: EtfStatusStore, status_df: pl.DataFrame
    ) -> None:
        """Test list_status field is correctly stored and retrieved."""
        store.write(status_df, year=2024)
        result = store.read(instrument_ids=[1500003])

        assert len(result) == 1
        assert result["list_status"][0] == "D"  # Delisted

    def test_filter_by_sids_with_status_fields(
        self, store: EtfStatusStore, status_df: pl.DataFrame
    ) -> None:
        """Test filtering works correctly with status fields."""
        store.write(status_df, year=2024)
        result = store.read(instrument_ids=[1500001, 1500002])

        assert len(result) == 2
        # Verify all status fields are present
        assert "is_suspended" in result.columns
        assert "is_st" in result.columns
        assert "list_status" in result.columns
