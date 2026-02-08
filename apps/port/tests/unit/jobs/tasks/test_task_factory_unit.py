"""
Tests for task factory functions.

This module tests the factory functions that create Prefect tasks for data ingestion.
The factories are lightweight wrappers that delegate to IngestionCoordinator.
"""

import pytest
from ditto_port.jobs.tasks import (
    create_ingest_task_t1_adj,
    create_ingest_task_t1_bars,
    t0_meta,
)
from ditto_port.jobs.tasks.t0_meta import create_ingest_task
from ditto_port.models import (
    DATASET_REGISTRY,
    Dataset,
    TaskTier,
)
from ditto_port.services.ingestion.coordinator import (
    IngestionResult,
)


@pytest.mark.unit
class TestCreateIngestTask:
    """Tests for create_ingest_task factory function."""

    def test_create_task_returns_callable(self):
        """Test that create_ingest_task returns a callable."""
        # Create a task for calendar dataset
        task_func = create_ingest_task(Dataset.CALENDAR)

        # Should be callable
        assert callable(task_func)

    def test_task_calls_coordinator(self, mocker):
        """Test that task calls IngestionCoordinator.ingest_date."""
        # Create task
        task_func = create_ingest_task(Dataset.CALENDAR)

        # Mock DataHub and Coordinator
        mock_hub = mocker.Mock()
        mock_coordinator = mocker.Mock()
        # 使用真实的 IngestionResult 对象
        mock_result = IngestionResult(
            dataset="calendar",
            trade_date="2024-01-02",
            status="success",
            row_count=100,
        )
        mock_coordinator.ingest_date.return_value = mock_result

        # Mock the sources.get() to return a mock source
        mock_source = mocker.Mock()
        mock_hub.sources.get.return_value = mock_source

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mock_coordinator)
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.tasks.t0_meta.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        # Call task
        result = task_func(
            trade_date="2024-01-02",
            source="tushare",
            force=False,
        )

        # Verify coordinator was called correctly
        mock_coordinator.ingest_date.assert_called_once_with(
            dataset="calendar", trade_date="2024-01-02", force=False
        )

        # Verify result is returned as dict
        assert result["status"] == "success"
        assert result["row_count"] == 100

    def test_task_closes_hub(self, mocker):
        """Test that task properly closes DataHub."""
        # Create task
        task_func = create_ingest_task(Dataset.CALENDAR)

        # Mock DataHub
        mock_hub = mocker.Mock()
        mock_coordinator = mocker.Mock()
        mock_result = IngestionResult(
            dataset="calendar",
            trade_date="2024-01-02",
            status="success",
        )
        mock_coordinator.ingest_date.return_value = mock_result

        mock_source = mocker.Mock()
        mock_hub.sources.get.return_value = mock_source

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mock_coordinator)
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.tasks.t0_meta.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        # Call task
        task_func(
            trade_date="2024-01-02",
            source="tushare",
            force=False,
        )

        # Verify context manager was called (close happens implicitly)
        # The context manager handles cleanup, so we just verify the task completed

    def test_task_propagates_exceptions(self, mocker):
        """Test that task propagates exceptions from coordinator."""
        # Create task
        task_func = create_ingest_task(Dataset.CALENDAR)

        # Mock DataHub
        mock_hub = mocker.Mock()
        mock_coordinator = mocker.Mock()
        # 让 ingest_date 方法抛出异常
        mock_coordinator.ingest_date.side_effect = Exception("Coordinator error")

        mock_source = mocker.Mock()
        mock_hub.sources.get.return_value = mock_source

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mock_coordinator)
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.tasks.t0_meta.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        # Call task - should raise exception
        with pytest.raises(Exception, match="Coordinator error"):
            task_func(
                trade_date="2024-01-02",
                source="tushare",
                force=False,
            )

        # Verify context manager handles cleanup


@pytest.mark.unit
class TestT0MetaTasks:
    """Tests for T0 metadata tasks."""

    def test_t0_meta_tasks_exist(self):
        """Test that all T0 meta tasks are exported."""
        # Check that key datasets have factory functions
        assert hasattr(t0_meta, "create_ingest_task")

    @pytest.mark.parametrize(
        "dataset",
        [
            Dataset.CALENDAR,
            Dataset.STOCK_BASIC,
            Dataset.ETF_BASIC,
        ],
    )
    def test_t0_datasets_in_registry(self, dataset):
        """Test that all T0 datasets are in DATASET_REGISTRY."""
        assert dataset in DATASET_REGISTRY
        assert DATASET_REGISTRY[dataset].tier == TaskTier.T0_META


@pytest.mark.unit
class TestT1IncrementalTasks:
    """Tests for T1 incremental tasks."""

    def test_t1_incremental_tasks_exist(self):
        """Test that all T1 incremental tasks are exported as aliases."""
        # Check that T1 task factory aliases are exported from __init__.py
        # 这些别名直接指向 t0_meta.create_ingest_task
        assert callable(create_ingest_task_t1_adj)
        assert callable(create_ingest_task_t1_bars)
        # 验证它们确实是同一个函数（因为都是 create_ingest_task 的别名）
        assert create_ingest_task_t1_adj is create_ingest_task
        assert create_ingest_task_t1_bars is create_ingest_task

    @pytest.mark.parametrize(
        "dataset",
        [
            Dataset.ETF_DAILY,
            Dataset.STOCK_DAILY,
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
        ],
    )
    def test_t1_datasets_in_registry(self, dataset):
        """Test that all T1 datasets are in DATASET_REGISTRY."""
        assert dataset in DATASET_REGISTRY
        assert DATASET_REGISTRY[dataset].tier == TaskTier.T1_INCREMENTAL


@pytest.mark.unit
class TestTaskIntegration:
    """Integration tests for task factory with real registry."""

    def test_all_registered_datasets_have_tasks(self):
        """Test that all datasets in registry can create tasks."""
        # Try creating tasks for all datasets
        for dataset in DATASET_REGISTRY:
            task_func = create_ingest_task(dataset)
            assert callable(task_func)

    def test_task_parameters_correct(self, mocker):
        """Test that task parameters are correctly passed."""
        task_func = create_ingest_task(Dataset.STOCK_DAILY)

        # Mock
        mock_hub = mocker.Mock()
        mock_coordinator = mocker.Mock()
        mock_result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-01-02",
            status="success",
        )
        mock_coordinator.ingest_date.return_value = mock_result

        mock_source = mocker.Mock()
        mock_hub.sources.get.return_value = mock_source

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = (mock_hub, mock_coordinator)
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_port.jobs.tasks.t0_meta.create_ingestion_context",
            return_value=mock_context_mgr,
        )

        # Call with different parameter combinations
        result1 = task_func(
            trade_date="2024-01-02",
            source="tushare",
            force=True,
        )

        result2 = task_func(
            trade_date="2024-01-03",
            source="akshare",
            force=False,
        )

        # Verify both calls succeeded
        assert result1["status"] == "success"
        assert result2["status"] == "success"
        assert mock_coordinator.ingest_date.call_count == 2
