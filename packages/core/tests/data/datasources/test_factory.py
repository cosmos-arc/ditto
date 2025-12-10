"""Unit tests for DataSourceFactory."""

from unittest.mock import MagicMock, patch

import pytest
from ditto_core.data.constants import DataSourceType
from ditto_core.data.datasources.base import DataSource
from ditto_core.data.datasources.factory import DataSourceFactory


class TestDataSourceFactory:
    """Test DataSourceFactory functionality."""

    @patch("ditto_core.data.datasources.tushare.TUSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.tushare.ts")
    def test_create_tushare_data_source(self, mock_ts: MagicMock) -> None:
        """Test creating a Tushare data source."""
        mock_ts.pro_api.return_value = MagicMock()

        source = DataSourceFactory.create(
            DataSourceType.TUSHARE, {"token": "test_token"}
        )

        assert isinstance(source, DataSource)

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_create_akshare_data_source(self, mock_ak: MagicMock) -> None:
        """Test creating an AkShare data source."""
        source = DataSourceFactory.create(
            DataSourceType.AKSHARE, {"min_request_interval": 0.5}
        )

        assert isinstance(source, DataSource)

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_create_data_source_with_no_config(self, mock_ak: MagicMock) -> None:
        """Test creating a data source without configuration."""
        source = DataSourceFactory.create(DataSourceType.AKSHARE)
        assert isinstance(source, DataSource)

    def test_create_unsupported_data_source(self) -> None:
        """Test creating an unsupported data source raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DataSourceFactory.create("unsupported_source")

        assert "Unsupported data source type: unsupported_source" in str(exc_info.value)
        assert "Available types:" in str(exc_info.value)
        assert DataSourceType.TUSHARE in str(exc_info.value)
        assert DataSourceType.AKSHARE in str(exc_info.value)

    def test_register_custom_data_source(self) -> None:
        """Test registering a custom data source."""

        class CustomDataSource(DataSource):
            """Custom data source for testing."""

            def __init__(self, config: dict[str, any] | None = None) -> None:
                super().__init__(config)

            def connect(self) -> bool:
                return True

            def disconnect(self) -> None:
                pass

            def get_etf_list(self) -> any:
                return None

            def _get_source_type(self) -> str:
                return "custom"

            def get_daily_data(
                self, symbol: str, start_date: str, end_date: str
            ) -> any:
                return None

        # Register the custom data source
        DataSourceFactory.register_source("custom", CustomDataSource)

        # Verify it's in the available sources
        available = DataSourceFactory.get_available_sources()
        assert "custom" in available

        # Create an instance
        source = DataSourceFactory.create("custom", {"test": "config"})
        assert isinstance(source, CustomDataSource)

    def test_get_available_sources(self) -> None:
        """Test getting list of available data source types."""
        available = DataSourceFactory.get_available_sources()

        assert isinstance(available, list)
        assert DataSourceType.TUSHARE in available
        assert DataSourceType.AKSHARE in available

    @patch("ditto_core.data.datasources.tushare.TUSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.tushare.ts")
    def test_create_tushare_convenience_method(self, mock_ts: MagicMock) -> None:
        """Test the convenience method for creating Tushare data source."""
        mock_ts.pro_api.return_value = MagicMock()

        source = DataSourceFactory.create_tushare(
            token="test_token", min_request_interval=0.2
        )

        assert isinstance(source, DataSource)

    @patch("ditto_core.data.datasources.akshare.AKSHARE_AVAILABLE", True)
    @patch("ditto_core.data.datasources.akshare.ak")
    def test_create_akshare_convenience_method(self, mock_ak: MagicMock) -> None:
        """Test the convenience method for creating AkShare data source."""
        source = DataSourceFactory.create_akshare(min_request_interval=0.3, timeout=30)

        assert isinstance(source, DataSource)

    def test_create_raises_import_error_for_missing_deps(self) -> None:
        """Test creating a source raises ImportError if dependencies are missing."""
        # This test assumes Tushare is not available in test environment
        with patch("ditto_core.data.datasources.tushare.TUSHARE_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                DataSourceFactory.create(DataSourceType.TUSHARE, {"token": "test"})

            assert "Tushare not available" in str(exc_info.value)
