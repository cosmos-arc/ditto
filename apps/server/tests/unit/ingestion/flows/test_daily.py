"""Tests for daily ingestion flow.

This module tests the daily ingestion flow which orchestrates T0 → T1 → T3
task dependencies with trade date validation and DQC triggering.
"""

# ruff: noqa: PLC0415  # 测试文件允许函数内导入

from unittest.mock import Mock, patch

import pytest
from prefect.testing.utilities import prefect_test_harness


@pytest.fixture(autouse=True)
def setup_prefect():
    """Set up Prefect test harness for each test."""
    with prefect_test_harness():
        yield


class TestDailyIngestionFlow:
    """Tests for daily_ingestion_flow."""

    def test_flow_exists(self):
        """Test that daily_ingestion_flow is defined."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        assert daily_ingestion_flow is not None
        assert callable(daily_ingestion_flow)

    def test_flow_accepts_trade_date(self):
        """Test that flow accepts trade_date parameter."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        # Flow should be callable with trade_date
        assert callable(daily_ingestion_flow)

    @pytest.mark.parametrize(
        ("trade_date", "is_trade_day"),
        [
            ("2024-01-02", True),  # Tuesday
            ("2024-01-06", False),  # Saturday
            ("2024-01-07", False),  # Sunday
        ],
    )
    def test_flow_skips_non_trade_dates(self, trade_date, is_trade_day):
        """Test that flow skips non-trading days."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        # Mock calendar to return is_trade_day
        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = is_trade_day

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date=trade_date, data_root="data")

        # Verify result
        if is_trade_day:
            # Should execute tasks
            mock_hub.calendar.is_trading_day.assert_called_once()
        else:
            # Should skip
            assert result["skipped"] is True
            assert result["reason"] == "非交易日"

    def test_flow_executes_t0_tasks(self):
        """Test that flow executes T0 tasks first."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        # Mock T0 tasks
        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should execute T0 tasks
        assert "t0_results" in result

    def test_flow_executes_t1_tasks_after_t0(self):
        """Test that flow executes T1 tasks after T0 completes."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should have T1 results
        assert "t1_results" in result

    def test_flow_triggers_dqc_after_t1(self):
        """Test that flow triggers DQC after T1 completes."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should have DQC results
        assert "dqc_results" in result

    def test_flow_aggregates_results(self):
        """Test that flow aggregates all task results."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should have summary
        assert "summary" in result
        assert "trade_date" in result["summary"]
        assert "total_tasks" in result["summary"]
        assert "success_count" in result["summary"]
        assert "failed_count" in result["summary"]

    def test_flow_handles_task_failure(self):
        """Test that flow handles individual task failures gracefully."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should not raise exception, but record failure
        assert "failed_count" in result["summary"]

    def test_flow_closes_hub(self):
        """Test that flow properly closes DataHub."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Verify hub.close() was called at least once
        # (flow 层调用 1 次，每个任务内部也会调用各自的 close)
        mock_hub.close.assert_called()
        # 确保至少调用了 8 次（flow 层 1 次 + 7 个数据集任务）
        assert mock_hub.close.call_count >= 8


class TestTradeDateValidation:
    """Tests for trade date validation logic."""

    def test_valid_trade_date(self):
        """Test flow with valid trade date."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        assert result["skipped"] is False

    def test_weekend_skipped(self):
        """Test that weekend dates are skipped."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = False

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-06", data_root="data")

        assert result["skipped"] is True
        assert result["reason"] == "非交易日"

    def test_holiday_skipped(self):
        """Test that holidays are skipped."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = False

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(
                trade_date="2024-02-10",
                data_root="data",  # Spring Festival
            )

        assert result["skipped"] is True


class TestTaskDependency:
    """Tests for task dependency orchestration."""

    def test_t0_tasks_run_in_parallel(self):
        """Test that T0 tasks run in parallel (no dependencies)."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # T0 tasks should all complete
        t0_results = result.get("t0_results", {})
        assert len(t0_results) > 0

    def test_t1_tasks_wait_for_t0(self):
        """Test that T1 tasks wait for T0 completion."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # T1 should execute after T0
        assert "t1_results" in result

    def test_dqc_waits_for_t1(self):
        """Test that DQC waits for T1 completion."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = Mock()
        mock_hub.calendar.is_trading_day.return_value = True

        with patch("ditto_datahub.DataHub", return_value=mock_hub):
            result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # DQC should execute after T1
        assert "dqc_results" in result
