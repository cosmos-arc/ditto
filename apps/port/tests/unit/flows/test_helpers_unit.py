"""Unit tests for helpers.py flow context managers.

This module provides unit-level coverage for the helpers module,
testing the context manager behavior with mocked dependencies.
"""

from __future__ import annotations

import pytest
from ditto_port.jobs.flows.helpers import create_ingestion_context


@pytest.mark.unit
class TestCreateIngestionContext:
    """Unit tests for create_ingestion_context."""

    def test_is_context_manager(self):
        """Test that create_ingestion_context is a context manager."""
        # Check it's a generator-based context manager
        assert hasattr(create_ingestion_context, "__name__")
        assert create_ingestion_context.__name__ == "create_ingestion_context"

    def test_creates_datahub_with_data_root(self, mocker):
        """Test that context creates DataHub with data_root parameter."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mock_dh = mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")

        with create_ingestion_context(data_root="/custom/data", source="tushare") as (
            _hub,
            _coordinator,
        ):
            pass

        # Verify DataHub was created with custom data_root
        mock_dh.assert_called_once_with(data_root="/custom/data")

    def test_gets_data_source_with_source_param(self, mocker):
        """Test that context gets data source with source parameter."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")

        with create_ingestion_context(data_root="data", source="custom_source") as (
            _hub,
            _coordinator,
        ):
            pass

        # Verify sources.get was called with correct source
        mock_hub.sources.get.assert_called_once_with("custom_source")

    def test_creates_ingestion_coordinator(self, mocker):
        """Test that context creates IngestionCoordinator with correct params."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mock_coordinator_cls = mocker.patch(
            "ditto_port.services.ingestion.coordinator.IngestionCoordinator"
        )
        mock_coordinator = mocker.MagicMock()
        mock_coordinator_cls.return_value = mock_coordinator

        with create_ingestion_context(data_root="data", source="tushare") as (
            _hub,
            _coordinator,
        ):
            pass

        # Verify IngestionCoordinator was created with correct params
        mock_coordinator_cls.assert_called_once()
        call_kwargs = mock_coordinator_cls.call_args.kwargs
        assert call_kwargs["hub"] is mock_hub
        assert call_kwargs["source"] is mock_source
        assert call_kwargs["source_name"] == "tushare"

    def test_yields_hub_and_coordinator(self, mocker):
        """Test that context yields hub and coordinator instances."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mock_coordinator_cls = mocker.patch(
            "ditto_port.services.ingestion.coordinator.IngestionCoordinator"
        )
        mock_coordinator = mocker.MagicMock()
        mock_coordinator_cls.return_value = mock_coordinator

        with create_ingestion_context(data_root="data", source="tushare") as (
            hub,
            coordinator,
        ):
            assert hub is mock_hub
            assert coordinator is mock_coordinator

    def test_closes_hub_on_success(self, mocker):
        """Test that hub.close() is called on successful completion."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")

        with create_ingestion_context(data_root="data", source="tushare") as (
            _hub,
            _coordinator,
        ):
            pass

        # Verify hub.close() was called
        mock_hub.close.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that hub.close() is called even when exception occurs."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")

        with pytest.raises(ValueError, match="Test error"):
            with create_ingestion_context(data_root="data", source="tushare") as (
                _hub,
                _coordinator,
            ):
                raise ValueError("Test error")

        # Verify hub.close() was still called
        mock_hub.close.assert_called_once()

    def test_default_source_is_tushare(self, mocker):
        """Test that default source parameter is 'tushare'."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")

        with create_ingestion_context(data_root="data") as (_hub, _coordinator):
            pass

        # Verify sources.get was called with default "tushare"
        mock_hub.sources.get.assert_called_once_with("tushare")

    def test_context_manager_allows_using_coordinator(self, mocker):
        """Test that coordinator can be used within context."""
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mock_coordinator_cls = mocker.patch(
            "ditto_port.services.ingestion.coordinator.IngestionCoordinator"
        )
        mock_coordinator = mocker.MagicMock()
        mock_result = mocker.MagicMock()
        mock_result.status = "success"
        mock_coordinator.ingest_date.return_value = mock_result
        mock_coordinator_cls.return_value = mock_coordinator

        with create_ingestion_context(data_root="data", source="tushare") as (
            _hub,
            coordinator,
        ):
            result = coordinator.ingest_date(
                dataset="stock_daily", trade_date="2024-01-01"
            )

        # Verify coordinator method was called
        mock_coordinator.ingest_date.assert_called_once_with(
            dataset="stock_daily", trade_date="2024-01-01"
        )
        assert result.status == "success"

    def test_multiple_contexts_are_independent(self, mocker):
        """Test that multiple context instances are independent."""
        mock_hub1 = mocker.MagicMock()
        mock_hub2 = mocker.MagicMock()
        mock_source1 = mocker.MagicMock()
        mock_source2 = mocker.MagicMock()
        mock_hub1.sources.get.return_value = mock_source1
        mock_hub2.sources.get.return_value = mock_source2

        mocker.patch("ditto_datahub.DataHub", side_effect=[mock_hub1, mock_hub2])
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")

        with create_ingestion_context(data_root="data1", source="tushare") as (
            hub1,
            _coord1,
        ):
            assert hub1 is mock_hub1

        with create_ingestion_context(data_root="data2", source="tushare") as (
            hub2,
            _coord2,
        ):
            assert hub2 is mock_hub2

        # Verify both hubs were closed
        mock_hub1.close.assert_called_once()
        mock_hub2.close.assert_called_once()
