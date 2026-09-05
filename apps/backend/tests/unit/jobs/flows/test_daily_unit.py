"""
Unit tests for daily ingestion flow.

This module provides unit-level coverage for the daily ingestion flow,
testing individual code paths and branches without full integration setup.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import ditto_apps.jobs.flows.daily as daily_module
import pytest
from ditto_application.processes.quality.batch import QualityBatchCoordinator
from ditto_application.processes.quality.types import L3CheckResult
from ditto_apps.jobs.flows.daily import (
    _collect_results,
    check_trading_day,
    daily_ingestion_flow,
)
from ditto_data.models import Dataset
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


CHECK_TRADING_DAY_RUNNER = _prefect_runner(check_trading_day)
DAILY_INGESTION_FLOW_RUNNER = _prefect_runner(daily_ingestion_flow)


def _assert_authoritative_dq_evidence(
    first: dict[str, object],
    second: dict[str, object],
    *,
    ingest: MagicMock,
    l3_service: MagicMock,
) -> None:
    first_t1 = first["t1_results"]
    second_t1 = second["t1_results"]
    first_dqc = first["dqc_results"]
    second_dqc = second["dqc_results"]
    assert isinstance(first_t1, dict)
    assert isinstance(second_t1, dict)
    assert isinstance(first_dqc, dict)
    assert isinstance(second_dqc, dict)
    first_stock = first_t1["stock_daily"]
    second_stock = second_t1["stock_daily"]
    first_results = first_dqc["results_by_dataset"]
    second_results = second_dqc["results_by_dataset"]
    assert isinstance(first_stock, dict)
    assert isinstance(second_stock, dict)
    assert isinstance(first_results, dict)
    assert isinstance(second_results, dict)
    stock_quality = second_results["stock_daily"]
    valuation_quality = second_results["valuation_metrics"]
    assert isinstance(stock_quality, dict)
    assert isinstance(valuation_quality, dict)
    assert first_stock["status"] == "success"
    assert second_stock["status"] == "skipped"
    assert first_results == second_results
    assert stock_quality["passed"] is True
    assert valuation_quality["passed"] is True
    assert ingest.call_count == 4
    assert l3_service.check_dataset.call_count == 4
    assert all(
        call.kwargs["market_wide"] is True
        for call in l3_service.check_dataset.call_args_list
    )


def test_sync_runner_ingests_only_explicit_dependency_closed_scope(
    mocker: MockerFixture,
) -> None:
    """A strategy-scoped sync run must not call unrelated dataset providers."""
    mocker.patch.object(daily_module, "run_check_trading_day", return_value=True)
    ingested: list[Dataset] = []

    def ingest_dataset(**kwargs: object) -> dict[str, object]:
        dataset = kwargs["dataset"]
        assert isinstance(dataset, Dataset)
        ingested.append(dataset)
        return {
            "dataset": dataset.value,
            "trade_date": "2026-07-16",
            "status": "success",
            "checksum": f"sha256:{dataset.value}",
        }

    mocker.patch.object(
        daily_module,
        "run_ingest_dataset",
        side_effect=ingest_dataset,
    )
    dq = mocker.patch.object(
        daily_module,
        "run_dq_batch_check",
        return_value={"trade_date": "2026-07-16", "results_by_dataset": {}},
    )

    result = daily_module.run_daily_ingestion(
        trade_date="2026-07-16",
        source="tushare",
        required_datasets=("stock_daily", "adj_factor"),
    )

    assert ingested == [
        Dataset.STOCK_BASIC,
        Dataset.STOCK_DAILY,
        Dataset.ADJ_FACTOR,
    ]
    t0_results = result["t0_results"]
    t1_results = result["t1_results"]
    assert isinstance(t0_results, dict)
    assert isinstance(t1_results, dict)
    assert set(t0_results) == {"stock_basic"}
    assert set(t1_results) == {"stock_daily", "adj_factor"}
    assert dq.call_args.kwargs["datasets"] == [
        "stock_basic",
        "stock_daily",
        "adj_factor",
    ]


def test_sync_runner_uses_plain_business_functions_without_prefect_entrypoints(
    mocker: MockerFixture,
) -> None:
    """CLI 同步路径顺序执行同一摄取/DQ 业务函数，不提交 Prefect task。"""
    assert hasattr(daily_module, "run_daily_ingestion")
    check_day = mocker.patch.object(
        daily_module,
        "run_check_trading_day",
        return_value=True,
    )
    mocker.patch.object(
        daily_module,
        "get_datasets_by_tier",
        return_value=[Dataset.CALENDAR],
    )
    mocker.patch.object(
        daily_module,
        "get_parallel_datasets",
        return_value=[[Dataset.STOCK_DAILY]],
    )
    ingest = mocker.patch.object(
        daily_module,
        "run_ingest_dataset",
        side_effect=[
            {
                "dataset": "calendar",
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": "sha256:calendar",
            },
            {
                "dataset": "stock_daily",
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": "sha256:stock",
            },
        ],
    )
    dq = mocker.patch.object(
        daily_module,
        "run_dq_batch_check",
        return_value={
            "trade_date": "2026-07-16",
            "results_by_dataset": {
                "calendar": {"passed": True},
                "stock_daily": {"passed": True},
            },
        },
    )
    prefect_check = mocker.patch.object(daily_module, "check_trading_day")
    prefect_dq = mocker.patch.object(daily_module, "dq_batch_check")
    prefect_t0 = mocker.patch.object(daily_module, "create_ingest_task_t0")
    prefect_t1 = mocker.patch.object(daily_module, "create_ingest_task_t1_bars")

    result = daily_module.run_daily_ingestion(
        trade_date="2026-07-16",
        source="tushare",
    )

    assert result["skipped"] is False
    assert result["summary"] == {
        "trade_date": "2026-07-16",
        "total_tasks": 2,
        "success_count": 2,
        "failed_count": 0,
        "skipped_count": 0,
    }
    check_day.assert_called_once_with("2026-07-16")
    assert ingest.call_args_list == [
        mocker.call(
            dataset=Dataset.CALENDAR,
            trade_date="2026-07-16",
            source="tushare",
            force=False,
        ),
        mocker.call(
            dataset=Dataset.STOCK_DAILY,
            trade_date="2026-07-16",
            source="tushare",
            force=False,
        ),
    ]
    dq.assert_called_once_with(
        trade_date="2026-07-16",
        datasets=["calendar", "stock_daily"],
        market_wide=True,
        ingestion_results={
            "calendar": {
                "dataset": "calendar",
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": "sha256:calendar",
            },
            "stock_daily": {
                "dataset": "stock_daily",
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": "sha256:stock",
            },
        },
    )
    prefect_check.assert_not_called()
    prefect_dq.assert_not_called()
    prefect_t0.assert_not_called()
    prefect_t1.assert_not_called()


def test_sync_runner_second_same_day_run_keeps_authoritative_dq_evidence(
    mocker: MockerFixture,
) -> None:
    """首次成功与同日跳过重跑必须返回同一 checksum/row-count DQ 证据。"""
    from ditto_apps.jobs.tasks import dq_batch as dq_batch_module
    from ditto_apps.registry.infra.observability import (
        register_app_metric_definitions,
    )

    register_app_metric_definitions()

    mocker.patch.object(daily_module, "run_check_trading_day", return_value=True)
    mocker.patch.object(daily_module, "get_datasets_by_tier", return_value=[])
    mocker.patch.object(
        daily_module,
        "get_parallel_datasets",
        return_value=[[Dataset.STOCK_DAILY, Dataset.VALUATION_METRICS]],
    )
    ingest = mocker.patch.object(
        daily_module,
        "run_ingest_dataset",
        side_effect=[
            {
                "dataset": "stock_daily",
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": "sha256:stock",
                "row_count": 5_000,
                "quality_evidence": {
                    "kind": "write_time_l1_l2",
                    "status": "passed",
                    "source": "tushare",
                    "trade_date": "2026-07-16",
                    "levels": ["l1", "l2"],
                    "row_count": 5_000,
                    "checksum": "sha256:stock",
                },
            },
            {
                "dataset": "valuation_metrics",
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": "sha256:valuation",
                "row_count": 5_000,
                "quality_evidence": {
                    "kind": "write_time_l1_l2",
                    "status": "passed",
                    "source": "tushare",
                    "trade_date": "2026-07-16",
                    "levels": ["l1", "l2"],
                    "row_count": 5_000,
                    "checksum": "sha256:valuation",
                },
            },
            {
                "dataset": "stock_daily",
                "trade_date": "2026-07-16",
                "status": "skipped",
                "checksum": "sha256:stock",
                "row_count": 5_000,
                "quality_evidence": {
                    "kind": "persisted_ingestion_l1_l2",
                    "status": "passed",
                    "source": "tushare",
                    "trade_date": "2026-07-16",
                    "levels": ["l1", "l2"],
                    "row_count": 5_000,
                    "checksum": "sha256:stock",
                },
            },
            {
                "dataset": "valuation_metrics",
                "trade_date": "2026-07-16",
                "status": "skipped",
                "checksum": "sha256:valuation",
                "row_count": 5_000,
                "quality_evidence": {
                    "kind": "persisted_ingestion_l1_l2",
                    "status": "passed",
                    "source": "tushare",
                    "trade_date": "2026-07-16",
                    "levels": ["l1", "l2"],
                    "row_count": 5_000,
                    "checksum": "sha256:valuation",
                },
            },
        ],
    )
    l3_service = mocker.MagicMock()
    l3_service.check_dataset.side_effect = [
        L3CheckResult(
            dataset="stock_daily",
            trade_date="2026-07-16",
            passed=True,
            issue_count=0,
        ),
        L3CheckResult(
            dataset="valuation_metrics",
            trade_date="2026-07-16",
            passed=True,
            issue_count=0,
            applicable=False,
        ),
        L3CheckResult(
            dataset="stock_daily",
            trade_date="2026-07-16",
            passed=True,
            issue_count=0,
        ),
        L3CheckResult(
            dataset="valuation_metrics",
            trade_date="2026-07-16",
            passed=True,
            issue_count=0,
            applicable=False,
        ),
    ]
    evidence_verifier = mocker.MagicMock()
    evidence_verifier.verify_exact_date.return_value = True
    quality_coordinator = QualityBatchCoordinator(
        patrol=l3_service,
        metadata=mocker.MagicMock(),
        evidence_verifier=evidence_verifier,
        alert_manager=mocker.MagicMock(),
    )
    container = mocker.MagicMock()

    def get_service(service_type: type[object]) -> object:
        if service_type is QualityBatchCoordinator:
            return quality_coordinator
        return mocker.MagicMock()

    container.get.side_effect = get_service
    context = mocker.MagicMock()
    context.__enter__.return_value = container
    context.__exit__.return_value = None
    mocker.patch.object(
        dq_batch_module,
        "create_prefect_host",
        return_value=context,
    )
    mocker.patch.object(
        daily_module,
        "run_dq_batch_check",
        side_effect=dq_batch_module.run_dq_batch_check,
    )

    first = daily_module.run_daily_ingestion("2026-07-16")
    second = daily_module.run_daily_ingestion("2026-07-16")
    _assert_authoritative_dq_evidence(
        first,
        second,
        ingest=ingest,
        l3_service=l3_service,
    )


@pytest.fixture(autouse=True)
def mock_daily_dq_batch_check(mocker: MockerFixture):
    """Replace DQC task execution with a lightweight future for unit tests."""

    mock_future = mocker.Mock()
    mock_future.result.return_value = {
        "trade_date": "2024-01-02",
        "datasets_checked": [
            "etf_daily",
            "index_daily",
            "stock_daily",
            "adj_factor",
        ],
        "total_issues": 0,
        "alert_count": 0,
        "results_by_dataset": {},
    }
    mock_task = mocker.Mock()
    mock_task.submit.return_value = mock_future
    return mocker.patch("ditto_apps.jobs.flows.daily.dq_batch_check", mock_task)


@pytest.mark.unit
class TestCheckTradingDay:
    """Unit tests for check_trading_day task."""

    def test_returns_true_for_trading_day(self, mocker: MockerFixture):
        """Test that task returns True for valid trading day."""
        mock_metadata_facade = mocker.MagicMock()
        mock_metadata_facade.is_trading_day.return_value = True

        # Mock IngestionBundle
        mock_bundle = mocker.MagicMock()
        mock_bundle.metadata_facade = mock_metadata_facade

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = mock_bundle
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingestion_bundle",
            return_value=mock_context_mgr,
        )
        result = CHECK_TRADING_DAY_RUNNER(trade_date="2024-01-02")

        assert result is True
        mock_metadata_facade.is_trading_day.assert_called_once_with("2024-01-02")

    def test_returns_false_for_non_trading_day(self, mocker: MockerFixture):
        """Test that task returns False for non-trading day."""
        mock_metadata_facade = mocker.MagicMock()
        mock_metadata_facade.is_trading_day.return_value = False

        # Mock IngestionBundle
        mock_bundle = mocker.MagicMock()
        mock_bundle.metadata_facade = mock_metadata_facade

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = mock_bundle
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingestion_bundle",
            return_value=mock_context_mgr,
        )
        result = CHECK_TRADING_DAY_RUNNER(trade_date="2024-01-06")

        assert result is False

    def test_propagates_exception(self, mocker: MockerFixture):
        """Test that exceptions are propagated."""
        mock_metadata_facade = mocker.MagicMock()
        mock_metadata_facade.is_trading_day.side_effect = ValueError("Test error")

        # Mock IngestionBundle
        mock_bundle = mocker.MagicMock()
        mock_bundle.metadata_facade = mock_metadata_facade

        mock_context_mgr = mocker.MagicMock()
        mock_context_mgr.__enter__.return_value = mock_bundle
        mock_context_mgr.__exit__.return_value = None

        mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingestion_bundle",
            return_value=mock_context_mgr,
        )
        with pytest.raises(ValueError, match="Test error"):
            CHECK_TRADING_DAY_RUNNER(trade_date="2024-01-02")

    def test_is_prefect_task(self, mocker: MockerFixture):
        """
        Test that check_trading_day preserves task name after mock.

        在单元测试中，@task decorator 被 mock，函数本身保留。
        此测试验证 mock 没有破坏函数的基本属性。
        """
        assert callable(check_trading_day)
        assert check_trading_day.name == "check_trading_day"


@pytest.mark.unit
class TestDailyIngestionFlowNonTradingDay:
    """Unit tests for daily_ingestion_flow non-trading day branch."""

    def test_returns_skipped_result_for_non_trading_day(self, mocker: MockerFixture):
        """Test that flow returns skipped result for non-trading day."""
        mocker.patch(
            "ditto_apps.jobs.flows.daily.check_trading_day", return_value=False
        )
        result = DAILY_INGESTION_FLOW_RUNNER(
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
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        # Mock get_datasets_by_tier to return T0 datasets
        t0_datasets = [Dataset.CALENDAR, Dataset.STOCK_BASIC]
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=t0_datasets,
        )
        # Mock task creation
        mock_create_task = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t0"
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
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify T0 task was created and submitted
        assert mock_create_task.call_count == 2
        assert mock_task.submit.call_count == 2
        assert "calendar" in result["t0_results"]

    def test_handles_empty_t0_datasets(self, mocker: MockerFixture):
        """Test that flow handles empty T0 datasets list."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = DAILY_INGESTION_FLOW_RUNNER(
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
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        # Mock get_parallel_datasets to return adj_factor in level 0
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.ADJ_FACTOR]],
        )
        mock_t1_adj = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_adj"
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
        mocker.patch("ditto_apps.jobs.flows.daily.create_ingest_task_t0")
        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify t1_adj factory was used for adj_factor
        mock_t1_adj.assert_called_once_with(Dataset.ADJ_FACTOR)
        assert "adj_factor" in result["t1_results"]

    def test_uses_correct_task_factory_for_fund_adj(self, mocker: MockerFixture):
        """Test that fund_adj uses create_ingest_task_t1_adj."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.FUND_ADJ]],
        )
        mock_t1_adj = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_adj"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "fund_adj",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_adj.return_value = mock_task

        mocker.patch("ditto_apps.jobs.flows.daily.create_ingest_task_t0")
        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        mock_t1_adj.assert_called_once_with(Dataset.FUND_ADJ)
        assert "fund_adj" in result["t1_results"]

    def test_uses_correct_task_factory_for_bars_datasets(self, mocker: MockerFixture):
        """Test that bars datasets use create_ingest_task_t1_bars."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[[Dataset.STOCK_DAILY, Dataset.ETF_DAILY]],
        )
        mock_t1_bars = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "stock_daily",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_t1_bars.return_value = mock_task

        mocker.patch("ditto_apps.jobs.flows.daily.create_ingest_task_t0")
        DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify t1_bars factory was called for both datasets
        assert mock_t1_bars.call_count == 2

    def test_handles_multi_level_t1_dependencies(self, mocker: MockerFixture):
        """Test that T1 multi-level dependencies use correct wait_for."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[Dataset.CALENDAR],
        )
        # Mock two levels of T1 datasets
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[
                [Dataset.STOCK_DAILY],  # Level 0
                [Dataset.ADJ_FACTOR],  # Level 1 (depends on Level 0)
            ],
        )
        mock_t0 = mocker.patch("ditto_apps.jobs.flows.daily.create_ingest_task_t0")
        mock_t1_bars = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_t1_adj = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_adj"
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

        DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify level 1 (adj_factor) waits for level 0 (stock_daily)
        t1_adj_submit_call = mock_t1_adj_task.submit.call_args
        assert "wait_for" in t1_adj_submit_call.kwargs

    def test_prefect_runner_submits_only_explicit_dependency_closed_scope(
        self,
        mocker: MockerFixture,
        mock_daily_dq_batch_check: object,
    ) -> None:
        """The Prefect adapter must consume the same application-owned scope."""
        mocker.patch(
            "ditto_apps.jobs.flows.daily.check_trading_day",
            return_value=True,
        )

        def task_for(dataset: Dataset):
            task = mocker.Mock()
            future = mocker.Mock()
            future.result.return_value = {
                "dataset": dataset.value,
                "trade_date": "2026-07-16",
                "status": "success",
                "checksum": f"sha256:{dataset.value}",
            }
            task.submit.return_value = future
            return task

        t0_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t0",
            side_effect=task_for,
        )
        bars_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars",
            side_effect=task_for,
        )
        adj_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_adj",
            side_effect=task_for,
        )

        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2026-07-16",
            source="tushare",
            required_datasets=("stock_daily", "adj_factor"),
        )

        assert t0_factory.call_args_list == [mocker.call(Dataset.STOCK_BASIC)]
        assert bars_factory.call_args_list == [mocker.call(Dataset.STOCK_DAILY)]
        assert adj_factory.call_args_list == [mocker.call(Dataset.ADJ_FACTOR)]
        assert set(result["t0_results"]) == {"stock_basic"}
        assert set(result["t1_results"]) == {"stock_daily", "adj_factor"}

    def test_handles_empty_t1_datasets(self, mocker: MockerFixture):
        """Test that flow handles empty T1 datasets list."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["t1_results"] == {}


@pytest.mark.unit
class TestDailyIngestionFlowResultAggregation:
    """Unit tests for result aggregation logic."""

    def test_aggregates_success_status(self, mocker: MockerFixture):
        """Test that success status is counted correctly."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("success")]],
        )
        mock_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "success",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["summary"]["success_count"] == 1
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 0

    def test_aggregates_failed_status(self, mocker: MockerFixture):
        """Test that failed status is counted correctly."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("failed")]],
        )
        mock_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "failed",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 1
        assert result["summary"]["skipped_count"] == 0

    def test_aggregates_skipped_status(self, mocker: MockerFixture):
        """Test that skipped status is counted correctly."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[[MockDataset("skipped")]],
        )
        mock_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars"
        )
        mock_task = mocker.Mock()
        mock_future = mocker.Mock()
        mock_future.result.return_value = {
            "dataset": "test",
            "status": "skipped",
        }
        mock_task.submit.return_value = mock_future
        mock_factory.return_value = mock_task

        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        assert result["summary"]["success_count"] == 0
        assert result["summary"]["failed_count"] == 0
        assert result["summary"]["skipped_count"] == 1

    def test_aggregates_mixed_statuses(self, mocker: MockerFixture):
        """Test that mixed statuses are counted correctly."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[
                [MockDataset("success"), MockDataset("failed")],
                [MockDataset("skipped")],
            ],
        )
        mock_factory = mocker.patch(
            "ditto_apps.jobs.flows.daily.create_ingest_task_t1_bars"
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

        result = DAILY_INGESTION_FLOW_RUNNER(
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
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        result = DAILY_INGESTION_FLOW_RUNNER(
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
        """Test that DQC results contain expected structure."""
        mocker.patch("ditto_apps.jobs.flows.daily.check_trading_day", return_value=True)
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_datasets_by_tier",
            return_value=[],
        )
        mocker.patch(
            "ditto_apps.jobs.flows.daily.get_parallel_datasets",
            return_value=[],
        )
        # Mock dq_batch_check to return expected structure
        mock_dqc_future = mocker.Mock()
        mock_dqc_future.result.return_value = {
            "trade_date": "2024-01-02",
            "datasets_checked": [
                "etf_daily",
                "index_daily",
                "stock_daily",
                "adj_factor",
            ],
            "total_issues": 0,
            "alert_count": 0,
            "results_by_dataset": {},
        }
        mock_dqc_task = mocker.patch("ditto_apps.jobs.flows.daily.dq_batch_check")
        mock_dqc_task.submit.return_value = mock_dqc_future

        result = DAILY_INGESTION_FLOW_RUNNER(
            trade_date="2024-01-02",
            source="tushare",
        )

        # Verify DQC results structure
        assert result["dqc_results"]["trade_date"] == "2024-01-02"
        assert "datasets_checked" in result["dqc_results"]
        assert "total_issues" in result["dqc_results"]
        assert "alert_count" in result["dqc_results"]
        mock_dqc_task.submit.assert_called_once_with(
            trade_date="2024-01-02",
            datasets=[],
            market_wide=True,
            ingestion_results={},
            wait_for=[],
        )


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
