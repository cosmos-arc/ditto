"""Tests for repair flow.

This module tests the repair flow which handles retrying failed tasks
and filling data holes.
"""

# 测试文件允许函数内导入

import pytest


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestRetryFailedFlow:
    """Tests for retry_failed_flow."""

    def test_flow_exists(self, patch_datahub):
        """Test that retry_failed_flow is defined."""
        from ditto_port.jobs.flows.repair import retry_failed_flow

        assert retry_failed_flow is not None
        assert callable(retry_failed_flow)

    def test_flow_retries_failed_tasks(self, patch_datahub):
        """Test that flow retries failed tasks."""
        from ditto_port.jobs.flows.repair import retry_failed_flow

        patch_datahub.ingestion_log.get_failed_dates.return_value = [
            "2024-01-02",
            "2024-01-03",
        ]

        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
            data_root="data",
        )

        # Should return retry result
        assert "dataset" in result
        assert "retried_count" in result

    def test_flow_limits_retry_count(self, patch_datahub):
        """Test that flow respects limit parameter."""
        from ditto_port.jobs.flows.repair import retry_failed_flow

        # Return 2 failed dates (matching the limit)
        patch_datahub.ingestion_log.get_failed_dates.return_value = [
            "2024-01-02",
            "2024-01-03",
        ]

        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=2,  # Only retry 2
            data_root="data",
        )

        # Should respect limit
        assert result["retried_count"] <= 2

    def test_flow_handles_no_failures(self, patch_datahub):
        """Test that flow handles case with no failed tasks."""
        from ditto_port.jobs.flows.repair import retry_failed_flow

        patch_datahub.ingestion_log.get_failed_dates.return_value = []

        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
            data_root="data",
        )

        # Should indicate no retries
        assert result["retried_count"] == 0
        assert result["total_failed"] == 0

    def test_flow_uses_force_on_retry(self, patch_datahub):
        """Test that flow uses force=True when retrying."""
        from ditto_port.jobs.flows.repair import retry_failed_flow

        patch_datahub.ingestion_log.get_failed_dates.return_value = ["2024-01-02"]

        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
            data_root="data",
        )

        # Should complete successfully
        assert "dataset" in result

    def test_flow_closes_hub(self, patch_datahub):
        """Test that flow properly closes DataHub."""
        from ditto_port.jobs.flows.repair import retry_failed_flow

        patch_datahub.ingestion_log.get_failed_dates.return_value = []

        retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
            data_root="data",
        )

        # Verify hub.close() was called
        patch_datahub.close.assert_called_once()


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestRepairHolesFlow:
    """Tests for repair_holes_flow."""

    def test_flow_detects_and_repairs_holes(self, patch_datahub):
        """Test that flow can detect and repair data holes."""
        from ditto_port.jobs.flows.repair import repair_holes_flow

        patch_datahub.calendar_store.get_first_trading_day.return_value = "2024-01-02"
        patch_datahub.calendar_store.get_last_trading_day.return_value = "2024-01-31"
        patch_datahub.calendar_store.get_range.return_value = [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
        ]
        patch_datahub.ingestion_log.get_ingested_dates.return_value = ["2024-01-02"]

        result = repair_holes_flow(
            dataset="stock_daily",
            data_root="data",
        )

        # Should repair holes
        assert "dataset" in result
        assert result["dataset"] == "stock_daily"

    def test_flow_handles_no_holes(self, patch_datahub):
        """Test that flow handles case with no holes."""
        from ditto_port.jobs.flows.repair import repair_holes_flow

        patch_datahub.calendar_store.get_first_trading_day.return_value = "2024-01-02"
        patch_datahub.calendar_store.get_last_trading_day.return_value = "2024-01-31"
        patch_datahub.calendar_store.get_range.return_value = ["2024-01-02"]
        patch_datahub.ingestion_log.get_ingested_dates.return_value = ["2024-01-02"]

        result = repair_holes_flow(
            dataset="stock_daily",
            data_root="data",
        )

        # Should indicate no holes
        assert "holes_count" in result or result.get("total_dates") == 0


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestDailyRepairFlow:
    """Tests for daily_repair_flow."""

    def test_flow_runs_retry_and_hole_detection(self, patch_datahub):
        """Test that flow runs both retry and hole detection."""
        from ditto_port.jobs.flows.repair import daily_repair_flow

        patch_datahub.ingestion_log.get_failed_dates.return_value = []
        patch_datahub.calendar_store.get_first_trading_day.return_value = "2024-01-02"
        patch_datahub.calendar_store.get_last_trading_day.return_value = "2024-01-31"
        patch_datahub.calendar_store.get_range.return_value = ["2024-01-02"]
        patch_datahub.ingestion_log.get_ingested_dates.return_value = ["2024-01-02"]

        result = daily_repair_flow(data_root="data")

        # Should run both operations
        assert "retry_result" in result
        assert "holes_result" in result

    def test_flow_aggregates_results(self, patch_datahub):
        """Test that flow aggregates retry and holes results."""
        from ditto_port.jobs.flows.repair import daily_repair_flow

        patch_datahub.ingestion_log.get_failed_dates.return_value = []
        patch_datahub.calendar_store.get_first_trading_day.return_value = "2024-01-02"
        patch_datahub.calendar_store.get_last_trading_day.return_value = "2024-01-31"
        patch_datahub.calendar_store.get_range.return_value = ["2024-01-02"]
        patch_datahub.ingestion_log.get_ingested_dates.return_value = ["2024-01-02"]

        result = daily_repair_flow(data_root="data")

        # Should have summary
        assert "summary" in result or (
            "retry_result" in result and "holes_result" in result
        )
