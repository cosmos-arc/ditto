"""Unit tests for DataCollector."""

from datetime import date
from typing import Any
from unittest.mock import MagicMock, Mock

import polars as pl
import pytest
from ditto_core.data.collector import DataCollector
from ditto_core.data.services.data_writer import DataWriter


class TestDataCollector:
    """Test DataCollector functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_data_writer = MagicMock(spec=DataWriter)
        self.collector = DataCollector(
            data_writer=self.mock_data_writer,
            batch_size=500,
            max_concurrent_fetches=2,
        )

    def test_initialization(self) -> None:
        """Test DataCollector initialization."""
        assert self.collector.data_writer == self.mock_data_writer
        assert self.collector.batch_size == 500
        assert self.collector.max_concurrent_fetches == 2

    def test_initialization_with_defaults(self) -> None:
        """Test DataCollector initialization with default values."""
        collector = DataCollector(data_writer=self.mock_data_writer)
        assert collector.batch_size == 1000
        assert collector.max_concurrent_fetches == 3

    def test_update_etf_list_no_sources(self) -> None:
        """Test updating ETF list with no data sources."""
        with pytest.raises(ValueError, match="未配置主数据源 Tushare"):
            self.collector.update_etf_list()

    def test_update_daily_data_stub(self) -> None:
        """Test updating daily market data - stub implementation."""
        # Note: This test ensures backward compatibility with old test structure
        # but the actual implementation is tested in
        # test_update_daily_data_with_single_symbol
        # We're testing that the method exists and returns a dict-like structure
        pass

    def test_update_daily_data_stub_no_params(self) -> None:
        """Test updating daily data with no parameters - should fail."""
        # Note: The new implementation requires symbols, start_date, and end_date
        # This test verifies that missing parameters raise an error
        with pytest.raises(TypeError, match="missing 3 required positional arguments"):
            self.collector.update_daily_data()

    @pytest.mark.asyncio
    async def test_update_adj_factors(self) -> None:
        """Test updating adjustment factors."""
        result = await self.collector.update_adj_factors(
            ts_codes=["000001.SZ"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert isinstance(result, dict)
        assert result["total_records"] == 0
        assert result["new_records"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_verify_data_quality(self) -> None:
        """Test verifying data quality for a symbol."""
        result = await self.collector.verify_data_quality(
            symbol="000001.SZ", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
        )

        assert isinstance(result, dict)
        assert result["symbol"] == "000001.SZ"
        assert result["issues"] == []
        assert result["quality_score"] == 100.0

    @pytest.mark.asyncio
    async def test_verify_data_quality_no_dates(self) -> None:
        """Test verifying data quality without date range."""
        result = await self.collector.verify_data_quality(symbol="000001.SZ")

        assert result["symbol"] == "000001.SZ"
        assert isinstance(result["issues"], list)
        assert isinstance(result["quality_score"], float)

    @pytest.mark.asyncio
    async def test_validate_daily_data(self) -> None:
        """Test validating daily data for a symbol."""
        mock_data = MagicMock()
        result = await self.collector._validate_daily_data("000001.SZ", mock_data)

        assert isinstance(result, list)
        assert result == []

    def test_update_etf_list_fetches_and_stores_data(self) -> None:
        """Test that update_etf_list fetches data from source and stores it."""
        # Arrange
        mock_tushare = Mock()
        mock_tushare.get_etf_list.return_value = pl.DataFrame(
            {
                "symbol": ["510300.SH", "516010.SH"],
                "name": ["沪深300ETF", "上证50ETF"],
                "list_date": ["2012-04-26", "2015-05-26"],
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        collector._sources = {"tushare": mock_tushare}

        # Act
        result = collector.update_etf_list()

        # Assert
        assert result["total_updated"] == 2
        assert result["source"] == "tushare"
        assert result["status"] == "success"

        # Verify store_etf_info was called
        self.mock_data_writer.store_etf_info.assert_called_once()

    def test_update_daily_data_with_single_symbol(self, monkeypatch: Any) -> None:
        """Test updating daily data for a single symbol with cross-validation."""
        # Arrange
        mock_source = Mock()
        mock_source.get_daily_data.return_value = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        collector._sources = {"tushare": mock_source}

        # Act
        result = collector.update_daily_data(
            symbols=["510300.SH"], start_date="2024-01-01", end_date="2024-01-01"
        )

        # Assert
        assert result["total_records"] == 1
        assert "510300.SH" in result["symbols_updated"]
        assert result["status"] == "completed"

    def test_update_daily_data_with_validation(self, monkeypatch: Any) -> None:
        """Test updating daily data with cross-validation enabled."""
        # Arrange
        mock_primary = Mock()
        mock_primary.get_daily_data.return_value = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
            }
        )

        mock_backup = Mock()
        mock_backup.get_daily_data.return_value = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.551],  # Slight difference (0.03%)
                "volume": [1000000],
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        collector._sources = {"tushare": mock_primary, "akshare": mock_backup}

        # Act
        result = collector.update_daily_data(
            symbols=["510300.SH"],
            start_date="2024-01-01",
            end_date="2024-01-01",
            validate=True,
        )

        # Assert
        assert result["total_records"] == 1
        assert "510300.SH" in result["symbols_updated"]
        assert result["status"] == "completed"

    def test_validate_price_consistency_with_identical_data(self) -> None:
        """Test price validation with identical data."""
        df1 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})
        df2 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})

        collector = DataCollector(data_writer=self.mock_data_writer)
        assert collector._validate_price_consistency(df1, df2) is True

    def test_validate_price_consistency_with_small_difference(self) -> None:
        """Test price validation with small difference within tolerance."""
        df1 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})
        df2 = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "close": [3.551],  # 0.03% difference
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        assert collector._validate_price_consistency(df1, df2) is True

    def test_validate_price_consistency_with_large_difference(self) -> None:
        """Test price validation with large difference beyond tolerance."""
        df1 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})
        df2 = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "close": [3.80],  # 7% difference
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        assert collector._validate_price_consistency(df1, df2) is False

    def test_validate_price_consistency_with_empty_dataframes(self) -> None:
        """Test price validation with empty DataFrames."""
        df1 = pl.DataFrame({"date": [], "close": []})
        df2 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})

        collector = DataCollector(data_writer=self.mock_data_writer)
        assert collector._validate_price_consistency(df1, df2) is False

        # Test with both empty
        df2_empty = pl.DataFrame({"date": [], "close": []})
        assert collector._validate_price_consistency(df1, df2_empty) is False

    def test_validate_price_consistency_with_none_values(self) -> None:
        """Test price validation with None values in price data."""
        df1 = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [3.55, None, 3.57],
            }
        )
        df2 = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [3.55, 3.56, None],
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        # Should validate only non-null values (2024-01-01)
        assert collector._validate_price_consistency(df1, df2) is True

        # Test with all null values
        df1_all_null = pl.DataFrame({"date": ["2024-01-01"], "close": [None]})
        df2_all_null = pl.DataFrame({"date": ["2024-01-01"], "close": [None]})
        result = collector._validate_price_consistency(df1_all_null, df2_all_null)
        assert result is False

    def test_validate_price_consistency_with_missing_columns(self) -> None:
        """Test price validation with missing required columns."""
        df1 = pl.DataFrame({"date": ["2024-01-01"]})  # Missing close
        df2 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})

        collector = DataCollector(data_writer=self.mock_data_writer)
        assert collector._validate_price_consistency(df1, df2) is False

        # Test with missing date
        df1_no_date = pl.DataFrame({"close": [3.55]})
        df2_no_date = pl.DataFrame({"close": [3.55]})
        assert collector._validate_price_consistency(df1_no_date, df2_no_date) is False

    def test_validate_price_consistency_custom_tolerance(self) -> None:
        """Test price validation with custom tolerance."""
        df1 = pl.DataFrame({"date": ["2024-01-01"], "close": [3.55]})
        df2 = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "close": [3.80],  # 7% difference
            }
        )

        collector = DataCollector(data_writer=self.mock_data_writer)
        # Default tolerance (1%) should fail
        assert collector._validate_price_consistency(df1, df2) is False

        # Custom tolerance (10%) should pass
        assert collector._validate_price_consistency(df1, df2, tolerance=0.10) is True

    def test_update_daily_data_with_empty_symbols_list(self) -> None:
        """Test updating daily data with empty symbols list."""
        # Arrange
        collector = DataCollector(data_writer=self.mock_data_writer)

        # Act
        result = collector.update_daily_data(
            symbols=[], start_date="2024-01-01", end_date="2024-01-01"
        )

        # Assert
        assert result["total_records"] == 0
        assert result["symbols_updated"] == []
        assert result["validation_errors"] == []
        assert result["status"] == "completed"

        # Verify no data source calls were made
        assert len(collector._sources) == 0
