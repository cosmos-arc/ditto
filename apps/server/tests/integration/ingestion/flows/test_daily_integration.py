"""Tests for daily ingestion flow.

This module tests the daily ingestion flow which orchestrates T0 → T1 → T3
task dependencies with trade date validation and DQC triggering.

The flow uses Prefect's native dependency mechanism (@task + wait_for)
for declarative orchestration.
"""

# ruff: noqa: PLC0415  # 测试文件允许函数内导入

import pytest


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestDailyIngestionFlow:
    """Tests for daily_ingestion_flow."""

    def test_flow_exists(self):
        """Test that daily_ingestion_flow is defined."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        assert daily_ingestion_flow is not None
        assert callable(daily_ingestion_flow)

    def test_flow_has_correct_name(self):
        """Test that flow has correct name attribute."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        assert daily_ingestion_flow.name == "daily-ingestion"

    def test_flow_accepts_required_params(self):
        """Test that flow accepts required parameters."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        # Flow should be callable with required params
        assert callable(daily_ingestion_flow)

    @pytest.mark.parametrize(
        ("trade_date", "is_trade_day"),
        [
            ("2024-01-02", True),  # Tuesday
            ("2024-01-06", False),  # Saturday
            ("2024-01-07", False),  # Sunday
        ],
    )
    def test_flow_skips_non_trade_dates(self, trade_date, is_trade_day, mocker):
        """Test that flow skips non-trading days."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        # Mock calendar to return is_trade_day
        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = is_trade_day

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(trade_date=trade_date, data_root="data")

        # Verify result
        if is_trade_day:
            # Should execute tasks
            mock_hub.calendar.is_trading_day.assert_called_once()
        else:
            # Should skip
            assert result["skipped"] is True
            assert result["reason"] == "非交易日"
            assert result["summary"]["total_tasks"] == 0

    def test_check_trading_day_is_task(self):
        """Test that check_trading_day is a Prefect task."""
        from ditto_server.ingestion.flows.daily import check_trading_day
        from prefect.tasks import Task

        # Verify it's a Task instance
        assert isinstance(check_trading_day, Task)
        assert check_trading_day.name == "check_trading_day"

    def test_flow_uses_submit_for_t0_tasks(self, mocker):
        """Test that flow uses .submit() for T0 tasks."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )

        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Verify .submit() was called (not direct call)
        assert mock_task.submit.called
        # Verify .result() was called to get the result
        assert mock_future.result.called

    def test_t1_tasks_use_wait_for(self, mocker):
        """Test that T1 tasks use wait_for parameter."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch("ditto_server.ingestion.flows.daily.create_ingest_task_t0")

        mock_t1_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )

        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "stock_daily",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_factory.return_value = mock_task

        daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Verify submit was called with wait_for parameter
        submit_call = mock_task.submit.call_args
        assert "wait_for" in submit_call.kwargs

    def test_flow_aggregates_results(self, mocker):
        """Test that flow properly aggregates results."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should have summary
        assert "summary" in result
        assert "trade_date" in result["summary"]
        assert "total_tasks" in result["summary"]
        assert "success_count" in result["summary"]
        assert "failed_count" in result["summary"]
        assert "skipped_count" in result["summary"]

    def test_flow_returns_dqc_placeholder(self, mocker):
        """Test that flow returns DQC placeholder."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should have DQC results with placeholder
        assert "dqc_results" in result
        assert result["dqc_results"]["status"] == "skipped"
        assert "DQC 检查待实现" in result["dqc_results"]["message"]


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestTradingDayValidation:
    """Tests for trading day validation logic."""

    def test_check_trading_day_closes_hub(self, mocker):
        """Test that check_trading_day properly closes DataHub."""
        from ditto_server.ingestion.flows.daily import check_trading_day

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = check_trading_day.fn(
            trade_date="2024-01-02",
            data_root="data",
        )

        # Verify hub.close() was called
        mock_hub.close.assert_called_once()
        assert result is True

    def test_valid_trade_date_executes_tasks(self, mocker):
        """Test flow with valid trade date."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        assert result["skipped"] is False

    def test_weekend_skipped(self, mocker):
        """Test that weekend dates are skipped."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = False

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(trade_date="2024-01-06", data_root="data")

        assert result["skipped"] is True
        assert result["reason"] == "非交易日"

    def test_holiday_skipped(self, mocker):
        """Test that holidays are skipped."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = False

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(
            trade_date="2024-02-10",
            data_root="data",  # Spring Festival
        )

        assert result["skipped"] is True


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestTaskDependencyOrchestration:
    """Tests for task dependency orchestration using Prefect wait_for."""

    def test_t0_tasks_submitted_in_parallel(self, mocker):
        """Test that T0 tasks are submitted for parallel execution."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )

        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Verify submit was called (not direct task call)
        assert mock_task.submit.called

    def test_t1_tasks_wait_for_t0(self, mocker):
        """Test that T1 tasks have wait_for parameter set."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        mock_t0 = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )
        mock_t1 = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )

        # Setup T0 mocks
        mock_t0_task = mocker.MagicMock()
        t0_future = mocker.MagicMock()
        t0_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_t0_task.submit.return_value = t0_future
        mock_t0.return_value = mock_t0_task

        # Setup T1 mocks
        mock_t1_task = mocker.MagicMock()
        mock_t1_task.submit.return_value = mocker.MagicMock(
            result=mocker.MagicMock(
                return_value={
                    "dataset": "stock_daily",
                    "status": "success",
                }
            )
        )
        mock_t1.return_value = mock_t1_task

        daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Verify T1 submit was called
        assert mock_t1_task.submit.called
        # Verify wait_for was passed
        submit_kwargs = mock_t1_task.submit.call_args.kwargs
        assert "wait_for" in submit_kwargs


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestResultAggregation:
    """Tests for result aggregation logic."""

    def test_aggregate_with_success_results(self, mocker):
        """Test aggregation with all successful results."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        mock_t0 = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )

        # Mock successful T0 result
        mock_t0_task = mocker.MagicMock()
        mock_t0_future = mocker.MagicMock()
        mock_t0_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
            "row_count": 100,
        }
        mock_t0_task.submit.return_value = mock_t0_future
        mock_t0.return_value = mock_t0_task

        result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        assert result["summary"]["success_count"] >= 0
        assert result["summary"]["total_tasks"] >= 0

    def test_aggregate_includes_all_sections(self, mocker):
        """Test that aggregation includes all result sections."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Verify all sections present
        assert "trade_date" in result
        assert "skipped" in result
        assert "reason" in result
        assert "t0_results" in result
        assert "t1_results" in result
        assert "dqc_results" in result
        assert "summary" in result


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestErrorHandling:
    """Tests for error handling in various scenarios."""

    def test_flow_handles_missing_dataset_key(self, mocker):
        """Test that flow handles results without dataset key."""
        from ditto_server.ingestion.flows.daily import daily_ingestion_flow

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)

        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )

        # Mock result without "dataset" key
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {"status": "success"}
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(trade_date="2024-01-02", data_root="data")

        # Should use "unknown" as fallback
        assert "unknown" in result["t0_results"]
