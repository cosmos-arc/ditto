"""Tests for StockBarsReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.stores.market.stock.bars.bars_reader import StockBarsReader


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def reader(data_root: Path) -> StockBarsReader:
    """Create StockBarsReader instance."""
    return StockBarsReader(data_root)


@pytest.fixture
def sample_bars_df() -> pl.DataFrame:
    """Create sample stock daily bars DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 1, 2],
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


@pytest.fixture
def populated_reader(
    reader: StockBarsReader, sample_bars_df: pl.DataFrame
) -> StockBarsReader:
    """Create reader with pre-populated data."""
    # Use the writer to populate data
    from ditto_datahub.stores.market.stock.bars.bars_writer import StockBarsWriter

    writer = StockBarsWriter(reader.data_root)
    writer.write(sample_bars_df, year=2024)
    return reader


class TestStockBarsReader:
    """Test suite for StockBarsReader."""

    def test_read_empty(self, reader: StockBarsReader) -> None:
        """Test read with no data."""
        df = reader.read()
        assert len(df) == 0

    def test_read_no_filters(self, populated_reader: StockBarsReader) -> None:
        """Test read without filters."""
        df = populated_reader.read()
        assert len(df) == 4
        assert "instrument_id" in df.columns
        assert "trade_date" in df.columns
        assert "open" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns

    def test_read_with_instrument_ids(self, populated_reader: StockBarsReader) -> None:
        """Test read with instrument_ids filter."""
        df = populated_reader.read(instrument_ids=[1])
        assert len(df) == 3
        assert df["instrument_id"].unique().to_list() == [1]

    def test_read_with_date_range(self, populated_reader: StockBarsReader) -> None:
        """Test read with date range filter."""
        df = populated_reader.read(start_date="2024-01-02", end_date="2024-01-03")
        assert len(df) == 3
        assert df["trade_date"].max() == date(2024, 1, 3)

    def test_count_empty(self, reader: StockBarsReader) -> None:
        """Test count with no data."""
        count = reader.count()
        assert count == 0

    def test_count(self, populated_reader: StockBarsReader) -> None:
        """Test count with data."""
        count = populated_reader.count()
        assert count == 4

    def test_count_with_filters(self, populated_reader: StockBarsReader) -> None:
        """Test count with filters."""
        count = populated_reader.count(instrument_ids=[1])
        assert count == 3

    def test_get_years_empty(self, reader: StockBarsReader) -> None:
        """Test get_years with no data."""
        years = reader.get_years()
        assert years == []

    def test_get_years(self, populated_reader: StockBarsReader) -> None:
        """Test get_years returns available years."""
        years = populated_reader.get_years()
        assert years == [2024]

    def test_get_date_range_empty(self, reader: StockBarsReader) -> None:
        """Test get_date_range with no data."""
        start, end = reader.get_date_range()
        assert start is None
        assert end is None

    def test_get_date_range(self, populated_reader: StockBarsReader) -> None:
        """Test get_date_range with data."""
        start, end = populated_reader.get_date_range()
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    def test_list_instrument_ids_empty(self, reader: StockBarsReader) -> None:
        """Test list_instrument_ids with no data."""
        ids = reader.list_instrument_ids()
        assert ids == []

    def test_list_instrument_ids(self, populated_reader: StockBarsReader) -> None:
        """Test list_instrument_ids with data."""
        ids = populated_reader.list_instrument_ids()
        assert ids == [1, 2]

    def test_data_root_property(self, reader: StockBarsReader, data_root: Path) -> None:
        """Test data_root property."""
        assert reader.data_root == data_root
