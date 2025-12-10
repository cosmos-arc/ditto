"""Tests for AkShare data source implementation."""

import time
from unittest.mock import Mock, patch

import pytest
import requests
from ditto_core.data.datasources.akshare import AkShareDataSource
from ditto_core.data.exceptions import NetworkError, ValidationError


class TestAkShareDataSource:
    """Test AkShare data source."""

    def test_init_without_akshare(self) -> None:
        """Test initialization when akshare is not available."""
        with patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", False):
            with pytest.raises(ImportError, match="AkShare not available"):
                AkShareDataSource()

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_init_with_config(self, mock_ak: Mock) -> None:
        """Test initialization with custom config."""
        config = {"min_request_interval": 1.0}
        source = AkShareDataSource(config)
        assert source.min_request_interval == 1.0
        assert source.last_request_time == 0.0

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_connect(self, mock_ak: Mock) -> None:
        """Test connect method."""
        source = AkShareDataSource()
        assert source.connect() is True

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", False)
    def test_connect_without_akshare(self) -> None:
        """Test connect when akshare is not available."""
        # We need to patch at import level for this test
        with patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", False):
            # When AKSHARE_AVAILABLE is False, init raises ImportError
            # So we can't even create the instance
            with pytest.raises(ImportError):
                AkShareDataSource()

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_disconnect(self, mock_ak: Mock) -> None:
        """Test disconnect method."""
        source = AkShareDataSource()
        # Disconnect should not raise any errors
        source.disconnect()

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_rate_limit(self, mock_ak: Mock) -> None:
        """Test rate limiting functionality."""
        config = {"min_request_interval": 0.1}
        source = AkShareDataSource(config)

        # First call should not delay
        start_time = time.time()
        source._rate_limit()
        first_call_time = time.time() - start_time

        # Second immediate call should delay
        start_time = time.time()
        source._rate_limit()
        second_call_time = time.time() - start_time

        # Second call should take longer due to rate limiting
        assert second_call_time >= 0.1

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_etf_list_empty_data(self, mock_ak: Mock) -> None:
        """Test get_etf_list when AkShare returns empty data."""
        # Mock empty DataFrame
        mock_ak.fund_etf_category_sina.return_value = None

        source = AkShareDataSource()
        result = source.get_etf_list()

        # Should return empty DataFrame with correct schema
        assert result.shape == (0, 5)
        assert "symbol" in result.columns
        assert "name" in result.columns

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_etf_list_network_error(self, mock_ak: Mock) -> None:
        """Test get_etf_list when network error occurs."""
        mock_ak.fund_etf_category_sina.side_effect = (
            requests.exceptions.RequestException("Network error")
        )

        source = AkShareDataSource()

        with pytest.raises(NetworkError, match="Failed to connect to AkShare"):
            source.get_etf_list()

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_etf_list_validation_error(self, mock_ak: Mock) -> None:
        """Test get_etf_list when validation error occurs."""
        mock_ak.fund_etf_category_sina.side_effect = KeyError("Missing key")

        source = AkShareDataSource()

        with pytest.raises(ValidationError, match="Invalid data format from AkShare"):
            source.get_etf_list()

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_etf_list_success(self, mock_ak: Mock) -> None:
        """Test successful ETF list retrieval."""
        import pandas as pd

        # Mock successful response
        mock_data = pd.DataFrame(
            {
                "代码": ["510300", "510500"],
                "名称": ["沪深300ETF", "中证500ETF"],
                "基金管理人": ["华夏基金", "南方基金"],
                "跟踪标的": ["沪深300指数", "中证500指数"],
                "成立日期": ["2012-05-04", "2013-03-15"],
            }
        )
        mock_ak.fund_etf_category_sina.return_value = mock_data

        source = AkShareDataSource()
        result = source.get_etf_list()

        # Check column names are renamed correctly
        assert list(result.columns) == [
            "symbol",
            "name",
            "fund_manager",
            "tracking_index",
            "establishment_date",
        ]
        assert len(result) == 2
        assert result[0, "symbol"] == "510300"

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_daily_data_sh_prefix(self, mock_ak: Mock) -> None:
        """Test get_daily_data with SH prefix symbol."""
        import pandas as pd

        # Mock successful response
        mock_data = pd.DataFrame(
            {
                "日期": ["2024-01-01", "2024-01-02"],
                "开盘": [3.0, 3.1],
                "最高": [3.2, 3.3],
                "最低": [2.9, 3.0],
                "收盘": [3.1, 3.2],
                "成交量": [1000000, 1100000],
                "成交额": [3100000, 3520000],
            }
        )

        # Test SH prefix handling
        mock_ak.stock_zh_a_hist.return_value = mock_data

        source = AkShareDataSource()
        result = source.get_daily_data("SH000001", "2024-01-01", "2024-01-02")

        # Verify SH prefix is handled correctly (prefix removed for API call)
        mock_ak.stock_zh_a_hist.assert_called_with(
            symbol="000001",
            period="daily",
            start_date="20240101",
            end_date="20240102",
            adjust="",
        )

        # Check result structure
        assert "knowledge_date" in result.columns
        assert result[0, "symbol"] == "SH000001"

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_daily_data_no_prefix(self, mock_ak: Mock) -> None:
        """Test get_daily_data without prefix symbol."""
        import pandas as pd

        # Mock successful response
        mock_data = pd.DataFrame(
            {
                "日期": ["2024-01-01"],
                "开盘": [3.0],
                "最高": [3.2],
                "最低": [2.9],
                "收盘": [3.1],
                "成交量": [1000000],
                "成交额": [3100000],
            }
        )
        mock_ak.stock_zh_a_hist.return_value = mock_data

        source = AkShareDataSource()
        result = source.get_daily_data("000001", "2024-01-01", "2024-01-02")

        # Verify symbol is used as-is
        mock_ak.stock_zh_a_hist.assert_called_with(
            symbol="000001",
            period="daily",
            start_date="20240101",
            end_date="20240102",
            adjust="",
        )

        # Check result structure
        assert result[0, "symbol"] == "000001"

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_daily_data_empty_response(self, mock_ak: Mock) -> None:
        """Test get_daily_data when AkShare returns empty response."""
        # Mock None return
        mock_ak.stock_zh_a_hist.return_value = None

        source = AkShareDataSource()
        result = source.get_daily_data("SH000001", "2024-01-01", "2024-01-02")

        # Should return empty DataFrame with correct schema
        assert result.shape == (0, 9)  # 9 columns including knowledge_date
        assert "symbol" in result.columns
        assert "knowledge_date" in result.columns

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_daily_data_network_error(self, mock_ak: Mock) -> None:
        """Test get_daily_data when network error occurs."""
        mock_ak.stock_zh_a_hist.side_effect = requests.exceptions.RequestException(
            "Network error"
        )

        source = AkShareDataSource()

        with pytest.raises(NetworkError, match="Failed to connect to AkShare"):
            source.get_daily_data("SH000001", "2024-01-01", "2024-01-02")

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_adjustment_factors(self, mock_ak: Mock) -> None:
        """Test get_adjustment_factors method."""
        source = AkShareDataSource()
        result = source.get_adjustment_factors("SH000001", "2024-01-01", "2024-01-03")

        # Should return DataFrame with all factors as 1.0
        assert len(result) == 3  # 3 days
        assert all(result["adj_factor"] == 1.0)
        assert result[0, "symbol"] == "SH000001"
        assert result[0, "ex_date"] == "2024-01-01"

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_adjustment_factors_single_day(self, mock_ak: Mock) -> None:
        """Test get_adjustment_factors for single day."""
        source = AkShareDataSource()
        result = source.get_adjustment_factors("SH000001", "2024-01-01", "2024-01-01")

        # Should return single day
        assert len(result) == 1
        assert result[0, "ex_date"] == "2024-01-01"

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_adjustment_factors_validation_error(self, mock_ak: Mock) -> None:
        """Test get_adjustment_factors handles validation errors."""
        from ditto_core.data.exceptions import ValidationError

        source = AkShareDataSource()

        # Test with invalid date format - should raise ValidationError
        with pytest.raises(ValidationError, match="Invalid data format from AkShare"):
            source.get_adjustment_factors("SH000001", "invalid-date", "2024-01-02")

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_unexpected_error_handling(self, mock_ak: Mock) -> None:
        """Test handling of unexpected errors."""
        # Mock unexpected exception
        mock_ak.fund_etf_category_sina.side_effect = Exception("Unexpected error")

        source = AkShareDataSource()

        # Should return empty DataFrame instead of raising
        result = source.get_etf_list()
        assert result.shape == (0, 5)

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_get_source_type(self, mock_ak: Mock) -> None:
        """Test get_source_type method."""
        source = AkShareDataSource()
        assert source._get_source_type() == "akshare"
