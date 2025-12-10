"""Unit tests for Tushare data source exception handling."""

import time
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
import requests
from ditto_core.data.datasources.tushare import TushareDataSource
from ditto_core.data.exceptions import NetworkError, ValidationError


class TestTushareDataSourceExceptionHandling:
    """Test exception handling in TushareDataSource."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Mock successful connection
        with patch("ditto_core.data.datasources.tushare.ts") as mock_ts:
            self.mock_pro = MagicMock()
            mock_ts.pro_api.return_value = self.mock_pro
            self.source = TushareDataSource({"token": "test_token"})
            self.source._connected = True

    def test_get_etf_list_network_error(self) -> None:
        """Test handling of network errors in get_etf_list."""
        # Mock requests exception
        self.mock_pro.fund_basic.side_effect = requests.exceptions.ConnectionError(
            "Network error"
        )

        with pytest.raises(NetworkError) as exc_info:
            self.source.get_etf_list()

        assert "Failed to connect to Tushare" in str(exc_info.value)
        assert exc_info.value.source == "tushare"

    def test_get_etf_list_validation_error(self) -> None:
        """Test handling of validation errors in get_etf_list."""
        # Mock API response that will cause validation error
        mock_response = pd.DataFrame({"wrong_column": ["value"]})

        self.mock_pro.fund_basic.return_value = mock_response

        with pytest.raises(ValidationError) as exc_info:
            self.source.get_etf_list()

        assert "Invalid data format from Tushare" in str(exc_info.value)
        assert exc_info.value.source == "tushare"

    def test_get_etf_list_unexpected_error_returns_empty_df(self) -> None:
        """Test that unexpected errors return empty DataFrame with correct schema."""
        # Mock unexpected error
        self.mock_pro.fund_basic.side_effect = RuntimeError("Unexpected error")

        result = self.source.get_etf_list()

        # Should return empty DataFrame with correct schema
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
        assert "symbol" in result.columns
        assert "name" in result.columns

    def test_get_daily_data_network_error(self) -> None:
        """Test handling of network errors in get_daily_data."""
        self.mock_pro.daily.side_effect = requests.exceptions.Timeout("Request timeout")

        with pytest.raises(NetworkError) as exc_info:
            self.source.get_daily_data("510300.SH", "20240101", "20240131")

        assert "Failed to connect to Tushare" in str(exc_info.value)
        assert exc_info.value.source == "tushare"
        assert exc_info.value.symbol == "510300.SH"

    def test_get_daily_data_validation_error(self) -> None:
        """Test handling of validation errors in get_daily_data."""
        # Mock invalid response
        mock_response = pd.DataFrame({"invalid_data": ["test"]})

        self.mock_pro.daily.return_value = mock_response

        with pytest.raises(ValidationError) as exc_info:
            self.source.get_daily_data("159919.SZ", "20240101", "20240131")

        assert "Invalid data format from Tushare" in str(exc_info.value)
        assert exc_info.value.source == "tushare"
        assert exc_info.value.symbol == "159919.SZ"

    def test_get_daily_data_unexpected_error_returns_empty_df(self) -> None:
        """Test that unexpected errors return empty DataFrame with correct schema."""
        self.mock_pro.daily.side_effect = Exception("Unexpected error")

        result = self.source.get_daily_data("510300.SH", "20240101", "20240131")

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

    def test_get_adjustment_factors_network_error(self) -> None:
        """Test handling of network errors in get_adjustment_factors."""
        self.mock_pro.adj_factor.side_effect = requests.exceptions.HTTPError(
            "HTTP error"
        )

        with pytest.raises(NetworkError) as exc_info:
            self.source.get_adjustment_factors("510300.SH", "20240101", "20240131")

        assert "Failed to connect to Tushare" in str(exc_info.value)
        assert exc_info.value.source == "tushare"
        assert exc_info.value.symbol == "510300.SH"

    def test_get_adjustment_factors_validation_error(self) -> None:
        """Test handling of validation errors in get_adjustment_factors."""
        mock_response = pd.DataFrame({"malformed": ["data"]})

        self.mock_pro.adj_factor.return_value = mock_response

        with pytest.raises(ValidationError) as exc_info:
            self.source.get_adjustment_factors("159919.SZ", "20240101", "20240131")

        assert "Invalid data format from Tushare" in str(exc_info.value)
        assert exc_info.value.source == "tushare"
        assert exc_info.value.symbol == "159919.SZ"

    def test_get_adjustment_factors_unexpected_error_returns_empty_df(self) -> None:
        """Test that unexpected errors return empty DataFrame with correct schema."""
        self.mock_pro.adj_factor.side_effect = RuntimeError("Unexpected error")

        result = self.source.get_adjustment_factors("510300.SH", "20240101", "20240131")

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
        expected_columns = [
            "symbol",
            "ex_date",
            "adj_factor",
            "adj_type",
            "knowledge_date",
        ]
        for col in expected_columns:
            assert col in result.columns

    @patch("ditto_core.data.datasources.tushare.TUSHARE_AVAILABLE", False)
    def test_tushare_not_available(self) -> None:
        """Test behavior when Tushare is not available."""
        with pytest.raises(ImportError) as exc_info:
            TushareDataSource()

        assert "Tushare not available" in str(exc_info.value)

    def test_rate_limiting(self) -> None:
        """Test that rate limiting is applied."""
        with patch("ditto_core.data.datasources.tushare.ts") as mock_ts:
            mock_ts.pro_api.return_value = MagicMock()
            source = TushareDataSource(
                {"min_request_interval": 0.1, "token": "test_token"}
            )

            # Mock successful API call
            mock_response = pd.DataFrame(
                {
                    "ts_code": ["510300.SH"],
                    "name": ["Test ETF"],
                    "management": ["Test Manager"],
                    "benchmark": ["Test Index"],
                    "establish_date": ["20120101"],
                }
            )

            source.pro.fund_basic.return_value = mock_response

            # Make two calls and measure time
            start_time = time.time()
            source.get_etf_list()
            source.get_etf_list()
            elapsed = time.time() - start_time

            # Should have waited at least 0.1 seconds
            assert elapsed >= 0.1

    def test_connect_method_exception_handling(self) -> None:
        """Test exception handling in connect method."""
        # Test with valid token
        with patch("ditto_core.data.datasources.tushare.ts") as mock_ts:
            source = TushareDataSource({"token": "test_token"})

            # Test successful connection - connect method should not raise
            source.connect()  # Should not raise an exception
