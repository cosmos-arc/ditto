"""Tests for StockBarsStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.domains.market.stock.bars import StockBarsStore


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> StockBarsStore:
    """Create StockBarsStore instance."""
    return StockBarsStore(data_root)


@pytest.fixture
def sample_bars_df() -> pl.DataFrame:
    """Create sample stock daily bars DataFrame."""
    return pl.DataFrame(
        {
            "sid": [1, 1, 1, 2],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "open": [3.50, 3.52, 3.55, 2.80],
            "high": [3.55, 3.58, 3.60, 2.85],
            "low": [3.48, 3.50, 3.52, 2.78],
            "close": [3.52, 3.55, 3.58, 2.82],
            "volume": [1000000, 1200000, 900000, 800000],
            "amount": [3520000, 4260000, 3222000, 2256000],
        }
    )


class TestStockBarsStore:
    """Test suite for StockBarsStore."""

    def test_get_key_columns(self, store: StockBarsStore) -> None:
        """Test _get_key_columns returns correct key columns."""
        assert store._get_key_columns() == ["sid", "trade_date"]

    def test_read_empty(self, store: StockBarsStore) -> None:
        """Test read with no data."""
        df = store.read()
        assert len(df) == 0

    def test_read_no_filters(
        self, store: StockBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test read without filters."""
        store.write(sample_bars_df, year=2024)
        df = store.read()
        assert len(df) == 4
        assert "sid" in df.columns
        assert "trade_date" in df.columns
        assert "open" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns

    def test_write_creates_directory(
        self,
        store: StockBarsStore,
        sample_bars_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "market" / "stock" / "bars"
        assert not dataset_dir.exists()

        store.write(sample_bars_df, year=2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()

    def test_get_years_empty(self, store: StockBarsStore) -> None:
        """Test get_years with no data."""
        years = store.get_years()
        assert years == []

    def test_get_years(
        self, store: StockBarsStore, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test get_years returns available years."""
        store.write(sample_bars_df, year=2022)
        store.write(sample_bars_df, year=2024)
        store.write(sample_bars_df, year=2023)

        years = store.get_years()
        assert years == [2022, 2023, 2024]

    def test_dataset_name(self, store: StockBarsStore) -> None:
        """Test that dataset name is market/stock/bars."""
        assert store._dataset == "market/stock/bars"
