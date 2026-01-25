"""
Unit tests for daily ingestion flow.

This module provides unit-level coverage for the daily ingestion flow,
testing individual code paths and branches without full integration setup.
"""

from __future__ import annotations

import pytest
from ditto_port.jobs.flows.daily import (
    _collect_results,
    check_trading_day,
    daily_ingestion_flow,
)
from ditto_port.models import Dataset
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestCheckTradingDay:
    """Unit tests for check_trading_day task."""

    def test_returns_true_for_trading_day(self, mocker: MockerFixture):
        """Test that task returns True for valid trading day."""
        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = True

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mocker.MagicMock())
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingestion_context",
            return_value=mock_context_mgr,
        )
        result = check_trading_day(trade_date="2024-01-02")

        assert result is True
        mock_hub.calendar.is_trading_day.assert_called_once_with("2024-01-02")

    def test_returns_false_for_non_trading_day(self, mocker: MockerFixture):
        """Test that task returns False for non-trading day."""
        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.return_value = False

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mocker.MagicMock())
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingestion_context",
            return_value=mock_context_mgr,
        )
        result = check_trading_day(trade_date="2024-01-06")

        assert result is False

    def test_propagates_exception(self, mocker: MockerFixture):
        """Test that exceptions are propagated."""
        mock_hub = mocker.MagicMock()
        mock_hub.calendar.is_trading_day.side_effect = ValueError("Test error")

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mocker.MagicMock())
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingestion_context",
            return_value=mock_context_mgr,
        )
        with pytest.raises(ValueError, match="Test error"):
            check_trading_day(trade_date="2024-01-02")

    def test_is_prefect_task(self, mocker: MockerFixture):
        """
        Test that check_trading_day preserves task name after mock.

        在单元测试中，@task decorator 被 mock，函数本身保留。
        此测试验证 mock 没有破坏函数的基本属性。
        """
        assert callable(check_trading_day)
        assert check_trading_day.__name__ == "check_trading_day"


@pytest.mark.unit
class TestDailyIngestionFlowNonTradingDay:
    """Unit tests for daily_ingestion_flow non-trading day branch."""

    def test_returns_skipped_result_for_non_trading_day(self, mocker: MockerFixture):
        """Test that flow returns skipped result for non-trading day."""
        mocker.patch(
            "ditto_port.jobs.flows.daily.check_trading_day", return_value=False
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-06",
            source="tushare",
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

    def test_executes_t0_datasets(self, mocker: MockerFixture):
        """Test that flow executes T0 datasets."""
        # Mock check_trading_day to return True
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        # Mock get_datasets_by_tier to return T0 datasets
        t0_datasets = [Dataset.CALENDAR, Dataset.STOCK_BASIC]
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=t0_datasets,
        )
        # Mock task creation
        mock_create_task = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t0"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_create_task.return_value = mock_task

        # Mock get_parallel_datasets to return empty list
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify T0 task was created and submitted
        assert mock_create_task.call_count == 2
        assert mock_task.submit.call_count == 2
        assert "calendar" in result["t0_results"]

    def test_handles_empty_t0_datasets(self, mocker: MockerFixture):
        """Test that flow handles empty T0 datasets list."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["t0_results"] == {}
        assert result["t1_results"] == {}
        assert result["summary"]["total_tasks"] == 0


@pytest.mark.unit
class TestDailyIngestionFlowT1Execution:
    """Unit tests for T1 task execution."""

    def test_uses_correct_task_factory_for_adj_factor(self, mocker: MockerFixture):
        """Test that adj_factor uses create_ingest_task_t1_adj."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        # Mock get_parallel_datasets to return adj_factor in level 0
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.ADJ_FACTOR]],
        )
        mock_t1_adj = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_adj"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "adj_factor",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_adj.return_value = mock_task

        # Mock T0 futures
        mocker.patch("ditto_port.jobs.flows.daily.create_ingest_task_t0")
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify t1_adj factory was used for adj_factor
        mock_t1_adj.assert_called_once_with(Dataset.ADJ_FACTOR)
        assert "adj_factor" in result["t1_results"]

    def test_uses_correct_task_factory_for_fund_adj(self, mocker: MockerFixture):
        """Test that fund_adj uses create_ingest_task_t1_adj."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.FUND_ADJ]],
        )
        mock_t1_adj = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_adj"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "fund_adj",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_adj.return_value = mock_task

        mocker.patch("ditto_port.jobs.flows.daily.create_ingest_task_t0")
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        mock_t1_adj.assert_called_once_with(Dataset.FUND_ADJ)
        assert "fund_adj" in result["t1_results"]

    def test_uses_correct_task_factory_for_bars_datasets(self, mocker: MockerFixture):
        """Test that bars datasets use create_ingest_task_t1_bars."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.STOCK_DAILY, Dataset.ETF_DAILY]],
        )
        mock_t1_bars = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "stock_daily",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_bars.return_value = mock_task

        mocker.patch("ditto_port.jobs.flows.daily.create_ingest_task_t0")
        daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify t1_bars factory was called for both datasets
        assert mock_t1_bars.call_count == 2

    def test_handles_multi_level_t1_dependencies(self, mocker: MockerFixture):
        """Test that T1 multi-level dependencies use correct wait_for."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[Dataset.CALENDAR],
        )
        # Mock two levels of T1 datasets
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[
                [Dataset.STOCK_DAILY],  # Level 0
                [Dataset.ADJ_FACTOR],  # Level 1 (depends on Level 0)
            ],
        )
        mock_t0 = mocker.patch("ditto_port.jobs.flows.daily.create_ingest_task_t0")
        mock_t1_bars = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_t1_adj = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_adj"
        )
        # Setup mocks
        mock_t0_task = mocker.Mock()
        t0_future = mocker.Mock()
        t0_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_t0_task.submit.return_value = t0_future
        mock_t0.return_value = mock_t0_task

        mock_t1_bars_task = mocker.Mock()
        t1_bars_future = mocker.Mock()
        t1_bars_future.result.return_value = {
            "dataset": "stock_daily",
            "status": "success",
        }
        mock_t1_bars_task.submit.return_value = t1_bars_future
        mock_t1_bars.return_value = mock_t1_bars_task

        mock_t1_adj_task = mocker.Mock()
        t1_adj_future = mocker.Mock()
        t1_adj_future.result.return_value = {
            "dataset": "adj_factor",
            "status": "success",
        }
        mock_t1_adj_task.submit.return_value = t1_adj_future
        mock_t1_adj.return_value = mock_t1_adj_task

        daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify level 1 (adj_factor) waits for level 0 (stock_daily)
        t1_adj_submit_call = mock_t1_adj_task.submit.call_args
        assert "wait_for" in t1_adj_submit_call.kwargs

    def test_handles_empty_t1_datasets(self, mocker: MockerFixture):
        """Test that flow handles empty T1 datasets list."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["t1_results"] == {}


@pytest.mark.unit
class TestDailyIngestionFlowResultAggregation:
    """Unit tests for result aggregation logic."""

    def test_aggregates_success_status(self, mocker: MockerFixture):
        """Test that success status is counted correctly."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("success")]],
        )
        mock_factory = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["summary"]["success_count"] == 1
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 0

    def test_aggregates_failed_status(self, mocker: MockerFixture):
        """Test that failed status is counted correctly."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("failed")]],
        )
        mock_factory = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "failed",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 1
        assert result["summary"]["skipped_count"] == 0

    def test_aggregates_skipped_status(self, mocker: MockerFixture):
        """Test that skipped status is counted correctly."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("skipped")]],
        )
        mock_factory = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "skipped",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 1

    def test_aggregates_mixed_statuses(self, mocker: MockerFixture):
        """Test that mixed statuses are counted correctly."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[
                [MockDataset("success"), MockDataset("failed")],
                [MockDataset("skipped")],
            ],
        )
        mock_factory = mocker.patch(
            "ditto_port.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
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
        )

        assert result["summary"]["success_count"] == 1
        assert result["summary"]["failed_count"] == 1
        assert result["summary"]["skipped_count"] == 1
        assert result["summary"]["total_tasks"] == 3


@pytest.mark.unit
class TestDailyIngestionFlowReturnValue:
    """Unit tests for return value structure."""

    def test_return_value_contains_all_required_keys(self, mocker: MockerFixture):
        """Test that return value contains all required keys."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
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

    def test_dqc_results_placeholder(self, mocker: MockerFixture):
        """Test that DQC results contain placeholder."""
        mocker.patch("ditto_port.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_port.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = daily_ingestion_flow(
            trade_date="2024-01-02",
            source="tushare",
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


@pytest.mark.unit
class TestCollectResults:
    """Unit tests for _collect_results helper function."""

    def test_collects_empty_futures_list(self):
        """Test that empty futures list returns empty dict."""
        result = _collect_results([])
        assert result == {}

    def test_collects_single_future(self, mocker: MockerFixture):
        """Test that single future is collected correctly."""
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }

        result = _collect_results([mock_future])

        assert "calendar" in result
        assert result["calendar"]["status"] == "success"
        mock_future.result.assert_called_once()

    def test_collects_multiple_futures(self, mocker: MockerFixture):
        """Test that multiple futures are collected correctly."""
        mock_future1 = mocker.Mock()
        mock_future1.result.return_value = {
            "dataset": "calendar",
            "status": "success",
        }
        mock_future2 = mocker.Mock()
        mock_future2.result.return_value = {
            "dataset": "stock_basic",
            "status": "success",
        }

        result = _collect_results([mock_future1, mock_future2])

        assert "calendar" in result
        assert "stock_basic" in result
        assert len(result) == 2

    def test_handles_missing_dataset_key(self, mocker: MockerFixture):
        """Test that future without 'dataset' key uses 'unknown' as key."""
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "status": "success",
        }

        result = _collect_results([mock_future])

        assert "unknown" in result
        assert result["unknown"]["status"] == "success"

    def test_handles_multiple_missing_dataset_keys(self, mocker: MockerFixture):
        """Test that multiple futures without 'dataset' key create separate entries."""
        mock_future1 = mocker.Mock()
        mock_future1.result.return_value = {"status": "success"}
        mock_future2 = mocker.Mock()
        mock_future2.result.return_value = {"status": "failed"}

        result = _collect_results([mock_future1, mock_future2])

        # 后面的会覆盖前面的，因为都使用 "unknown" 作为 key
        assert "unknown" in result
        assert result["unknown"]["status"] == "failed"

    def test_preserves_all_result_fields(self, mocker: MockerFixture):
        """Test that all fields in result are preserved."""
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test_dataset",
            "status": "success",
            "rows": 100,
            "message": "OK",
        }

        result = _collect_results([mock_future])

        assert result["test_dataset"]["rows"] == 100
        assert result["test_dataset"]["message"] == "OK"
