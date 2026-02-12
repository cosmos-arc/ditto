"""
Unit tests for backfill flow.

This module provides unit-level coverage for the backfill flow,
testing individual code paths and branches without full integration setup.

Note: The @flow decorator is mocked in conftest.py to avoid Prefect API server
startup during unit tests.
"""

from __future__ import annotations

import pytest

# Import functions and models directly
# The @flow decorator is mocked in conftest.py, so these are plain functions
from ditto_port.jobs.flows.backfill import (
    BackfillFlowConfig,
    BackfillFlowResult,
    backfill_flow,
    backfill_missing_flow,
)
from pydantic import ValidationError


@pytest.mark.unit
class TestBackfillFlowConfig:
    """Unit tests for BackfillFlowConfig model."""

    def test_config_with_required_fields(self):
        """Test that config accepts required fields."""
        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert config.dataset == "stock_daily"
        assert config.start_date == "2024-01-01"
        assert config.end_date == "2024-01-31"

    def test_config_with_all_fields(self):
        """Test that config accepts all fields."""
        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            source="tushare",
            data_root="data",
            parallel=4,
            chunk_size=20,
            resume_from="2024-01-15",
            skip_existing=True,
        )

        assert config.dataset == "stock_daily"
        assert config.source == "tushare"
        assert config.data_root == "data"
        assert config.parallel == 4
        assert config.chunk_size == 20
        assert config.resume_from == "2024-01-15"
        assert config.skip_existing is True

    def test_config_defaults(self):
        """Test that config has correct defaults."""
        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert config.source == "tushare"
        assert config.data_root == "data"
        assert config.parallel == 1
        assert config.chunk_size == 10
        assert config.resume_from is None
        assert config.skip_existing is False

    def test_config_validates_required_fields(self):
        """Test that config validates required fields."""
        with pytest.raises(ValidationError) as exc_info:
            BackfillFlowConfig(
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("dataset",) for error in errors)

    def test_config_model_dump(self):
        """Test that config can be dumped to dict."""
        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            parallel=2,
        )

        data = config.model_dump()

        assert data["dataset"] == "stock_daily"
        assert data["start_date"] == "2024-01-01"
        assert data["end_date"] == "2024-01-31"
        assert data["parallel"] == 2


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
        """Test that backfill_flow is callable."""
        # In unit tests, @flow decorator is mocked to bypass Prefect API server
        # So we check that the function is callable instead of being a Flow instance
        assert callable(backfill_flow)
        assert backfill_flow.__name__ == "backfill_flow"

    def test_uses_ingestion_context(self, mocker):
        """Test that flow uses create_ingestion_context."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        # Create a mock context manager that returns (metadata_service, coordinator)
        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mock_patch = mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
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

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            source="tushare",
        )
        result = backfill_flow(config)

        # Verify context was created with correct source
        mock_patch.assert_called_once_with(source="tushare")
        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 20

    def test_creates_ingestion_coordinator(self, mocker):
        """Test that flow gets coordinator from context."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
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

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            source="tushare",
        )
        backfill_flow(config)

        # Verify BackfillManager was created with coordinator from context
        mock_manager_cls.assert_called_once()
        call_kwargs = mock_manager_cls.call_args.kwargs
        assert call_kwargs["coordinator"] is mock_coordinator
        assert call_kwargs["metadata_service"] is mock_metadata_service
        assert call_kwargs["ingestion_log_service"] is mock_ingestion_log_service

    def test_creates_backfill_manager(self, mocker):
        """Test that flow creates BackfillManager."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        backfill_flow(config)

        # Verify BackfillManager was created with correct params
        mock_manager_cls.assert_called_once()
        call_kwargs = mock_manager_cls.call_args.kwargs
        assert call_kwargs["coordinator"] is mock_coordinator
        assert call_kwargs["metadata_service"] is mock_metadata_service
        assert call_kwargs["ingestion_log_service"] is mock_ingestion_log_service

    def test_respects_resume_from_parameter(self, mocker):
        """Test that flow overrides start_date when resume_from is provided."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 10
        mock_result.success_count = 10
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.backfill_range.return_value = mock_result

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            resume_from="2024-01-15",
        )
        result = backfill_flow(config)

        # Verify backfill_range was called with resume_from date
        mock_manager.backfill_range.assert_called_once()
        call_kwargs = mock_manager.backfill_range.call_args.kwargs
        assert call_kwargs["start_date"] == "2024-01-15"
        # Result should also show the resumed start_date
        assert result["start_date"] == "2024-01-15"

    def test_passes_parallel_to_backfill_range(self, mocker):
        """Test that flow passes parallel parameter to backfill_range."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
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

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            parallel=4,
        )
        backfill_flow(config)

        # Verify parallel parameter was passed
        call_kwargs = mock_manager.backfill_range.call_args.kwargs
        assert call_kwargs["parallel"] == 4

    def test_returns_result_dict_with_all_keys(self, mocker):
        """Test that flow returns dict with all required keys."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 20
        mock_result.success_count = 18
        mock_result.skipped_count = 1
        mock_result.failed_count = 1
        mock_manager.backfill_range.return_value = mock_result

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        result = backfill_flow(config)

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
        """Test that context manager cleanup happens on successful completion."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
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

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        backfill_flow(config)

        # Verify context manager was properly used
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that context manager cleanup happens even when exception occurs."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        # Mock BackfillManager to raise exception
        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager
        mock_manager.backfill_range.side_effect = ValueError("Test error")

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        with pytest.raises(ValueError, match="Test error"):
            backfill_flow(config)

        # Verify context manager cleanup still happened
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()


@pytest.mark.unit
class TestBackfillMissingFlow:
    """Unit tests for backfill_missing_flow."""

    def test_is_prefect_flow(self):
        """Test that backfill_missing_flow is callable."""
        # In unit tests, @flow decorator is mocked to bypass Prefect API server
        # So we check that the function is callable instead of being a Flow instance
        assert callable(backfill_missing_flow)
        assert backfill_missing_flow.__name__ == "backfill_missing_flow"

    def test_uses_ingestion_context(self, mocker):
        """Test that flow uses create_ingestion_context."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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

        result = backfill_missing_flow(
            dataset="stock_daily",
            source="tushare",
        )

        # Verify context was created and result is correct
        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 5

    def test_creates_ingestion_coordinator(self, mocker):
        """Test that flow gets coordinator from context."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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
            source="tushare",
        )

        # Verify BackfillManager was created with coordinator from context
        mock_manager_cls.assert_called_once()
        call_kwargs = mock_manager_cls.call_args.kwargs
        assert call_kwargs["coordinator"] is mock_coordinator
        assert call_kwargs["metadata_service"] is mock_metadata_service
        assert call_kwargs["ingestion_log_service"] is mock_ingestion_log_service

    def test_creates_backfill_manager(self, mocker):
        """Test that flow creates BackfillManager."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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
        assert "metadata_service" in call_kwargs
        assert "ingestion_log_service" in call_kwargs

    def test_passes_parallel_to_backfill_missing(self, mocker):
        """Test that flow passes parallel parameter to backfill_missing."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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
            parallel=3,
        )

        # Verify parallel parameter was passed
        call_kwargs = mock_manager.backfill_missing.call_args.kwargs
        assert call_kwargs["parallel"] == 3

    def test_returns_result_with_missing_data(self, mocker):
        """Test that flow returns correct result when there are missing dates."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager
        mock_result = mocker.MagicMock()
        mock_result.dataset = "stock_daily"
        mock_result.total_dates = 0
        mock_result.success_count = 0
        mock_result.skipped_count = 0
        mock_result.failed_count = 0
        mock_manager.backfill_missing.return_value = mock_result

        result = backfill_missing_flow(
            dataset="stock_daily",
        )

        # Verify message when no missing data
        assert result["message"] == "没有缺失数据"
        assert result["total_dates"] == 0

    def test_closes_hub_on_success(self, mocker):
        """Test that context manager cleanup happens on successful completion."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

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

        # Verify context manager was properly used
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that context manager cleanup happens even when exception occurs."""
        mock_metadata_service = mocker.MagicMock()
        mock_coordinator = mocker.MagicMock()

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_coordinator,
        )
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        mock_ingestion_log_service = mocker.MagicMock()
        mock_log_context_mgr = mocker.MagicMock()
        mock_log_context_mgr.__enter__.return_value = (
            mock_metadata_service,
            mock_ingestion_log_service,
        )
        mock_log_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.backfill.create_ingestion_log_context",
            return_value=mock_log_context_mgr,
        )

        # Mock BackfillManager to raise exception
        mock_manager_cls = mocker.patch(
            "ditto_port.jobs.flows.backfill.BackfillManager"
        )
        mock_manager = mocker.MagicMock()
        mock_manager_cls.return_value = mock_manager
        mock_manager.backfill_missing.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            backfill_missing_flow(
                dataset="stock_daily",
            )

        # Verify context manager cleanup still happened
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()
