"""
Tests for data source clients.

This module tests the functionality of data source clients,
including Tushare, AkShare, and the factory pattern with failover.
"""

import asyncio
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import polars as pl
import pytest
from data.clients.akshare_client import AkShareClient
from data.clients.base import DailyData, DataSourceClient, EtfInfo
from data.clients.factory import DataSourceFactory, DataSourceType
from data.clients.tushare_client import TushareClient


class TestDataSourceClient:
    """Test base data source client functionality."""

    @pytest.fixture
    def mock_client(self) -> Any:
        """Create a mock data source client for testing."""
        client = Mock(spec=DataSourceClient)
        client.api_key = "test_key"
        client.config = {}
        return client

    def test_etf_info_creation(self) -> None:
        """Test ETF info data class creation."""
        etf = EtfInfo(
            ts_code="510300.SH",
            symbol="510300",
            name="沪深300ETF",
            manager="华夏基金",
            establish_date=date(2012, 4, 26),
            list_date=date(2012, 5, 7),
            fund_type="ETF",
        )

        assert etf.ts_code == "510300.SH"
        assert etf.symbol == "510300"
        assert etf.name == "沪深300ETF"
        assert etf.tracking_index is None

    def test_daily_data_creation(self) -> None:
        """Test daily data data class creation."""
        data = DailyData(
            ts_code="510300.SH",
            trade_date=date(2024, 1, 2),
            open=3.5,
            high=3.55,
            low=3.48,
            close=3.52,
            pre_close=3.5,
            change=0.02,
            pct_chg=0.57,
            vol=1000000,
            amount=3520000,
            knowledge_date=date(2024, 1, 3),
        )

        assert data.ts_code == "510300.SH"
        assert data.close == 3.52
        assert data.pct_chg == 0.57

    def test_data_quality_validation_empty_data(self) -> None:
        """Test data quality validation with empty data."""
        client = Mock(spec=DataSourceClient)
        client.validate_data_quality = DataSourceClient.validate_data_quality.__get__(
            client
        )

        # Test with empty data
        daily_df = pl.DataFrame()
        adj_df = pl.DataFrame()

        result = asyncio.run(
            client.validate_data_quality("510300.SH", daily_df, adj_df)
        )

        assert result["ts_code"] == "510300.SH"
        assert result["daily_records"] == 0
        assert "No daily data found" in result["issues"]
        assert result["quality_score"] < 100


@pytest.mark.asyncio
class TestTushareClient:
    """Test Tushare client functionality."""

    @pytest.fixture
    def mock_tushare_pro(self) -> Any:
        """Mock Tushare Pro API."""
        mock_pro = Mock()
        return mock_pro

    @pytest.fixture
    def tushare_client(self, mock_tushare_pro: Any) -> Any:
        """Create Tushare client with mocked API."""
        with patch("tushare.pro_api", return_value=mock_tushare_pro):
            client = TushareClient(api_key="test_key")
            return client

    async def test_initialization_with_api_key(self) -> None:
        """Test client initialization with API key."""
        with patch("tushare.pro_api") as mock_pro_api:
            client = TushareClient(api_key="test_key")
            assert client.api_key == "test_key"
            mock_pro_api.assert_called_once()

    def test_initialization_without_api_key(self) -> None:
        """Test client initialization without API key raises error."""
        with pytest.raises(ValueError, match="Tushare API key is required"):
            TushareClient(api_key=None)

    async def test_convert_ts_code_for_akshare(self) -> None:
        """Test TS code conversion for AkShare format."""
        client = AkShareClient()

        # Test Shanghai exchange
        assert client._convert_ts_code("510300.SH") == "sh510300"

        # Test Shenzhen exchange
        assert client._convert_ts_code("159919.SZ") == "sz159919"

        # Test invalid exchange
        with pytest.raises(ValueError, match="Unknown exchange"):
            client._convert_ts_code("510300.XX")


@pytest.mark.asyncio
class TestAkShareClient:
    """Test AkShare client functionality."""

    @pytest.fixture
    def akshare_client(self) -> AkShareClient:
        """Create AkShare client."""
        return AkShareClient()

    def test_initialization(self, akshare_client: AkShareClient) -> None:
        """Test client initialization."""
        assert akshare_client.api_key is None
        assert akshare_client.min_request_interval == 0.5

    async def test_convert_ts_code(self, akshare_client: AkShareClient) -> None:
        """Test TS code conversion."""
        assert akshare_client._convert_ts_code("510300.SH") == "sh510300"
        assert akshare_client._convert_ts_code("159919.SZ") == "sz159919"


@pytest.mark.asyncio
class TestDataSourceFactory:
    """Test data source factory functionality."""

    @pytest.fixture
    def factory_config(self) -> dict[str, Any]:
        """Get factory configuration."""
        return {
            "tushare_api_key": "test_tushare_key",
            "tushare_pro_account": False,
            "tushare_config": {"max_retries": 2},
            "akshare_config": {"min_request_interval": 0.3},
        }

    @pytest.fixture
    def mock_factory(self, factory_config: dict[str, Any]) -> DataSourceFactory:
        """Create factory with mocked clients."""
        factory = DataSourceFactory(
            primary_source=DataSourceType.TUSHARE,
            backup_sources=[DataSourceType.AKSHARE],
            **factory_config,
        )
        return factory

    async def test_factory_initialization(self, factory_config: dict[str, Any]) -> None:
        """Test factory initialization."""
        factory = DataSourceFactory(**factory_config)
        assert factory.primary_source == DataSourceType.TUSHARE
        assert factory.backup_sources == [DataSourceType.AKSHARE]

    async def test_create_tushare_client(self, mock_factory: DataSourceFactory) -> None:
        """Test creating Tushare client."""
        with patch("ditto.data.clients.tushare_client.TushareClient") as mock_client:
            mock_instance = Mock()
            mock_client.return_value = mock_instance

            client = mock_factory._create_client(DataSourceType.TUSHARE)
            assert client == mock_instance
            mock_client.assert_called_once_with(
                api_key="test_tushare_key", pro_account=False, max_retries=2
            )

    async def test_create_akshare_client(self, mock_factory: DataSourceFactory) -> None:
        """Test creating AkShare client."""
        with patch("ditto.data.clients.akshare_client.AkShareClient") as mock_client:
            mock_instance = Mock()
            mock_client.return_value = mock_instance

            client = mock_factory._create_client(DataSourceType.AKSHARE)
            assert client == mock_instance
            mock_client.assert_called_once_with(min_request_interval=0.3)

    async def test_client_caching(self, mock_factory: DataSourceFactory) -> None:
        """Test that clients are cached after creation."""
        with patch("ditto.data.clients.tushare_client.TushareClient") as mock_client:
            mock_instance = Mock()
            mock_client.return_value = mock_instance

            # Create client twice
            client1 = mock_factory._create_client(DataSourceType.TUSHARE)
            client2 = mock_factory._create_client(DataSourceType.TUSHARE)

            # Should return same instance
            assert client1 is client2
            # Should only create once
            mock_client.assert_called_once()

    async def test_try_client_success(self) -> None:
        """Test successful client method call."""
        client = Mock()
        client.method_name = AsyncMock(return_value="success")

        factory = DataSourceFactory()
        result = await factory._try_client(
            client, "method_name", "arg1", kwarg1="value1"
        )

        assert result == "success"
        client.method_name.assert_called_once_with("arg1", kwarg1="value1")

    async def test_try_client_failure(self) -> None:
        """Test client method call failure."""
        client = Mock()
        client.method_name = AsyncMock(side_effect=Exception("Test error"))

        factory = DataSourceFactory()
        result = await factory._try_client(client, "method_name")

        assert result is None

    async def test_validate_data_consistency_empty_data(self) -> None:
        """Test data consistency validation with empty data."""
        factory = DataSourceFactory()

        empty_df = pl.DataFrame()
        single_df = pl.DataFrame({"trade_date": [date(2024, 1, 2)], "close": [3.5]})

        # Should handle empty data gracefully
        result = await factory._validate_data_consistency(empty_df, single_df, "test")
        assert result is True

        result = await factory._validate_data_consistency(single_df, empty_df, "test")
        assert result is True

    async def test_validate_data_consistency_price_differences(self) -> None:
        """Test data consistency validation with price differences."""
        factory = DataSourceFactory()

        primary_data = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "close": [3.50, 3.52],
            }
        )

        # Slightly different prices (within 1% threshold)
        backup_data = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "close": [3.51, 3.53],  # ~0.3% difference
            }
        )

        result = await factory._validate_data_consistency(
            primary_data, backup_data, "daily"
        )
        assert result is True

        # Large price differences
        backup_data_large_diff = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "close": [3.50, 3.80],  # ~8% difference
            }
        )

        result = await factory._validate_data_consistency(
            primary_data, backup_data_large_diff, "daily"
        )
        assert result is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for data clients."""

    @pytest.mark.slow
    async def test_tushare_real_api(self) -> None:
        """Test Tushare client with real API (requires valid API key)."""
        # This test requires a real API key and should be marked as slow
        # It should only run in integration environments
        pytest.skip("Requires Tushare API key - run in integration tests only")

    @pytest.mark.slow
    async def test_akshare_real_api(self) -> None:
        """Test AkShare client with real API."""
        # This test is slow and may be flaky due to external dependencies
        pytest.skip("External API test - run in integration tests only")

    async def test_end_to_end_fetch_with_mock(self) -> None:
        """Test end-to-end data fetching with mocked clients."""
        # Create mock primary client
        primary_client = Mock(spec=DataSourceClient)
        primary_client.get_etf_list = AsyncMock(
            return_value=pl.DataFrame(
                {
                    "ts_code": ["510300.SH", "159919.SZ"],
                    "name": ["沪深300ETF", "沪深300ETF"],
                }
            )
        )

        # Create mock backup client
        backup_client = Mock(spec=DataSourceClient)
        backup_client.get_etf_list = AsyncMock(
            return_value=pl.DataFrame(
                {
                    "ts_code": ["510300.SH", "159919.SZ"],
                    "name": ["沪深300ETF", "沪深300ETF"],
                }
            )
        )

        # Create factory with mocked clients
        factory = DataSourceFactory()
        factory._clients = {
            DataSourceType.TUSHARE: primary_client,
            DataSourceType.AKSHARE: backup_client,
        }

        # Test fetch with failover
        result = await factory.fetch_with_failover("get_etf_list")

        assert result.height == 2
        assert "510300.SH" in result["ts_code"].to_list()
        assert "159919.SZ" in result["ts_code"].to_list()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
