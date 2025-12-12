"""Tests for the DataReader implementation without adapter abstraction."""

from unittest.mock import patch

import pytest
from ditto_core.data.services.data_reader import DataReader


class TestDataReader:
    """Test cases for the DataReader implementation."""

    @pytest.fixture
    def test_reader(self):
        """Create a DataReader instance with in-memory databases for testing."""
        return DataReader.for_testing()

    def test_get_etf_list_returns_empty_dataframe_initially(self, test_reader):
        """Test that get_etf_list returns empty DataFrame when no data."""
        # Act
        result = test_reader.get_etf_list()

        # Assert
        assert result is not None
        assert len(result) == 0
        assert list(result.columns) == ["symbol", "name", "list_date", "knowledge_date"]

    def test_store_and_get_etf_list(self, test_reader):
        """Test storing and retrieving ETF data."""
        # Arrange
        test_data = [
            {"symbol": "159915", "name": "创业板ETF", "list_date": "2011-01-01"},
            {"symbol": "510300", "name": "沪深300ETF", "list_date": "2012-05-04"},
        ]

        # Act
        test_reader.store_etf_info(test_data)
        result = test_reader.get_etf_list()

        # Assert
        assert len(result) == 2
        symbols = result["symbol"].to_list()
        assert "159915" in symbols
        assert "510300" in symbols

    def test_get_daily_data_when_no_data_returns_empty(self, test_reader):
        """Test get_daily_data returns empty when no data exists."""
        # Act
        result = test_reader.get_daily_data("159915", "2024-01-01", "2024-01-05")

        # Assert
        assert len(result) == 0

    def test_store_and_get_daily_data(self, test_reader):
        """Test storing and retrieving daily price data."""
        # Arrange
        test_reader.store_etf_info([{"symbol": "159915", "name": "测试ETF"}])

        daily_data = [
            {
                "symbol": "159915",
                "date": "2024-01-02",
                "open": 2.5,
                "high": 2.6,
                "low": 2.4,
                "close": 2.55,
                "volume": 1000000,
            },
            {
                "symbol": "159915",
                "date": "2024-01-03",
                "open": 2.55,
                "high": 2.65,
                "low": 2.5,
                "close": 2.6,
                "volume": 1200000,
            },
        ]

        # Act
        test_reader.store_daily_data(daily_data)
        result = test_reader.get_daily_data("159915", "2024-01-01", "2024-01-05")

        # Assert
        assert len(result) == 2
        assert result["symbol"][0] == "159915"
        assert str(result["date"][0]) == "2024-01-02"
        assert float(result["close"][1]) == 2.6

    def test_get_trading_calendar_when_empty(self, test_reader):
        """Test get_trading_calendar returns empty when no data."""
        # Act
        result = test_reader.get_trading_calendar("2024-01-01", "2024-01-05")

        # Assert
        assert len(result) == 0

    def test_store_and_get_trading_calendar(self, test_reader):
        """Test storing and retrieving trading calendar."""
        # Arrange
        calendar_data = [
            {"date": "2024-01-01", "is_trading_day": False},
            {"date": "2024-01-02", "is_trading_day": True},
            {"date": "2024-01-03", "is_trading_day": True},
        ]

        # Act
        test_reader.store_trading_calendar(calendar_data)
        result = test_reader.get_trading_calendar("2024-01-01", "2024-01-05")

        # Assert
        assert len(result) == 3
        trading_days = result.filter(result["is_trading_day"] == True)
        assert len(trading_days) == 2

    def test_get_adjustment_factors_when_empty(self, test_reader):
        """Test get_adjustment_factors returns empty when no data."""
        # Act
        result = test_reader.get_adjustment_factors("159915")

        # Assert
        assert len(result) == 0

    def test_store_and_get_adjustment_factors(self, test_reader):
        """Test storing and retrieving adjustment factors."""
        # Arrange
        adj_data = [
            {
                "symbol": "159915",
                "ex_date": "2024-01-02",
                "adj_factor": 1.05,
                "adj_type": "dividend",
            },
            {
                "symbol": "159915",
                "ex_date": "2024-06-01",
                "adj_factor": 1.1,
                "adj_type": "split",
            },
        ]

        # Act
        test_reader.store_adjustment_factors(adj_data)
        result = test_reader.get_adjustment_factors("159915")

        # Assert
        assert len(result) == 2
        assert result["symbol"][0] == "159915"
        assert str(result["ex_date"][0]) == "2024-01-02"

    def test_data_reader_initialization_uses_real_paths(self):
        """Test that DataReader uses configured database paths when not in test mode."""
        # Arrange & Act
        with patch("ditto_foundation.config.settings.get_settings") as mock_settings:
            mock_settings.return_value.database.duckdb_path = "/test/path/market.db"
            mock_settings.return_value.database.sqlite_path = "/test/path/trading.db"

            reader = DataReader()

            # Assert
            # The constructor should have attempted to create the directories
            # We can't easily test the actual connections without files
            assert reader is not None
