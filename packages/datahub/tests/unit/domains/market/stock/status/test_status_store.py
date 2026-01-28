"""Tests for StockStatusStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.market.stock.status import StockStatusStore


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> StockStatusStore:
    """Create StockStatusStore instance."""
    return StockStatusStore(data_root)


@pytest.fixture
def sample_status_df() -> pl.DataFrame:
    """Create sample stock status DataFrame."""
    return pl.DataFrame(
        {
            "sid": [1, 1, 1, 2],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "is_suspended": [False, False, True, False],
            "suspend_timing": ["", "", "停牌", ""],
            "is_st": [False, False, False, True],
            "st_type": ["", "", "", "ST"],
            "list_status": ["L", "L", "L", "L"],
        }
    )


class TestStockStatusStore:
    """Test suite for StockStatusStore."""

    def test_read_empty(self, store: StockStatusStore) -> None:
        """Test read with no data."""
        df = store.read()
        assert len(df) == 0

    def test_read_no_filters(
        self, store: StockStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test read without filters."""
        store.write(sample_status_df, year=2024)
        df = store.read()
        assert len(df) == 4
        assert "sid" in df.columns
        assert "trade_date" in df.columns
        assert "is_suspended" in df.columns
        assert "is_st" in df.columns

    def test_write_creates_directory(
        self,
        store: StockStatusStore,
        sample_status_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "market" / "stock" / "status"
        assert not dataset_dir.exists()

        store.write(sample_status_df, year=2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    def test_get_years_empty(self, store: StockStatusStore) -> None:
        """Test get_years with no data."""
        years = store.get_years()
        assert years == []

    def test_get_years(
        self, store: StockStatusStore, sample_status_df: pl.DataFrame
    ) -> None:
        """Test get_years returns available years."""
        store.write(sample_status_df, year=2022)
        store.write(sample_status_df, year=2024)
        store.write(sample_status_df, year=2023)

        years = store.get_years()
        assert years == [2022, 2023, 2024]

    def test_dataset_name(self, store: StockStatusStore) -> None:
        """Test that dataset name is market/stock/status."""
        assert store._dataset == "market/stock/status"
