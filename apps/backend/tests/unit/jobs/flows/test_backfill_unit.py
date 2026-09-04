"""
Unit tests for backfill flow.

This module provides unit-level coverage for the backfill flow,
testing individual code paths and branches without full integration setup.

Note: The @flow decorator is mocked in conftest.py to avoid Prefect API server
startup during unit tests.
"""

from __future__ import annotations

import pytest
from ditto_application.exceptions import AppCommandError

# Import functions and models directly
# The @flow decorator is mocked in conftest.py, so these are plain functions
from ditto_apps.jobs.flows.backfill import (
    BackfillFlowConfig,
    BackfillFlowResult,
    backfill_flow,
    backfill_missing_flow,
    r2_data_product_bootstrap_flow,
    r2_data_product_repair_flow,
)
from pydantic import ValidationError


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


BACKFILL_FLOW_RUNNER = _prefect_runner(backfill_flow)
BACKFILL_MISSING_FLOW_RUNNER = _prefect_runner(backfill_missing_flow)
R2_BOOTSTRAP_FLOW_RUNNER = _prefect_runner(r2_data_product_bootstrap_flow)
R2_REPAIR_FLOW_RUNNER = _prefect_runner(r2_data_product_repair_flow)


def _create_mock_bundle(mocker, mock_backfill_manager):
    """Helper to create a mock IngestionBundle."""
    mock_bundle = mocker.MagicMock()
    mock_bundle.backfill_manager = mock_backfill_manager
    return mock_bundle


def _create_mock_backfill_result(mocker, **overrides):
    """Helper to create a mock backfill result."""
    result = mocker.MagicMock()
    result.dataset = overrides.get("dataset", "stock_daily")
    result.total_dates = overrides.get("total_dates", 20)
    result.success_count = overrides.get("success_count", 20)
    result.skipped_count = overrides.get("skipped_count", 0)
    result.failed_count = overrides.get("failed_count", 0)
    return result


def _setup_bundle_mock(mocker, mock_backfill_manager):
    """Helper to set up the create_ingestion_bundle mock."""
    mock_bundle = _create_mock_bundle(mocker, mock_backfill_manager)

    mock_context_mgr = mocker.MagicMock()
    mock_context_mgr.__enter__.return_value = mock_bundle
    mock_context_mgr.__exit__.return_value = None

    mocker.patch(
        "ditto_apps.jobs.flows.backfill.create_ingestion_bundle",
        return_value=mock_context_mgr,
    )
    return mock_bundle, mock_context_mgr


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
            BackfillFlowConfig(  # type: ignore[call-arg]
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
        assert callable(backfill_flow)
        assert backfill_flow.__name__ == "backfill_flow"  # type: ignore[attr-defined]

    def test_uses_ingestion_bundle(self, mocker):
        """Test that flow uses create_ingestion_bundle."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.return_value = _create_mock_backfill_result(mocker)
        _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            source="tushare",
        )
        result = BACKFILL_FLOW_RUNNER(config)

        # Verify bundle was created with correct source
        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 20

    def test_uses_bundle_backfill_manager(self, mocker):
        """Test that flow uses bundle.backfill_manager directly."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.return_value = _create_mock_backfill_result(mocker)
        mock_bundle, _ = _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            source="tushare",
        )
        BACKFILL_FLOW_RUNNER(config)

        # Verify backfill_manager from bundle was used directly
        mock_manager.backfill_range.assert_called_once()
        assert mock_bundle.backfill_manager is mock_manager

    def test_respects_resume_from_parameter(self, mocker):
        """Test that flow overrides start_date when resume_from is provided."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=10,
            success_count=10,
        )
        _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            resume_from="2024-01-15",
        )
        result = BACKFILL_FLOW_RUNNER(config)

        # Verify backfill_range was called with resume_from date
        mock_manager.backfill_range.assert_called_once()
        call_kwargs = mock_manager.backfill_range.call_args.kwargs
        assert call_kwargs["start_date"] == "2024-01-15"
        # Result should also show the resumed start_date
        assert result["start_date"] == "2024-01-15"

    def test_passes_parallel_to_backfill_range(self, mocker):
        """Test that flow passes parallel parameter to backfill_range."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.return_value = _create_mock_backfill_result(mocker)
        _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            parallel=4,
        )
        BACKFILL_FLOW_RUNNER(config)

        # Verify parallel parameter was passed
        call_kwargs = mock_manager.backfill_range.call_args.kwargs
        assert call_kwargs["parallel"] == 4

    def test_returns_result_dict_with_all_keys(self, mocker):
        """Test that flow returns dict with all required keys."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.return_value = _create_mock_backfill_result(
            mocker,
            success_count=18,
            skipped_count=1,
            failed_count=1,
        )
        _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        result = BACKFILL_FLOW_RUNNER(config)

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
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.return_value = _create_mock_backfill_result(mocker)
        _, mock_context_mgr = _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        BACKFILL_FLOW_RUNNER(config)

        # Verify context manager was properly used
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that context manager cleanup happens even when exception occurs."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_range.side_effect = ValueError("Test error")
        _, mock_context_mgr = _setup_bundle_mock(mocker, mock_manager)

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        with pytest.raises(ValueError, match="Test error"):
            BACKFILL_FLOW_RUNNER(config)

        # Verify context manager cleanup still happened
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()


@pytest.mark.unit
class TestBackfillMissingFlow:
    """Unit tests for backfill_missing_flow."""

    def test_is_prefect_flow(self):
        """Test that backfill_missing_flow is callable."""
        assert callable(backfill_missing_flow)
        assert backfill_missing_flow.__name__ == "backfill_missing_flow"  # type: ignore[attr-defined]

    def test_uses_ingestion_bundle(self, mocker):
        """Test that flow uses create_ingestion_bundle."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=5,
            success_count=5,
        )
        _setup_bundle_mock(mocker, mock_manager)

        result = BACKFILL_MISSING_FLOW_RUNNER(
            dataset="stock_daily",
            source="tushare",
        )

        # Verify result is correct
        assert result["dataset"] == "stock_daily"
        assert result["total_dates"] == 5

    def test_uses_bundle_backfill_manager(self, mocker):
        """Test that flow uses bundle.backfill_manager directly."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=5,
            success_count=5,
        )
        mock_bundle, _ = _setup_bundle_mock(mocker, mock_manager)

        BACKFILL_MISSING_FLOW_RUNNER(
            dataset="stock_daily",
            source="tushare",
        )

        # Verify backfill_manager from bundle was used directly
        mock_manager.backfill_missing.assert_called_once()
        assert mock_bundle.backfill_manager is mock_manager

    def test_passes_parallel_to_backfill_missing(self, mocker):
        """Test that flow passes parallel parameter to backfill_missing."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=5,
            success_count=5,
        )
        _setup_bundle_mock(mocker, mock_manager)

        BACKFILL_MISSING_FLOW_RUNNER(
            dataset="stock_daily",
            parallel=3,
        )

        # Verify parallel parameter was passed
        call_kwargs = mock_manager.backfill_missing.call_args.kwargs
        assert call_kwargs["parallel"] == 3

    def test_returns_result_with_missing_data(self, mocker):
        """Test that flow returns correct result when there are missing dates."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=5,
            success_count=5,
        )
        _setup_bundle_mock(mocker, mock_manager)

        result = BACKFILL_MISSING_FLOW_RUNNER(
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
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=0,
            success_count=0,
            skipped_count=0,
            failed_count=0,
        )
        _setup_bundle_mock(mocker, mock_manager)

        result = BACKFILL_MISSING_FLOW_RUNNER(
            dataset="stock_daily",
        )

        # Verify message when no missing data
        assert result["message"] == "没有缺失数据"
        assert result["total_dates"] == 0

    def test_closes_hub_on_success(self, mocker):
        """Test that context manager cleanup happens on successful completion."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=5,
            success_count=5,
        )
        _, mock_context_mgr = _setup_bundle_mock(mocker, mock_manager)

        BACKFILL_MISSING_FLOW_RUNNER(
            dataset="stock_daily",
        )

        # Verify context manager was properly used
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that context manager cleanup happens even when exception occurs."""
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.side_effect = ValueError("Test error")
        _, mock_context_mgr = _setup_bundle_mock(mocker, mock_manager)

        with pytest.raises(ValueError, match="Test error"):
            BACKFILL_MISSING_FLOW_RUNNER(
                dataset="stock_daily",
            )

        # Verify context manager cleanup still happened
        mock_context_mgr.__enter__.assert_called_once()
        mock_context_mgr.__exit__.assert_called_once()


@pytest.mark.unit
class TestR2DataProductBackfillGuards:
    """R2 job entrypoints must share the exact CLI confirmation boundary."""

    def test_bootstrap_rejects_wrong_confirmation_before_opening_bundle(
        self,
        mocker,
    ):
        create_bundle = mocker.patch(
            "ditto_apps.jobs.flows.backfill.create_ingestion_bundle"
        )
        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        with pytest.raises(AppCommandError, match="confirmation does not match"):
            R2_BOOTSTRAP_FLOW_RUNNER(config, "yes")

        create_bundle.assert_not_called()

    def test_repair_executes_after_exact_confirmation(self, mocker):
        mock_manager = mocker.MagicMock()
        mock_manager.backfill_missing.return_value = _create_mock_backfill_result(
            mocker,
            total_dates=2,
            success_count=2,
        )
        _setup_bundle_mock(mocker, mock_manager)

        result = R2_REPAIR_FLOW_RUNNER(
            "stock_daily",
            "data-product:repair:stock_daily:confirm",
        )

        assert result["success_count"] == 2
        assert result["confirmation_phrase"] == (
            "data-product:repair:stock_daily:confirm"
        )
        mock_manager.backfill_missing.assert_called_once_with(
            dataset="stock_daily",
            source="tushare",
            parallel=1,
        )
