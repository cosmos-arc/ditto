"""Tests for task factory functions.

This module tests the factory functions that create Prefect tasks for data ingestion.
The factories are lightweight wrappers that delegate to IngestionCoordinator.
"""

import pytest
from ditto_port.ingestion.config.datasets import (
    DATASET_REGISTRY,
    Dataset,
    TaskTier,
)
from ditto_port.ingestion.services.coordinator import (
    IngestionResult,
)
from ditto_port.ingestion.tasks import (
    t0_meta,
    t1_adj_factor,
    t1_bars,
)
from ditto_port.ingestion.tasks.t0_meta import create_ingest_task


class TestCreateIngestTask:
    """Tests for create_ingest_task factory function."""

    def test_create_task_returns_callable(self):
        """Test that create_ingest_task returns a callable."""
        # Create a task for calendar dataset
        task_func = create_ingest_task(Dataset.CALENDAR)

        # Should be callable
        assert callable(task_func)

    def test_task_uses_registry_config(self):
        """Test that task uses config from DATASET_REGISTRY."""
        # Create tasks for different datasets
        calendar_task = create_ingest_task(Dataset.CALENDAR)
        etf_daily_task = create_ingest_task(Dataset.ETF_DAILY)

        # Tasks should have names based on dataset
        assert calendar_task.name == f"ingest_{Dataset.CALENDAR.value}"
        assert etf_daily_task.name == f"ingest_{Dataset.ETF_DAILY.value}"

    @pytest.mark.parametrize(
        ("dataset", "expected_retry_limit"),
        [
            (Dataset.CALENDAR, 3),
            (Dataset.STOCK_DAILY, 3),
            (Dataset.ADJ_FACTOR, 3),
        ],
    )
    def test_task_retry_limit_from_registry(self, dataset, expected_retry_limit):
        """Test that task retry_limit matches DATASET_REGISTRY config."""
        task_func = create_ingest_task(dataset)

        # Prefect task should have correct retries
        assert task_func.retries == expected_retry_limit

    @pytest.mark.parametrize(
        ("dataset", "expected_timeout"),
        [
            (Dataset.CALENDAR, 60),
            (Dataset.STOCK_DAILY, 600),
            (Dataset.ADJ_FACTOR, 300),
        ],
    )
    def test_task_timeout_from_registry(self, dataset, expected_timeout):
        """Test that task timeout_seconds matches DATASET_REGISTRY config."""
        task_func = create_ingest_task(dataset)

        # Prefect task should have correct timeout
        assert task_func.timeout_seconds == expected_timeout

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

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch(
            "ditto_server.ingestion.services.coordinator.IngestionCoordinator",
            return_value=mock_coordinator,
        )

        # Call task
        result = task_func.fn(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
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

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch(
            "ditto_server.ingestion.services.coordinator.IngestionCoordinator",
            return_value=mock_coordinator,
        )

        # Call task
        task_func.fn(
            trade_date="2024-01-02",
            source="tushare",
            data_root="data",
            force=False,
        )

        # Verify hub.close() was called even on success
        mock_hub.close.assert_called_once()

    def test_task_closes_hub_on_exception(self, mocker):
        """Test that task closes DataHub even when exception occurs."""
        # Create task
        task_func = create_ingest_task(Dataset.CALENDAR)

        # Mock DataHub
        mock_hub = mocker.Mock()

        mock_source = mocker.Mock()
        mock_hub.sources.get.return_value = mock_source

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch(
            "ditto_server.ingestion.services.coordinator.IngestionCoordinator",
            side_effect=Exception("Coordinator error"),
        )

        # Call task - should raise exception
        with pytest.raises(Exception, match="Coordinator error"):
            task_func.fn(
                trade_date="2024-01-02",
                source="tushare",
                data_root="data",
                force=False,
            )

        # Verify hub.close() was called even on exception
        mock_hub.close.assert_called_once()


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


class TestT1IncrementalTasks:
    """Tests for T1 incremental tasks."""

    def test_t1_incremental_tasks_exist(self):
        """Test that all T1 incremental tasks are exported."""
        # Check that factory functions exist
        assert hasattr(t1_bars, "create_ingest_task")
        assert hasattr(t1_adj_factor, "create_ingest_task")

    @pytest.mark.parametrize(
        "dataset",
        [
            Dataset.ETF_DAILY,
            Dataset.STOCK_DAILY,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
        ],
    )
    def test_t1_datasets_in_registry(self, dataset):
        """Test that all T1 datasets are in DATASET_REGISTRY."""
        assert dataset in DATASET_REGISTRY
        assert DATASET_REGISTRY[dataset].tier == TaskTier.T1_INCREMENTAL


class TestTaskIntegration:
    """Integration tests for task factory with real registry."""

    def test_all_registered_datasets_have_tasks(self):
        """Test that all datasets in registry can create tasks."""
        # Try creating tasks for all datasets
        for dataset in DATASET_REGISTRY:
            task_func = create_ingest_task(dataset)
            assert callable(task_func)
            assert task_func.name == f"ingest_{dataset.value}"

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

        mocker.patch("ditto_datahub.DataHub", return_value=mock_hub)
        mocker.patch(
            "ditto_server.ingestion.services.coordinator.IngestionCoordinator",
            return_value=mock_coordinator,
        )

        # Call with different parameter combinations
        result1 = task_func.fn(
            trade_date="2024-01-02",
            source="tushare",
            data_root="/data",
            force=True,
        )

        result2 = task_func.fn(
            trade_date="2024-01-03",
            source="akshare",
            data_root="/data2",
            force=False,
        )

        # Verify both calls succeeded
        assert result1["status"] == "success"
        assert result2["status"] == "success"
        assert mock_coordinator.ingest_date.call_count == 2
