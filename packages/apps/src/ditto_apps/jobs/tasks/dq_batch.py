"""Prefect transport adapters for application-owned quality processes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ditto_application.processes.quality import (
    QualityBatchCoordinator,
    QualityBatchRequest,
    QualityCompletenessRequest,
    QualityCompletenessService,
)
from ditto_platform.foundation import Metrics
from prefect import task

from ditto_apps.jobs.context import create_prefect_host


def run_dq_batch_check(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
    market_wide: bool = False,
    ingestion_results: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Invoke the application quality batch and serialize its result."""
    with create_prefect_host() as container:
        coordinator = container.get(QualityBatchCoordinator)
        result = coordinator.run(
            QualityBatchRequest(
                trade_date=trade_date,
                datasets=tuple(datasets) if datasets is not None else None,
                market_wide=market_wide,
                ingestion_results=ingestion_results,
            )
        )

    Metrics.dq_batch_checks.add(1.0, {"trade_date": result.trade_date})
    Metrics.dq_batch_issues.add(
        float(result.total_issues), {"trade_date": result.trade_date}
    )
    Metrics.dq_batch_alerts.add(
        float(result.alert_count), {"trade_date": result.trade_date}
    )
    return cast(dict[str, Any], result.to_dict())


@task(
    name="dq-batch-check",
    description="批量数据质量检查(L3 统计异常)",
    tags=["dq", "batch", "l3"],
)
async def dq_batch_check(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
    market_wide: bool = False,
    ingestion_results: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Prefect wrapper for :func:`run_dq_batch_check`."""
    return run_dq_batch_check(
        trade_date=trade_date,
        datasets=datasets,
        market_wide=market_wide,
        ingestion_results=ingestion_results,
    )


@task(
    name="dq-completeness-check",
    description="数据完整性检查",
    tags=["dq", "completeness"],
)
def dq_completeness_check(
    trade_date: str,
    dataset: str,
    expected_sids: list[int] | None = None,
    market_wide: bool = False,
) -> dict[str, Any]:
    """Invoke and serialize the application completeness process."""
    with create_prefect_host() as container:
        service = container.get(QualityCompletenessService)
        result = service.run(
            QualityCompletenessRequest(
                trade_date=trade_date,
                dataset=dataset,
                expected_sids=(
                    tuple(expected_sids) if expected_sids is not None else None
                ),
                market_wide=market_wide,
            )
        )
    return cast(dict[str, Any], result.to_dict())
