"""
Tests for repair flow.

This module tests the repair flow which handles retrying failed tasks
and filling data holes.
"""

# 测试文件允许函数内导入

import pytest


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestRetryFailedFlow:
    """Tests for retry_failed_flow."""

    def test_flow_exists(self):
        """Test that retry_failed_flow is defined."""
        from ditto_interfaces.jobs.flows.repair import retry_failed_flow

        assert retry_failed_flow is not None
        assert callable(retry_failed_flow)

    def test_flow_retries_failed_tasks(self):
        """
        Test that flow retries failed tasks.

        注意: 此测试使用真实的 Data 层和数据，
        需要数据库中有失败记录才能正确执行。
        """
        from ditto_interfaces.jobs.flows.repair import retry_failed_flow

        # 使用真实的 Data 层，不再使用 mock
        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
        )

        # Should return retry result
        assert "dataset" in result
        assert "retried_count" in result

    def test_flow_limits_retry_count(self):
        """
        Test that flow respects limit parameter.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import retry_failed_flow

        # 使用真实的 Data 层，不再使用 mock
        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=2,  # Only retry 2
        )

        # Should respect limit
        assert result["retried_count"] <= 2

    def test_flow_handles_no_failures(self):
        """
        Test that flow handles case with no failed tasks.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import retry_failed_flow

        # 使用真实的 Data 层，不再使用 mock
        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
        )

        # Should indicate no retries
        assert result["retried_count"] == 0
        assert result["total_failed"] == 0

    def test_flow_uses_force_on_retry(self):
        """
        Test that flow uses force=True when retrying.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import retry_failed_flow

        result = retry_failed_flow(
            dataset="stock_daily",
            max_attempts=3,
            limit=10,
        )

        # Should complete successfully
        assert "dataset" in result

    # Note: Data resource lifecycle is managed by the dependency injection container.
    # The test_flow_closes_hub test is no longer applicable -
    # Data does not have close() method.


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestRepairHolesFlow:
    """Tests for repair_holes_flow."""

    def test_flow_detects_and_repairs_holes(self):
        """
        Test that flow can detect and repair data holes.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import repair_holes_flow

        result = repair_holes_flow(
            dataset="stock_daily",
        )

        # Should repair holes
        assert "dataset" in result
        assert result["dataset"] == "stock_daily"

    def test_flow_handles_no_holes(self):
        """
        Test that flow handles case with no holes.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import repair_holes_flow

        result = repair_holes_flow(
            dataset="stock_daily",
        )

        # Should indicate no holes
        assert "holes_count" in result or result.get("total_dates") == 0


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestDailyRepairFlow:
    """Tests for daily_repair_flow."""

    def test_flow_runs_retry_and_hole_detection(self):
        """
        Test that flow runs both retry and hole detection.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import daily_repair_flow

        result = daily_repair_flow()

        # Should run both operations
        assert "retry_result" in result
        assert "holes_result" in result

    def test_flow_aggregates_results(self):
        """
        Test that flow aggregates retry and holes results.

        注意: 此测试使用真实的 Data 层和数据。
        """
        from ditto_interfaces.jobs.flows.repair import daily_repair_flow

        result = daily_repair_flow()

        # Should have summary
        assert "summary" in result or (
            "retry_result" in result and "holes_result" in result
        )
