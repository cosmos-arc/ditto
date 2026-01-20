"""
Tests for helpers.py context managers.

This module tests the helpers context managers with real dependencies
but mocked data sources.
"""

# 测试文件允许函数内导入

import pytest
from pytest_mock import MockerFixture


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestCreateIngestionContext:
    """Integration tests for create_ingestion_context."""

    def test_context_manager_exists(self):
        """Test that create_ingestion_context is defined."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        assert create_ingestion_context is not None
        assert callable(create_ingestion_context)

    def test_context_creates_datahub(self, patch_datahub):
        """Test that context creates DataHub instance."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="data", source="tushare") as (
            hub,
            coordinator,
        ):
            assert hub is not None
            assert coordinator is not None

    def test_context_provides_coordinator(self, patch_datahub):
        """Test that context provides IngestionCoordinator instance."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="data", source="tushare") as (
            _hub,
            coordinator,
        ):
            assert coordinator is not None
            assert hasattr(coordinator, "ingest_date")

    def test_context_closes_hub_on_success(self, patch_datahub):
        """Test that hub.close() is called on successful completion."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="data", source="tushare") as (
            _hub,
            _coordinator,
        ):
            pass

        # Verify hub.close() was called
        patch_datahub.close.assert_called_once()

    def test_context_closes_hub_on_exception(self, patch_datahub):
        """Test that hub.close() is called even when exception occurs."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with pytest.raises(ValueError, match="Test error"):
            with create_ingestion_context(data_root="data", source="tushare") as (
                _hub,
                _coordinator,
            ):
                raise ValueError("Test error")

        # Verify hub.close() was still called
        patch_datahub.close.assert_called_once()

    def test_context_allows_custom_data_root(self, patch_datahub):
        """Test that context accepts custom data_root parameter."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="/custom/data", source="tushare") as (
            hub,
            _coordinator,
        ):
            assert hub is not None

    def test_context_allows_custom_source(self, patch_datahub):
        """Test that context accepts custom source parameter."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="data", source="custom_source") as (
            _hub,
            _coordinator,
        ):
            # Verify sources.get was called with custom source
            patch_datahub.sources.get.assert_called_with("custom_source")

    def test_context_default_source_is_tushare(self, patch_datahub):
        """Test that default source parameter is 'tushare'."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="data") as (_hub, _coordinator):
            # Verify sources.get was called with default "tushare"
            patch_datahub.sources.get.assert_called_with("tushare")

    def test_context_supports_coordinator_usage(
        self, patch_datahub, mocker: MockerFixture
    ):
        """Test that coordinator can be used within context."""
        # Mock the coordinator's ingest_date method
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        mock_result = mocker.Mock()
        mock_result.status = "success"

        with create_ingestion_context(data_root="data", source="tushare") as (
            _hub,
            coordinator,
        ):
            # Verify coordinator has the expected methods
            assert hasattr(coordinator, "ingest_date")
            assert hasattr(coordinator, "ingest_range")

    def test_multiple_contexts_are_independent(self, patch_datahub):
        """Test that multiple context instances are independent."""
        from ditto_port.jobs.flows.helpers import create_ingestion_context

        with create_ingestion_context(data_root="data1", source="tushare") as (
            hub1,
            _coord1,
        ):
            assert hub1 is not None

        # First hub should be closed after first context exits
        assert patch_datahub.close.call_count == 1

        with create_ingestion_context(data_root="data2", source="tushare") as (
            hub2,
            _coord2,
        ):
            assert hub2 is not None

        # Second call should close the second hub
        assert patch_datahub.close.call_count == 2
