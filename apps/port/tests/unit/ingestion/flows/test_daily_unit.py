"""Unit tests for daily ingestion flow.

This module provides unit-level coverage for the daily ingestion flow,
testing individual code paths and branches without full integration setup.
"""

from __future__ import annotations

import pytest
from ditto_port.ingestion.config.datasets import Dataset
from ditto_port.ingestion.flows.daily import (
    check_trading_day,
    daily_ingestion_flow,
)
from prefect.tasks import Task as PrefectTask


@pytest.mark.unit
class TestCheckTradingDay:
    """Unit tests for check_trading_day task."""

    def test_returns_true_for_trading_day(self, mocker):
        """Test that task returns True for valid trading day."""

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        result = check_trading_day.fn(
            trade_date="2024-01-02",
            data_root="data",
        )

        assert result is True
        mock_hub.calendar.is_trading_day.assert_called_once_with("2024-01-02")
        mock_hub.close.assert_called_once()

    def test_returns_false_for_non_trading_day(self, mocker):
        """Test that task returns False for non-trading day."""

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = False

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        result = check_trading_day.fn(
            trade_date="2024-01-06",
            data_root="data",
        )

        assert result is False
        mock_hub.close.assert_called_once()

    def test_closes_hub_on_exception(self, mocker):
        """Test that hub.close() is called even when is_trading_day raises."""

        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.side_effect = ValueError("Test error")

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        with pytest.raises(ValueError, match="Test error"):
            check_trading_day.fn(
                trade_date="2024-01-02",
                data_root="data",
            )

        # Verify close was still called
        mock_hub.close.assert_called_once()

    def test_is_prefect_task(self, mocker):
        """Test that check_trading_day is a Prefect task."""

        assert isinstance(check_trading_day, PrefectTask)
        assert check_trading_day.name == "check_trading_day"


@pytest.mark.unit
class TestDailyIngestionFlowNonTradingDay:
    """Unit tests for daily_ingestion_flow non-trading day branch."""

    def test_returns_skipped_result_for_non_trading_day(self, mocker):
        """Test that flow returns skipped result for non-trading day."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=False
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-06",
            source="tushare",
            data_root="data",
        )

        assert result["skipped"] is True
        assert result["reason"] == "非交易日"
        assert result["trade_date"] == "2024-01-06"
        assert result["t0_results"] == {}
        assert result["t1_results"] == {}
        assert result["dqc_results"] == {}
        assert result["summary"]["total_tasks"] == 0
        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 0


@pytest.mark.unit
class TestDailyIngestionFlowT0Execution:
    """Unit tests for T0 task execution."""

    def test_executes_t0_datasets(self, mocker):
        """Test that flow executes T0 datasets."""

        # Mock check_trading_day to return True
        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        # Mock get_datasets_by_tier to return T0 datasets
        t0_datasets = [Dataset.CALENDAR, Dataset.STOCK_BASIC]
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=t0_datasets,
        )
        # Mock task creation
        mock_create_task = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_create_task.return_value = mock_task

        # Mock get_parallel_datasets to return empty list
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        # Verify T0 task was created and submitted
        assert mock_create_task.call_count == 2
        assert mock_task.submit.call_count == 2
        assert "calendar" in result["t0_results"]

    def test_handles_empty_t0_datasets(self, mocker):
        """Test that flow handles empty T0 datasets list."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["t0_results"] == {}
        assert result["t1_results"] == {}
        assert result["summary"]["total_tasks"] == 0


@pytest.mark.unit
class TestDailyIngestionFlowT1Execution:
    """Unit tests for T1 task execution."""

    def test_uses_correct_task_factory_for_adj_factor(self, mocker):
        """Test that adj_factor uses create_ingest_task_t1_adj."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        # Mock get_parallel_datasets to return adj_factor in level 0
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.ADJ_FACTOR]],
        )
        mock_t1_adj = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_adj"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "adj_factor",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_adj.return_value = mock_task

        # Mock T0 futures
        mocker.patch("ditto_server.ingestion.flows.daily.create_ingest_task_t0")
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        # Verify t1_adj factory was used for adj_factor
        mock_t1_adj.assert_called_once_with(Dataset.ADJ_FACTOR)
        assert "adj_factor" in result["t1_results"]

    def test_uses_correct_task_factory_for_fund_adj(self, mocker):
        """Test that fund_adj uses create_ingest_task_t1_adj."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.FUND_ADJ]],
        )
        mock_t1_adj = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_adj"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "fund_adj",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_adj.return_value = mock_task

        mocker.patch("ditto_server.ingestion.flows.daily.create_ingest_task_t0")
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        mock_t1_adj.assert_called_once_with(Dataset.FUND_ADJ)
        assert "fund_adj" in result["t1_results"]

    def test_uses_correct_task_factory_for_bars_datasets(self, mocker):
        """Test that bars datasets use create_ingest_task_t1_bars."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.STOCK_DAILY, Dataset.ETF_DAILY]],
        )
        mock_t1_bars = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "stock_daily",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_bars.return_value = mock_task

        mocker.patch("ditto_server.ingestion.flows.daily.create_ingest_task_t0")
        daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        # Verify t1_bars factory was called for both datasets
        assert mock_t1_bars.call_count == 2

    def test_handles_multi_level_t1_dependencies(self, mocker):
        """Test that T1 multi-level dependencies use correct wait_for."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[Dataset.CALENDAR],
        )
        # Mock two levels of T1 datasets
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[
                [Dataset.STOCK_DAILY],  # Level 0
                [Dataset.ADJ_FACTOR],  # Level 1 (depends on Level 0)
            ],
        )
        mock_t0 = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t0"
        )
        mock_t1_bars = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )
        mock_t1_adj = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_adj"
        )
        # Setup mocks
        mock_t0_task = mocker.MagicMock()
        t0_future = mocker.MagicMock()
        t0_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_t0_task.submit.return_value = t0_future
        mock_t0.return_value = mock_t0_task

        mock_t1_bars_task = mocker.MagicMock()
        t1_bars_future = mocker.MagicMock()
        t1_bars_future.result.return_value = {
            "dataset": "stock_daily",
            "status": "success",
        }
        mock_t1_bars_task.submit.return_value = t1_bars_future
        mock_t1_bars.return_value = mock_t1_bars_task

        mock_t1_adj_task = mocker.MagicMock()
        t1_adj_future = mocker.MagicMock()
        t1_adj_future.result.return_value = {
            "dataset": "adj_factor",
            "status": "success",
        }
        mock_t1_adj_task.submit.return_value = t1_adj_future
        mock_t1_adj.return_value = mock_t1_adj_task

        daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        # Verify level 1 (adj_factor) waits for level 0 (stock_daily)
        t1_adj_submit_call = mock_t1_adj_task.submit.call_args
        assert "wait_for" in t1_adj_submit_call.kwargs

    def test_handles_empty_t1_datasets(self, mocker):
        """Test that flow handles empty T1 datasets list."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["t1_results"] == {}


@pytest.mark.unit
class TestDailyIngestionFlowResultAggregation:
    """Unit tests for result aggregation logic."""

    def test_aggregates_success_status(self, mocker):
        """Test that success status is counted correctly."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("success")]],
        )
        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["summary"]["success_count"] == 1
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 0

    def test_aggregates_failed_status(self, mocker):
        """Test that failed status is counted correctly."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("failed")]],
        )
        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "failed",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 1
        assert result["summary"]["skipped_count"] == 0

    def test_aggregates_skipped_status(self, mocker):
        """Test that skipped status is counted correctly."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("skipped")]],
        )
        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "skipped",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 1

    def test_aggregates_mixed_statuses(self, mocker):
        """Test that mixed statuses are counted correctly."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[
                [MockDataset("success"), MockDataset("failed")],
                [MockDataset("skipped")],
            ],
        )
        mock_factory = mocker.patch(
            "ditto_server.ingestion.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.MagicMock()
        mock_future = mocker.MagicMock()
        mock_future.result.side_effect = [
            {"dataset": "test1", "status": "success"},
            {"dataset": "test2", "status": "failed"},
            {"dataset": "test3", "status": "skipped"},
        ]
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["summary"]["success_count"] == 1
        assert result["summary"]["failed_count"] == 1
        assert result["summary"]["skipped_count"] == 1
        assert result["summary"]["total_tasks"] == 3


@pytest.mark.unit
class TestDailyIngestionFlowReturnValue:
    """Unit tests for return value structure."""

    def test_return_value_contains_all_required_keys(self, mocker):
        """Test that return value contains all required keys."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        # Verify all top-level keys
        assert "trade_date" in result
        assert "skipped" in result
        assert "reason" in result
        assert "t0_results" in result
        assert "t1_results" in result
        assert "dqc_results" in result
        assert "summary" in result

        # Verify summary keys
        assert "trade_date" in result["summary"]
        assert "total_tasks" in result["summary"]
        assert "success_count" in result["summary"]
        assert "failed_count" in result["summary"]
        assert "skipped_count" in result["summary"]

    def test_dqc_results_placeholder(self, mocker):
        """Test that DQC results contain placeholder."""

        mocker.patch(
            "ditto_server.ingestion.flows.daily.check_trading_day", return_value=True
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_server.ingestion.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
        )

        assert result["dqc_results"]["status"] == "skipped"
        assert "DQC 检查待实现" in result["dqc_results"]["message"]
        assert result["dqc_results"]["trade_date"] == "2024-01-02"


# Helper class for mocking datasets
class MockDataset:
    """Mock dataset for testing."""

    def __init__(self, status: str):
        self.status_value = status
        self.name = f"mock_{status}"

    def __repr__(self) -> str:
        return f"MockDataset({self.status_value})"
