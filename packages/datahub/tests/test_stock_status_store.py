"""Tests for StockStatusStore (B.3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest


class TestStockStatusStore:
    """Test suite for StockStatusStore."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def store(self, data_root: Path):
        """Create StockStatusStore instance."""
        from ditto_datahub.stores.stock_status_store import StockStatusStore

        return StockStatusStore(data_root)

    @pytest.fixture
    def sample_df(self) -> pl.DataFrame:
        """Create sample stock status data."""
        data: dict[str, list[Any]] = {
            "sid": [100000001, 100000001, 100000001, 100000002],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "is_suspended": [False, False, True, False],
            "suspend_timing": [None, None, "09:30-10:00", None],
            "is_st": [False, False, False, True],
            "st_type": [None, None, None, "ST"],
            "list_status": ["L", "L", "L", "L"],
            "source": ["tushare", "tushare", "tushare", "tushare"],
            "src_code": ["000001.SZ", "000001.SZ", "000001.SZ", "000002.SZ"],
        }
        return pl.DataFrame(data)

    # ============ _get_path tests ============

    def test_get_path(self, store) -> None:
        """Test _get_path generates correct file path."""
        path = store._get_path("stock_status", 2024)
        expected = store._data_root / "stock_status" / "2024.parquet"
        assert path == expected

    # ============ read tests ============

    def test_read_empty(self, store) -> None:
        """Test read with no data."""
        df = store.read("stock_status")
        assert len(df) == 0

    def test_read_no_filters(self, store, sample_df: pl.DataFrame) -> None:
        """Test read without filters."""
        store.write("stock_status", sample_df, 2024)
        df = store.read("stock_status")
        assert len(df) == 4
        assert "sid" in df.columns
        assert "trade_date" in df.columns
        assert "is_suspended" in df.columns
        assert "is_st" in df.columns
        assert "list_status" in df.columns

    def test_read_filter_by_sids(self, store, sample_df: pl.DataFrame) -> None:
        """Test read filtered by security IDs."""
        store.write("stock_status", sample_df, 2024)
        df = store.read("stock_status", sids=[100000001])
        assert len(df) == 3
        assert df["sid"].unique().to_list() == [100000001]

    # ============ write tests ============

    def test_write_new_file(
        self, store, sample_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test write creates new file."""
        file_path, checksum = store.write("stock_status", sample_df, 2024)

        assert file_path == str(tmp_path / "data" / "stock_status" / "2024.parquet")
        assert Path(file_path).exists()
        assert len(checksum) == 32  # MD5 hex string

    def test_write_creates_directory(
        self, store, sample_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "stock_status"
        assert not dataset_dir.exists()

        store.write("stock_status", sample_df, 2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    # ============ get_years tests ============

    def test_get_years_empty(self, store) -> None:
        """Test get_years with no data."""
        years = store.get_years("stock_status")
        assert years == []

    def test_get_years(self, store, sample_df: pl.DataFrame) -> None:
        """Test get_years returns available years."""
        store.write("stock_status", sample_df, 2022)
        store.write("stock_status", sample_df, 2024)
        store.write("stock_status", sample_df, 2023)

        years = store.get_years("stock_status")
        assert years == [2022, 2023, 2024]

    # ============ delete tests ============

    def test_delete_year(self, store, sample_df: pl.DataFrame, tmp_path: Path) -> None:
        """Test delete removes year partition."""
        store.write("stock_status", sample_df, 2024)

        result = store.delete("stock_status", 2024)
        assert result is True

        file_path = tmp_path / "data" / "stock_status" / "2024.parquet"
        assert not file_path.exists()

    # ============ count tests ============

    def test_count_empty(self, store) -> None:
        """Test count with no data."""
        count = store.count("stock_status")
        assert count == 0

    def test_count(self, store, sample_df: pl.DataFrame) -> None:
        """Test count returns total records."""
        store.write("stock_status", sample_df, 2024)
        count = store.count("stock_status")
        assert count == 4

    # ============ get_date_range tests ============

    def test_get_date_range_empty(self, store) -> None:
        """Test get_date_range with no data."""
        start, end = store.get_date_range("stock_status")
        assert start is None
        assert end is None

    def test_get_date_range(self, store, sample_df: pl.DataFrame) -> None:
        """Test get_date_range returns min/max dates."""
        store.write("stock_status", sample_df, 2024)
        start, end = store.get_date_range("stock_status")
        assert start == "2024-01-02"
        assert end == "2024-01-04"


class TestStockStatusRiskControlFields:
    """Tests for risk control fields (B.3)."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def store(self, data_root: Path):
        """Create StockStatusStore instance."""
        from ditto_datahub.stores.stock_status_store import StockStatusStore

        return StockStatusStore(data_root)

    @pytest.fixture
    def suspension_df(self) -> pl.DataFrame:
        """Create test data with suspension information."""
        data: dict[str, list[Any]] = {
            "sid": [100000001, 100000002, 100000003],
            "trade_date": [
                date(2024, 1, 5),
                date(2024, 1, 5),
                date(2024, 1, 5),
            ],
            "is_suspended": [True, False, True],
            "suspend_timing": ["09:30-10:00", "", "10:00-11:30"],
            "is_st": [False, True, False],
            "st_type": ["", "ST", ""],
            "list_status": ["L", "L", "D"],
            "source": ["tushare", "tushare", "tushare"],
            "src_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
        }
        return pl.DataFrame(data)

    def test_suspension_fields(self, store, suspension_df: pl.DataFrame) -> None:
        """Test suspension status fields are correctly stored and retrieved."""
        store.write("stock_status", suspension_df, 2024)
        result = store.read("stock_status", sids=[100000001])

        assert len(result) == 1
        assert result["is_suspended"][0] is True
        assert result["suspend_timing"][0] == "09:30-10:00"

    def test_st_status_fields(self, store, suspension_df: pl.DataFrame) -> None:
        """Test ST status fields are correctly stored and retrieved."""
        store.write("stock_status", suspension_df, 2024)
        result = store.read("stock_status", sids=[100000002])

        assert len(result) == 1
        assert result["is_st"][0] is True
        assert result["st_type"][0] == "ST"

    def test_list_status_field(self, store, suspension_df: pl.DataFrame) -> None:
        """Test list_status field is correctly stored and retrieved."""
        store.write("stock_status", suspension_df, 2024)
        result = store.read("stock_status", sids=[100000003])

        assert len(result) == 1
        assert result["list_status"][0] == "D"  # Delisted

    def test_filter_by_sids_with_risk_fields(
        self, store, suspension_df: pl.DataFrame
    ) -> None:
        """Test filtering works correctly with risk control fields."""
        store.write("stock_status", suspension_df, 2024)
        result = store.read("stock_status", sids=[100000001, 100000002])

        assert len(result) == 2
        # Verify all risk fields are present
        assert "is_suspended" in result.columns
        assert "suspend_timing" in result.columns
        assert "is_st" in result.columns
        assert "st_type" in result.columns
        assert "list_status" in result.columns

    def test_multiple_sids_with_mixed_status(self, store) -> None:
        """Test reading multiple SIDs with mixed status combinations."""
        mixed_df = pl.DataFrame(
            {
                "sid": [100000001, 100000001, 100000002, 100000002],
                "trade_date": [
                    date(2024, 1, 5),
                    date(2024, 1, 6),
                    date(2024, 1, 5),
                    date(2024, 1, 6),
                ],
                "is_suspended": [True, False, False, True],
                "suspend_timing": ["09:30-10:00", "", "", "14:00-15:00"],
                "is_st": [True, True, False, False],
                "st_type": ["*ST", "*ST", "", ""],
                "list_status": ["L", "L", "L", "P"],
                "source": ["tushare", "tushare", "tushare", "tushare"],
                "src_code": [
                    "000001.SZ",
                    "000001.SZ",
                    "000002.SZ",
                    "000002.SZ",
                ],
            }
        )
        store.write("stock_status", mixed_df, 2024)
        result = store.read("stock_status", sids=[100000001, 100000002])

        assert len(result) == 4
        # Verify first record (suspended ST stock)
        first = (
            result.filter(pl.col("sid") == 100000001)
            .sort("trade_date")
            .row(0, named=True)
        )
        assert first["is_suspended"] is True
        assert first["suspend_timing"] == "09:30-10:00"
        assert first["is_st"] is True
        assert first["st_type"] == "*ST"
