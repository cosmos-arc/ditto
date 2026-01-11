"""Unit tests for backfill flow.

This module provides unit-level coverage for the backfill flow,
testing individual code paths and branches without full integration setup.
"""

from __future__ import annotations

import pytest
from ditto_port.jobs.flows.backfill import (
    BackfillFlowResult,
    backfill_flow,
    backfill_missing_flow,
)
from prefect import Flow


@pytest.mark.unit
class TestBackfillFlowResult:
    """Unit tests for BackfillFlowResult model."""

    def test_model_with_valid_data(self):
        """Test that model accepts valid data."""

        result = BackfillFlowResult(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            total_dates=20,
            success_count=18,
            skipped_count=1,
            failed_count=1,
        )

        assert result.dataset == "stock_daily"
        assert result.start_date == "2024-01-01"
        assert result.end_date == "2024-01-31"
        assert result.total_dates == 20
        assert result.success_count == 18
        assert result.skipped_count == 1
        assert result.failed_count == 1

    def test_model_message_default(self):
        """Test that message field has default empty string."""

        result = BackfillFlowResult(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            total_dates=20,
            success_count=20,
            skipped_count=0,
            failed_count=0,
        )

        assert result.message == ""

    def test_model_with_custom_message(self):
        """Test that model accepts custom message."""

        result = BackfillFlowResult(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            total_dates=20,
            success_count=20,
            skipped_count=0,
            failed_count=0,
            message="All data ingested successfully",
        )

        assert result.message == "All data ingested successfully"


@pytest.mark.unit
class TestBackfillFlow:
    """Unit tests for backfill_flow."""

    def test_is_prefect_flow(self):
        """Test that backfill_flow is a Prefect flow."""

        assert isinstance(backfill_flow, Flow)
        assert backfill_flow.name == "backfill"

    def test_creates_datahub_with_data_root(self, mocker):
        """Test that flow creates DataHub with data_root parameter."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mock_dh = mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 20
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_range.return_value = mock_result

        backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            data_root="/custom/data",
        )

        # Verify DataHub was created with custom data_root
        mock_dh.assert_called_once_with(data_root="/custom/data")

    def test_creates_ingestion_coordinator(self, mocker):
        """Test that flow creates IngestionCoordinator."""

        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mock_coordinator_cls = mocker.patch(
            "ditto_port.services.ingestion.coordinator.IngestionCoordinator"
        )
        mock_coordinator = mocker.MagicMock()
        mock_coordinator_cls.return_value = mock_coordinator

        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 20
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_range.return_value = mock_result

        backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            source="tushare",
        )

        # Verify IngestionCoordinator was created with correct params
        mock_coordinator_cls.assert_called_once()
        call_kwargs = mock_coordinator_cls.call_args.kwargs
        assert call_kwargs["hub"] is mock_hub
        assert call_kwargs["source"] is mock_source
        assert call_kwargs["source_name"] == "tushare"

    def test_creates_backfill_manager(self, mocker):
        """Test that flow creates BackfillManager."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_calendar_store = mocker.MagicMock()
        mock_ingestion_log = mocker.MagicMock()
        mock_hub.calendar_store = mock_calendar_store
        mock_hub.ingestion_log = mock_ingestion_log

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        # Use autospec to properly mock the class
        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager",
            autospec=True,
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager

        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 20
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.backfill_range.return_value = mock_result

        backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Verify BackfillManager was created with correct params
        mock_manager_cls.assert_called_once()
        call_kwargs = mock_manager_cls.call_args.kwargs
        assert "coordinator" in call_kwargs
        assert call_kwargs["calendar_store"] is mock_calendar_store
        assert call_kwargs["ingestion_log_store"] is mock_ingestion_log

    def test_respects_resume_from_parameter(self, mocker):
        """Test that flow overrides start_date when resume_from is provided."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 10
        mock_result.success_count = 10
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_range.return_value = mock_result

        result = backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            resume_from="2024-01-15",
        )

        # Verify backfill_range was called with resume_from date
        mock_manager.return_value.backfill_range.assert_called_once()
        call_kwargs = mock_manager.return_value.backfill_range.call_args.kwargs
        assert call_kwargs["start_date"] == "2024-01-15"
        # Result should also show the resumed start_date
        assert result["start_date"] == "2024-01-15"

    def test_passes_parallel_to_backfill_range(self, mocker):
        """Test that flow passes parallel parameter to backfill_range."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 20
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_range.return_value = mock_result

        backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            parallel=4,
        )

        # Verify parallel parameter was passed
        call_kwargs = mock_manager.return_value.backfill_range.call_args.kwargs
        assert call_kwargs["parallel"] == 4

    def test_returns_result_dict_with_all_keys(self, mocker):
        """Test that flow returns dict with all required keys."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 18
        mock_result.skipped_count = 1
        mock_result.failed_count = 1
        mock_manager.return_value.backfill_range.return_value = mock_result

        result = backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Verify all keys present
        assert "dataset" in result
        assert "start_date" in result
        assert "end_date" in result
        assert "total_dates" in result
        assert "success_count" in result
        assert "skipped_count" in result
        assert "failed_count" in result
        assert "message" in result

        # Verify values
        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 20
        assert result["success_count"] == 18
        assert result["skipped_count"] == 1
        assert result["failed_count"] == 1
        assert "18/20" in result["message"]

    def test_closes_hub_on_success(self, mocker):
        """Test that hub.close() is called on successful completion."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 20
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_range.return_value = mock_result

        backfill_flow(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Verify hub.close() was called
        mock_hub.close.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that hub.close() is called even when exception occurs."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.side_effect = ValueError("Test error")

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        with pytest.raises(ValueError, match="Test error"):
            backfill_flow(
                dataset="stock_daily",
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

        # Verify hub.close() was still called
        mock_hub.close.assert_called_once()


@pytest.mark.unit
class TestBackfillMissingFlow:
    """Unit tests for backfill_missing_flow."""

    def test_is_prefect_flow(self):
        """Test that backfill_missing_flow is a Prefect flow."""

        assert isinstance(backfill_missing_flow, Flow)
        assert backfill_missing_flow.name == "backfill-missing"

    def test_creates_datahub_with_data_root(self, mocker):
        """Test that flow creates DataHub with data_root parameter."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mock_dh = mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 5
        mock_result.success_count = 5
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_missing.return_value = mock_result

        backfill_missing_flow(
            dataset="stock_daily",
            data_root="/custom/data",
        )

        # Verify DataHub was created with custom data_root
        mock_dh.assert_called_once_with(data_root="/custom/data")

    def test_creates_ingestion_coordinator(self, mocker):
        """Test that flow creates IngestionCoordinator."""

        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_hub.sources.get.return_value = mock_source
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mock_coordinator_cls = mocker.patch(
            "ditto_port.services.ingestion.coordinator.IngestionCoordinator"
        )
        mock_coordinator = mocker.MagicMock()
        mock_coordinator_cls.return_value = mock_coordinator

        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 5
        mock_result.success_count = 5
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_missing.return_value = mock_result

        backfill_missing_flow(
            dataset="stock_daily",
            source="tushare",
        )

        # Verify IngestionCoordinator was created with correct params
        mock_coordinator_cls.assert_called_once()
        call_kwargs = mock_coordinator_cls.call_args.kwargs
        assert call_kwargs["hub"] is mock_hub
        assert call_kwargs["source"] is mock_source
        assert call_kwargs["source_name"] == "tushare"

    def test_creates_backfill_manager(self, mocker):
        """Test that flow creates BackfillManager."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_calendar_store = mocker.MagicMock()
        mock_ingestion_log = mocker.MagicMock()
        mock_hub.calendar_store = mock_calendar_store
        mock_hub.ingestion_log = mock_ingestion_log

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager

        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 5
        mock_result.success_count = 5
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.backfill_missing.return_value = mock_result

        backfill_missing_flow(
            dataset="stock_daily",
        )

        # Verify BackfillManager was created with correct params
        mock_manager_cls.assert_called_once()
        call_kwargs = mock_manager_cls.call_args.kwargs
        assert "coordinator" in call_kwargs
        assert call_kwargs["calendar_store"] is mock_calendar_store
        assert call_kwargs["ingestion_log_store"] is mock_ingestion_log

    def test_passes_parallel_to_backfill_missing(self, mocker):
        """Test that flow passes parallel parameter to backfill_missing."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 5
        mock_result.success_count = 5
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_missing.return_value = mock_result

        backfill_missing_flow(
            dataset="stock_daily",
            parallel=3,
        )

        # Verify parallel parameter was passed
        call_kwargs = mock_manager.return_value.backfill_missing.call_args.kwargs
        assert call_kwargs["parallel"] == 3

    def test_returns_result_with_missing_data(self, mocker):
        """Test that flow returns correct result when there are missing dates."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 5
        mock_result.success_count = 5
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_missing.return_value = mock_result

        result = backfill_missing_flow(
            dataset="stock_daily",
        )

        # Verify result structure
        assert "dataset" in result
        assert "total_dates" in result
        assert "success_count" in result
        assert "skipped_count" in result
        assert "failed_count" in result
        assert "message" in result

        # Verify values
        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 5
        assert result["success_count"] == 5
        assert "5/5" in result["message"]

    def test_returns_result_with_no_missing_data(self, mocker):
        """Test that flow returns correct result when there are no missing dates."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 0
        mock_result.success_count = 0
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_missing.return_value = mock_result

        result = backfill_missing_flow(
            dataset="stock_daily",
        )

        # Verify message when no missing data
        assert result["message"] == "没有缺失数据"
        assert result["total_dates"] == 0

    def test_closes_hub_on_success(self, mocker):
        """Test that hub.close() is called on successful completion."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.return_value = mocker.MagicMock()
        mock_hub.calendar_store = mocker.MagicMock()
        mock_hub.ingestion_log = mocker.MagicMock()

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_port.services.ingestion.coordinator.IngestionCoordinator")
        mock_manager = mocker.patch("ditto_port.jobs.flows.backfill.BackfillManager")
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 5
        mock_result.success_count = 5
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.return_value.backfill_missing.return_value = mock_result

        backfill_missing_flow(
            dataset="stock_daily",
        )

        # Verify hub.close() was called
        mock_hub.close.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that hub.close() is called even when exception occurs."""

        mock_hub = mocker.MagicMock()
        mock_hub.sources.get.side_effect = ValueError("Test error")

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        with pytest.raises(ValueError, match="Test error"):
            backfill_missing_flow(
                dataset="stock_daily",
            )

        # Verify hub.close() was still called
        mock_hub.close.assert_called_once()
