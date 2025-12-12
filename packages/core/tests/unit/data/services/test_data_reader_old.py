"""Tests for DataReader service."""

from datetime import datetime
from typing import Any

import polars as pl
import pytest
from ditto_core.data.services.data_reader import DataReader

# Test data fixtures
test_etf_list = pl.DataFrame(
    {
        "symbol": ["510300.SH", "516010.SH", "513100.SH"],
        "name": ["沪深300ETF", "游戏ETF", "纳指ETF"],
        "list_date": ["2012-04-26", "2020-02-20", "2013-04-25"],
        "knowledge_date": [
            datetime(2024, 1, 1),
            datetime(2024, 1, 1),
            datetime(2024, 1, 1),
        ],
    }
)

test_daily_data = pl.DataFrame(
    {
        "symbol": ["510300.SH"] * 5,
        "date": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
        "open": [3.456, 3.467, 3.489, 3.501, 3.512],
        "high": [3.489, 3.498, 3.512, 3.523, 3.534],
        "low": [3.445, 3.456, 3.478, 3.489, 3.501],
        "close": [3.467, 3.489, 3.501, 3.512, 3.523],
        "volume": [12345678, 13456789, 14567890, 15678901, 16789012],
        "knowledge_date": [datetime(2024, 1, 2)] * 5,
    }
)

test_adjustment_factors = pl.DataFrame(
    {
        "symbol": ["510300.SH"] * 2,
        "ex_date": ["2023-12-18", "2024-06-17"],
        "adj_factor": [0.9543, 0.9876],
        "knowledge_date": [datetime(2023, 12, 18), datetime(2024, 6, 17)],
    }
)

test_trading_calendar = pl.DataFrame(
    {
        "date": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
        "is_trading_day": [True, True, True, True, True],
        "knowledge_date": [datetime(2024, 1, 1)] * 5,
    }
)


def test_data_reader_get_etf_list(mocker: Any) -> None:
    """Test getting ETF list from database."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_etf_list

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_etf_list()

    # Assert
    assert len(result) == 3
    assert "510300.SH" in result["symbol"].to_list()
    assert "name" in result.columns
    assert "list_date" in result.columns
    mock_adapter.fetch_df.assert_called_once()

    # Verify SQL query
    call_args = mock_adapter.fetch_df.call_args
    assert "etf_info" in call_args[0][0]
    assert "ORDER BY symbol" in call_args[0][0]


def test_data_reader_get_daily_data(mocker: Any) -> None:
    """Test getting daily price data for a symbol."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_daily_data

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_daily_data("510300.SH", "2024-01-01", "2024-01-10")

    # Assert
    assert len(result) == 5
    assert result["date"].min() == "2024-01-02"
    assert result["date"].max() == "2024-01-08"
    assert "symbol" in result.columns
    assert "open" in result.columns
    assert "high" in result.columns
    assert "low" in result.columns
    assert "close" in result.columns
    assert "volume" in result.columns

    # Verify SQL query and parameters
    call_args = mock_adapter.fetch_df.call_args
    assert "daily_price_adjusted" in call_args[0][0]  # Default to adjusted
    assert "symbol = ?" in call_args[0][0]
    assert "date >= ?" in call_args[0][0]
    assert "date <= ?" in call_args[0][0]
    assert "ORDER BY date" in call_args[0][0]


def test_data_reader_get_daily_data_raw(mocker: Any) -> None:
    """Test getting raw daily price data (non-adjusted)."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_daily_data

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_daily_data(
        "510300.SH", "2024-01-01", "2024-01-10", adjusted=False
    )

    # Assert
    assert len(result) == 5

    # Verify SQL query uses raw table
    call_args = mock_adapter.fetch_df.call_args
    assert "daily_price_raw" in call_args[0][0]


def test_data_reader_get_adjustment_factors(mocker: Any) -> None:
    """Test getting adjustment factors for a symbol."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_adjustment_factors

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_adjustment_factors("510300.SH")

    # Assert
    assert len(result) == 2
    assert "ex_date" in result.columns
    assert "adj_factor" in result.columns
    assert result["symbol"].unique().to_list() == ["510300.SH"]

    # Verify SQL query
    call_args = mock_adapter.fetch_df.call_args
    assert "adjustment_factors" in call_args[0][0]
    assert "WHERE symbol = ?" in call_args[0][0]
    assert "ORDER BY ex_date" in call_args[0][0]


def test_data_reader_get_trading_calendar(mocker: Any) -> None:
    """Test getting trading calendar for date range."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_trading_calendar

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_trading_calendar("2024-01-01", "2024-01-10")

    # Assert
    assert len(result) == 5
    assert "date" in result.columns
    assert "is_trading_day" in result.columns
    assert result["date"].min() == "2024-01-02"
    assert result["date"].max() == "2024-01-08"

    # Verify SQL query
    call_args = mock_adapter.fetch_df.call_args
    assert "trading_calendar" in call_args[0][0]
    assert "date >= ?" in call_args[0][0]
    assert "date <= ?" in call_args[0][0]
    assert "ORDER BY date" in call_args[0][0]


def test_data_reader_database_error_handling(mocker: Any) -> None:
    """Test error handling when database operations fail."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.side_effect = RuntimeError("Database connection failed")

    reader = DataReader(mock_adapter)

    # Act & Assert
    with pytest.raises(RuntimeError, match="Database connection failed"):
        reader.get_etf_list()

    with pytest.raises(RuntimeError, match="Database connection failed"):
        reader.get_daily_data("510300.SH", "2024-01-01", "2024-01-10")

    with pytest.raises(RuntimeError, match="Database connection failed"):
        reader.get_adjustment_factors("510300.SH")

    with pytest.raises(RuntimeError, match="Database connection failed"):
        reader.get_trading_calendar("2024-01-01", "2024-01-10")
