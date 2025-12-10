"""Test to verify that all global fixtures are working correctly."""

import datetime
import random
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl


def test_sample_price_data_fixture(sample_price_data: pl.DataFrame) -> None:
    """Test that sample_price_data fixture provides expected data."""
    # Check DataFrame shape
    assert sample_price_data.shape == (5, 9)

    # Check column names
    expected_columns = {
        "symbol",
        "trade_date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "amount",
        "knowledge_date",
    }
    assert set(sample_price_data.columns) == expected_columns

    # Check that symbol is consistent
    assert (sample_price_data["symbol"] == "510300.SH").all()

    # Check data types
    assert sample_price_data["symbol"].dtype == pl.String
    assert sample_price_data["trade_date"].dtype == pl.String
    assert sample_price_data["open_price"].dtype == pl.Float64
    assert sample_price_data["volume"].dtype == pl.Int64


def test_sample_etf_data_fixture(sample_etf_data: pl.DataFrame) -> None:
    """Test that sample_etf_data fixture provides expected data."""
    # Check DataFrame shape
    assert sample_etf_data.shape == (5, 5)

    # Check column names
    expected_columns = {
        "symbol",
        "name",
        "fund_manager",
        "tracking_index",
        "establishment_date",
    }
    assert set(sample_etf_data.columns) == expected_columns

    # Check that we have the expected ETFs
    symbols = sample_etf_data["symbol"].to_list()
    assert "510300.SH" in symbols
    assert "510500.SH" in symbols
    assert "516010.SH" in symbols

    # Check data types
    assert sample_etf_data["symbol"].dtype == pl.String
    assert sample_etf_data["name"].dtype == pl.String


def test_sample_adjustment_factor_data_fixture(
    sample_adjustment_factor_data: pl.DataFrame,
) -> None:
    """Test that sample_adjustment_factor_data fixture provides expected data."""
    # Check DataFrame shape
    assert sample_adjustment_factor_data.shape == (3, 5)

    # Check column names
    expected_columns = {
        "symbol",
        "ex_date",
        "adj_factor",
        "adj_type",
        "knowledge_date",
    }
    assert set(sample_adjustment_factor_data.columns) == expected_columns

    # Check that all adjustment types are cumulative
    assert (sample_adjustment_factor_data["adj_type"] == "cumulative").all()

    # Check that adj_factor values are increasing (cumulative)
    factors = sample_adjustment_factor_data.sort("ex_date")["adj_factor"].to_list()
    assert factors == sorted(factors)


def test_temp_dir_fixture(temp_dir: Path) -> None:
    """Test that temp_dir fixture provides a valid temporary directory."""
    # Check that it's a Path object
    assert isinstance(temp_dir, Path)

    # Check that directory exists
    assert temp_dir.exists()
    assert temp_dir.is_dir()

    # Check that we can create files in it
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    assert test_file.exists()
    assert test_file.read_text() == "test content"


def test_mock_current_time_fixture(mock_current_time: None) -> None:
    """Test that mock_current_time fixture fixes the current time."""
    # Get the mocked current time
    now = datetime.datetime.now()

    # Check that it matches our expected time
    assert now.year == 2024
    assert now.month == 1
    assert now.day == 8
    assert now.hour == 15
    assert now.minute == 0
    assert now.second == 0


def test_mock_tushare_api_fixture(mock_tushare_api: MagicMock) -> None:
    """Test that mock_tushare_api fixture provides a properly mocked API."""
    # Check that mock has the expected attributes
    assert hasattr(mock_tushare_api, "trade_cal")
    assert hasattr(mock_tushare_api, "fund_basic")
    assert hasattr(mock_tushare_api, "daily")
    assert hasattr(mock_tushare_api, "adj_factor")

    # Check that methods are callable
    assert callable(mock_tushare_api.trade_cal)
    assert callable(mock_tushare_api.fund_basic)
    assert callable(mock_tushare_api.daily)
    assert callable(mock_tushare_api.adj_factor)


def test_mock_akshare_api_fixture(mock_akshare_api: MagicMock) -> None:
    """Test that mock_akshare_api fixture provides a properly mocked API."""
    # Check that akshare module is mocked
    assert mock_akshare_api.fund_etf_basic is not None
    assert mock_akshare_api.stock_zh_a_hist is not None

    # Check that methods return expected data
    etf_data = mock_akshare_api.fund_etf_basic()
    assert etf_data is not None

    daily_data = mock_akshare_api.stock_zh_a_hist()
    assert daily_data is not None


def test_fixed_seed_fixture_applied() -> None:
    """Test that fixed_seed fixture is automatically applied to all tests."""
    # Generate some random numbers

    # First sequence
    seq1 = [random.random() for _ in range(5)]

    # Reset seed and generate again (simulating a new test)
    random.seed(42)
    seq2 = [random.random() for _ in range(5)]

    # They should be the same
    assert seq1 == seq2
