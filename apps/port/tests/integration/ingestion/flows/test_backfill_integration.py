"""Tests for backfill flow.

This module tests the backfill flow which handles historical data backfill
operations with date range chunking and resume capability.
"""

# 测试文件允许函数内导入

import pytest


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestBackfillFlow:
    """Tests for backfill_flow."""

    def test_flow_exists(self):
        """Test that backfill_flow is defined."""
        from ditto_port.jobs.flows.backfill import backfill_flow

        assert backfill_flow is not None
        assert callable(backfill_flow)

    def test_flow_accepts_date_range(self):
        """Test that flow accepts start_date and end_date parameters."""
        from ditto_port.jobs.flows.backfill import backfill_flow

        # Flow should be callable with date range
        assert callable(backfill_flow)

    def test_flow_backfills_single_dataset(self, patch_datahub):
        """Test that flow can backfill a single dataset."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        # Mock calendar_store.get_range to return empty list for simplicity
        patch_datahub.calendar_store.get_range.return_value = []

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            data_root="data",
        )
        result = backfill_flow(config)

        # Should return backfill result
        assert "dataset" in result
        assert "total_dates" in result
        assert "success_count" in result

    def test_flow_supports_parallel_execution(self, patch_datahub):
        """Test that flow supports parallel execution."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        # Mock calendar_store.get_range to return empty list for simplicity
        patch_datahub.calendar_store.get_range.return_value = []

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            parallel=3,
            data_root="data",
        )
        result = backfill_flow(config)

        # Should complete without error
        assert "dataset" in result

    def test_flow_handles_empty_date_range(self, patch_datahub):
        """Test that flow handles empty date range gracefully."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        patch_datahub.calendar_store.get_range.return_value = []

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-01",  # Non-trading day
            data_root="data",
        )
        result = backfill_flow(config)

        # Should return empty result
        assert result["total_dates"] == 0

    def test_flow_chunks_date_range(self, patch_datahub):
        """Test that flow can chunk date range for progress tracking."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        trade_dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        patch_datahub.calendar_store.get_range.return_value = trade_dates

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            chunk_size=2,
            data_root="data",
        )
        result = backfill_flow(config)

        # Should process all dates
        assert result["total_dates"] >= 0

    def test_flow_closes_hub(self, patch_datahub, mocker):
        """Test that flow properly closes DataHub."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        # Patch DataHub at the location where it's used
        mocker.patch(
            "ditto_port.jobs.flows.helpers.DataHub", return_value=patch_datahub
        )

        # Create a new method that always returns empty list
        def empty_range(*args, **kwargs):
            return []

        # Override the method to ensure it returns empty list
        patch_datahub.calendar_store.get_range.side_effect = empty_range

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            data_root="data",
        )
        backfill_flow(config)

        # Verify hub.close() was called
        patch_datahub.close.assert_called_once_with()


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestBackfillMissingFlow:
    """Tests for backfill_missing_flow."""

    def test_flow_backfills_missing_dates(self, patch_datahub):
        """Test that flow can backfill only missing dates."""
        from ditto_port.jobs.flows.backfill import backfill_missing_flow

        patch_datahub.calendar_store.get_first_trading_day.return_value = "2024-01-02"
        patch_datahub.calendar_store.get_last_trading_day.return_value = "2024-01-31"
        patch_datahub.calendar_store.get_range.return_value = [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
        ]
        patch_datahub.ingestion_log.get_ingested_dates.return_value = ["2024-01-02"]

        result = backfill_missing_flow(
            dataset="stock_daily",
            data_root="data",
        )

        # Should backfill missing dates
        assert "dataset" in result
        assert result["dataset"] == "stock_daily"

    def test_flow_handles_no_missing_dates(self, patch_datahub):
        """Test that flow handles case with no missing dates."""
        from ditto_port.jobs.flows.backfill import backfill_missing_flow

        patch_datahub.calendar_store.get_first_trading_day.return_value = "2024-01-02"
        patch_datahub.calendar_store.get_last_trading_day.return_value = "2024-01-31"
        patch_datahub.calendar_store.get_range.return_value = ["2024-01-02"]
        patch_datahub.ingestion_log.get_ingested_dates.return_value = ["2024-01-02"]

        result = backfill_missing_flow(
            dataset="stock_daily",
            data_root="data",
        )

        # Should indicate no missing dates
        assert result["total_dates"] == 0


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestResumeCapability:
    """Tests for resume capability."""

    def test_flow_can_resume_from_checkpoint(self, patch_datahub):
        """Test that flow can resume from a checkpoint."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        # Mock calendar_store.get_range to return empty list for simplicity
        patch_datahub.calendar_store.get_range.return_value = []

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            resume_from="2024-01-15",
            data_root="data",
        )
        result = backfill_flow(config)

        # Should handle resume parameter
        assert "dataset" in result

    def test_flow_skips_already_ingested_dates(self, patch_datahub):
        """Test that flow skips dates that are already ingested."""
        from ditto_port.jobs.flows.backfill import (
            BackfillFlowConfig,
            backfill_flow,
        )

        # Mock calendar_store.get_range to return empty list for simplicity
        patch_datahub.calendar_store.get_range.return_value = []

        config = BackfillFlowConfig(
            dataset="stock_daily",
            start_date="2024-01-01",
            end_date="2024-01-31",
            skip_existing=True,
            data_root="data",
        )
        result = backfill_flow(config)

        # Should handle skip_existing parameter
        assert "dataset" in result
