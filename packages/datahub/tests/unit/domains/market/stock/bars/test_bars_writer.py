"""Tests for StockBarsWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.stores.market.stock.bars.bars_writer import StockBarsWriter


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Create temporary data root directory."""
    return tmp_path / "data"


@pytest.fixture
def writer(data_root: Path) -> StockBarsWriter:
    """Create StockBarsWriter instance."""
    return StockBarsWriter(data_root)


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


class TestStockBarsWriter:
    """Test suite for StockBarsWriter."""

    def test_write_creates_directory(
        self,
        writer: StockBarsWriter,
        sample_bars_df: pl.DataFrame,
        tmp_path: Path,
    ) -> None:
        """Test write creates dataset directory if not exists."""
        dataset_dir = tmp_path / "data" / "market" / "stock" / "bars"
        assert not dataset_dir.exists()

        result = writer.write(sample_bars_df, year=2024)

        assert dataset_dir.exists()
        assert (dataset_dir / "2024.parquet").exists()
        assert result.added == 4
        assert result.updated == 0
        assert result.is_merge is False

    def test_write_empty_df(self, writer: StockBarsWriter) -> None:
        """Test write with empty DataFrame."""
        empty_df = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Int64,
                "amount": pl.Int64,
            }
        )
        result = writer.write(empty_df, year=2024)

        assert result.added == 0
        assert result.updated == 0

    def test_write_merge(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write with merge (existing data)."""
        # First write
        writer.write(sample_bars_df, year=2024)

        # Second write with new data
        new_df = pl.DataFrame(
            {
                "instrument_id": [3],
                "trade_date": [date(2024, 1, 5)],
                "open": [4.00],
                "high": [4.05],
                "low": [3.98],
                "close": [4.02],
                "volume": [1500000],
                "amount": [6030000],
            }
        )

        result = writer.write(new_df, year=2024)

        assert result.added == 1
        assert result.updated == 0
        assert result.is_merge is True

    def test_write_on_duplicate_keep_first(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write with OnDuplicate.KEEP_FIRST."""
        # First write
        writer.write(sample_bars_df, year=2024)

        # Second write with overlapping data
        overlap_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 1, 2)],
                "open": [3.60],  # Different value
                "high": [3.65],
                "low": [3.58],
                "close": [3.62],
                "volume": [1100000],
                "amount": [3682000],
            }
        )

        result = writer.write(
            overlap_df, year=2024, on_duplicate=OnDuplicate.KEEP_FIRST
        )

        assert result.added == 0
        assert result.updated == 0

        # Verify original data is preserved
        from ditto_datahub.stores.market.stock.bars.bars_reader import (
            StockBarsReader,
        )

        reader = StockBarsReader(writer.data_root)
        df = reader.read(
            instrument_ids=[1], start_date="2024-01-02", end_date="2024-01-02"
        )
        assert len(df) == 1
        assert df["open"][0] == 3.50  # Original value

    def test_write_on_duplicate_keep_last(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write with OnDuplicate.KEEP_LAST."""
        # First write
        writer.write(sample_bars_df, year=2024)

        # Second write with overlapping data
        overlap_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 1, 2)],
                "open": [3.60],  # Different value
                "high": [3.65],
                "low": [3.58],
                "close": [3.62],
                "volume": [1100000],
                "amount": [3682000],
            }
        )

        result = writer.write(overlap_df, year=2024, on_duplicate=OnDuplicate.KEEP_LAST)

        assert result.added == 0
        assert result.updated == 1

        # Verify new data overwrote old data
        from ditto_datahub.stores.market.stock.bars.bars_reader import (
            StockBarsReader,
        )

        reader = StockBarsReader(writer.data_root)
        df = reader.read(
            instrument_ids=[1], start_date="2024-01-02", end_date="2024-01-02"
        )
        assert len(df) == 1
        assert df["open"][0] == 3.60  # New value

    def test_write_on_duplicate_error(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test write with OnDuplicate.ERROR raises on duplicate."""
        # First write
        writer.write(sample_bars_df, year=2024)

        # Second write with overlapping data
        overlap_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 1, 2)],
                "open": [3.60],
                "high": [3.65],
                "low": [3.58],
                "close": [3.62],
                "volume": [1100000],
                "amount": [3682000],
            }
        )

        with pytest.raises(ValueError, match="Duplicate data"):
            writer.write(overlap_df, year=2024, on_duplicate=OnDuplicate.ERROR)

    def test_delete(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test delete operation."""
        writer.write(sample_bars_df, year=2024)

        # Delete specific instrument
        deleted = writer.delete(instrument_ids=[1])
        assert deleted == 3

        # Verify deletion
        from ditto_datahub.stores.market.stock.bars.bars_reader import StockBarsReader

        reader = StockBarsReader(writer.data_root)
        count = reader.count()
        assert count == 1  # Only instrument 2 remains

    def test_delete_with_date_range(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame
    ) -> None:
        """Test delete with date range."""
        writer.write(sample_bars_df, year=2024)

        # Delete data in date range
        deleted = writer.delete(start_date="2024-01-02", end_date="2024-01-03")
        assert deleted == 3

        # Verify deletion
        from ditto_datahub.stores.market.stock.bars.bars_reader import StockBarsReader

        reader = StockBarsReader(writer.data_root)
        count = reader.count()
        assert count == 1  # Only 2024-01-04 remains

    def test_delete_partition(
        self, writer: StockBarsWriter, sample_bars_df: pl.DataFrame, tmp_path: Path
    ) -> None:
        """Test delete_partition operation."""
        writer.write(sample_bars_df, year=2024)

        dataset_dir = tmp_path / "data" / "market" / "stock" / "bars"
        assert (dataset_dir / "2024.parquet").exists()

        # Delete partition
        deleted = writer.delete_partition("2024")
        assert deleted is True
        assert not (dataset_dir / "2024.parquet").exists()

        # Delete non-existent partition
        deleted = writer.delete_partition("2025")
        assert deleted is False

    def test_data_root_property(self, writer: StockBarsWriter, data_root: Path) -> None:
        """Test data_root property."""
        assert writer.data_root == data_root
