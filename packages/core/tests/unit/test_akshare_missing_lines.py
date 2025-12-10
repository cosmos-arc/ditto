"""Test to cover missing lines in akshare.py."""

from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from ditto_core.data.datasources.akshare import AkShareDataSource


def test_akshare_not_available_initialization() -> None:
    """Test initialization when AKSHARE_AVAILABLE is False."""
    with patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", False):
        with pytest.raises(ImportError) as exc_info:
            AkShareDataSource()

        assert "AkShare not available" in str(exc_info.value)


def test_akshare_rate_limit() -> None:
    """Test rate limiting functionality."""
    source = AkShareDataSource()
    source._last_request_time = None

    # Test first call
    with patch("time.time", return_value=1000.0):
        source._rate_limit()
        assert source._last_request_time == 1000.0

    # Test rate limiting
    with patch("time.time", return_value=1000.1):
        source._rate_limit()  # Should not sleep as interval is 1 second


def test_akshare_get_daily_data_empty_dataframe() -> None:
    """Test get_daily_data returns empty DataFrame when data is empty."""
    source = AkShareDataSource()

    with patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True):
        with patch("ditto_core.data.datasources.akshare.ak") as mock_ak:
            # Return empty DataFrame
            mock_df = MagicMock()
            mock_df.empty = True
            mock_ak.stock_zh_a_hist.return_value = mock_df

            result = source.get_daily_data("510300", "2024-01-01", "2024-01-31")

            assert isinstance(result, pl.DataFrame)
            assert len(result) == 0
            expected_columns = [
                "symbol",
                "trade_date",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
                "amount",
                "knowledge_date",
            ]
            for col in expected_columns:
                assert col in result.columns


def test_akshare_get_daily_data_sh_prefix() -> None:
    """Test get_daily_data with SH prefix symbol."""
    source = AkShareDataSource()

    with patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True):
        with patch("ditto_core.data.datasources.akshare.ak") as mock_ak:
            # Mock DataFrame with Chinese column names
            import pandas as pd

            mock_df = pd.DataFrame(
                {
                    "日期": ["2024-01-01"],
                    "开盘": [3.0],
                    "最高": [3.5],
                    "最低": [2.5],
                    "收盘": [3.2],
                    "成交量": [1000000],
                    "成交额": [3200000],
                }
            )
            mock_ak.stock_zh_a_hist.return_value = mock_df

            result = source.get_daily_data("SH510300", "2024-01-01", "2024-01-31")

            assert isinstance(result, pl.DataFrame)
            assert len(result) == 1
            assert result["symbol"][0] == "SH510300"


def test_akshare_get_adjustment_factors_empty_result() -> None:
    """Test get_adjustment_factors with empty date range."""
    source = AkShareDataSource()

    # Test with start_date > end_date
    result = source.get_adjustment_factors("510300", "2024-01-31", "2024-01-01")

    assert isinstance(result, pl.DataFrame)
    assert len(result) == 0
    expected_columns = ["symbol", "ex_date", "adj_factor", "adj_type", "knowledge_date"]
    for col in expected_columns:
        assert col in result.columns


def test_akshare_unexpected_exception_in_connect() -> None:
    """Test connect method with unexpected exception."""
    source = AkShareDataSource()

    # AkShare doesn't require connection, should always return True
    assert source.connect() is True


def test_akshare_disconnect() -> None:
    """Test disconnect method."""
    source = AkShareDataSource()
    # Disconnect should not raise any error
    source.disconnect()  # Should pass without error
