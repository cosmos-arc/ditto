"""Prefect adapter tests for the application-owned quality batch."""

from __future__ import annotations

import pytest
from ditto_application.processes.quality.types import (
    QualityBatchDatasetResult,
    QualityBatchRequest,
    QualityBatchResult,
    QualityCompletenessRequest,
    QualityCompletenessResult,
)
from ditto_apps.registry.infra.observability import register_app_metric_definitions
from ditto_platform.foundation import reset_for_testing
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


@pytest.fixture(autouse=True)
def register_app_metrics() -> None:
    """Register metrics for direct task-function execution."""
    reset_for_testing()
    register_app_metric_definitions()


@pytest.mark.unit
def test_run_dq_batch_check_only_delegates_and_serializes(
    mocker: MockerFixture,
) -> None:
    coordinator = mocker.MagicMock()
    coordinator.run.return_value = QualityBatchResult(
        trade_date="2026-07-16",
        datasets_checked=("stock_daily",),
        total_issues=0,
        alert_count=0,
        results_by_dataset={
            "stock_daily": QualityBatchDatasetResult(
                passed=True,
                issue_count=0,
                alert_count=0,
            )
        },
    )
    container = mocker.MagicMock()
    container.get.return_value = coordinator
    context = mocker.MagicMock()
    context.__enter__.return_value = container
    context.__exit__.return_value = None
    mocker.patch(
        "ditto_apps.jobs.tasks.dq_batch.create_prefect_host",
        return_value=context,
    )

    from ditto_apps.jobs.tasks.dq_batch import run_dq_batch_check

    result = run_dq_batch_check(
        trade_date="2026-07-16",
        datasets=["stock_daily"],
        market_wide=True,
        ingestion_results={"stock_daily": {"status": "success"}},
    )

    coordinator.run.assert_called_once_with(
        QualityBatchRequest(
            trade_date="2026-07-16",
            datasets=("stock_daily",),
            market_wide=True,
            ingestion_results={"stock_daily": {"status": "success"}},
        )
    )
    assert result == {
        "trade_date": "2026-07-16",
        "datasets_checked": ["stock_daily"],
        "total_issues": 0,
        "alert_count": 0,
        "results_by_dataset": {
            "stock_daily": {
                "passed": True,
                "issue_count": 0,
                "alert_count": 0,
            }
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prefect_task_wrapper_delegates_to_sync_adapter(
    mocker: MockerFixture,
) -> None:
    run = mocker.patch(
        "ditto_apps.jobs.tasks.dq_batch.run_dq_batch_check",
        return_value={"trade_date": "2026-07-16"},
    )
    from ditto_apps.jobs.tasks.dq_batch import dq_batch_check

    result = await _prefect_runner(dq_batch_check)(
        trade_date="2026-07-16",
        datasets=["stock_daily"],
        market_wide=True,
        ingestion_results={"stock_daily": {"status": "success"}},
    )

    assert result == {"trade_date": "2026-07-16"}
    run.assert_called_once_with(
        trade_date="2026-07-16",
        datasets=["stock_daily"],
        market_wide=True,
        ingestion_results={"stock_daily": {"status": "success"}},
    )


@pytest.mark.unit
def test_completeness_task_only_delegates_and_serializes(
    mocker: MockerFixture,
) -> None:
    service = mocker.MagicMock()
    service.run.return_value = QualityCompletenessResult(
        trade_date="2026-07-16",
        dataset="stock_daily",
        expected_count=2,
        actual_count=1,
        missing_sids=(1002,),
        extra_sids=(),
    )
    container = mocker.MagicMock()
    container.get.return_value = service
    context = mocker.MagicMock()
    context.__enter__.return_value = container
    context.__exit__.return_value = None
    mocker.patch(
        "ditto_apps.jobs.tasks.dq_batch.create_prefect_host",
        return_value=context,
    )
    from ditto_apps.jobs.tasks.dq_batch import dq_completeness_check

    result = _prefect_runner(dq_completeness_check)(
        trade_date="2026-07-16",
        dataset="stock_daily",
        expected_sids=[1001, 1002],
        market_wide=True,
    )

    service.run.assert_called_once_with(
        QualityCompletenessRequest(
            trade_date="2026-07-16",
            dataset="stock_daily",
            expected_sids=(1001, 1002),
            market_wide=True,
        )
    )
    assert result["missing_sids"] == [1002]
