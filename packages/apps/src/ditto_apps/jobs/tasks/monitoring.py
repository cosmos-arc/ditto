"""数据摄取质量监控任务."""

from __future__ import annotations

from typing import Any

from ditto_data.quality.kernel_types import DQResult
from ditto_platform.foundation import Metrics, logger
from prefect import task


@task(
    name="monitor_ingestion_quality",
    description="Monitor and record quality metrics for data ingestion",
    tags=["monitoring", "quality", "metrics"],
)
def monitor_ingestion_quality(
    trade_date: str,
    ingestion_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Monitor and record quality metrics for data ingestion.

    Records OpenTelemetry metrics for:
    - Ingestion row counts (Counter)
    - Ingestion duration (Histogram)
    - API call counts (Counter)
    - New securities registered (Counter)
    - DQ check results (Counter)

    Args:
        trade_date: Trade date being monitored (YYYY-MM-DD).
        ingestion_results: Dict of dataset results with keys:
            - rows_fetched: int
            - rows_written: int
            - new_securities_registered: int
            - api_calls: int
            - duration_sec: float
            - status: str
            - dq_result: DQResult | None

    Returns:
        Dict with aggregated metrics:
        - total_datasets: int
        - successful_datasets: int
        - datasets_with_errors: int
        - datasets_with_warnings: int
        - total_rows_fetched: int
        - total_rows_written: int
        - total_new_securities: int
        - total_api_calls: int
        - total_duration_sec: float
        - total_dq_errors: int
        - total_dq_warnings: int

    """
    logger.info(
        "Starting ingestion quality monitoring",
        event="monitoring_start",
        trade_date=trade_date,
        datasets_count=len(ingestion_results),
    )

    # Initialize counters
    total_datasets = len(ingestion_results)
    successful_datasets = 0
    datasets_with_errors = 0
    datasets_with_warnings = 0
    total_rows_fetched = 0
    total_rows_written = 0
    total_new_securities = 0
    total_api_calls = 0
    total_duration_sec = 0.0
    total_dq_errors = 0
    total_dq_warnings = 0

    # Process each dataset result
    for dataset, result in ingestion_results.items():
        # Extract metrics
        rows_fetched = result.get("rows_fetched", 0)
        rows_written = result.get("rows_written", 0)
        new_securities = result.get("new_securities_registered", 0)
        api_calls = result.get("api_calls", 0)
        duration_sec = result.get("duration_sec", 0.0)
        status = result.get("status", "unknown")

        # Accumulate totals
        total_rows_fetched += rows_fetched
        total_rows_written += rows_written
        total_new_securities += new_securities
        total_api_calls += api_calls
        total_duration_sec += duration_sec

        # Record OpenTelemetry metrics
        Metrics.data_records.add(
            rows_written,
            {
                "dataset": dataset,
                "status": status,
            },
        )

        Metrics.data_update_duration.record(
            duration_sec,
            {"dataset": dataset},
        )

        # Log API calls
        if api_calls > 0:
            logger.debug(
                "API calls recorded",
                event="monitoring_api_calls",
                dataset=dataset,
                api_calls=api_calls,
            )

        # Log new securities
        if new_securities > 0:
            logger.info(
                "New securities registered",
                event="monitoring_new_securities",
                dataset=dataset,
                new_securities=new_securities,
            )

        # Count successful datasets
        if status in ("success", "warning"):
            successful_datasets += 1

        # Process DQ results
        dq_result: DQResult | None = result.get("dq_result")
        if dq_result:
            if dq_result.error_count > 0:
                datasets_with_errors += 1
                total_dq_errors += dq_result.error_count

                # Record error metrics using data_errors counter
                Metrics.data_errors.add(
                    dq_result.error_count,
                    {
                        "dataset": dataset,
                        "severity": "error",
                        "type": "dq_check",
                    },
                )

            if dq_result.warn_count > 0:
                datasets_with_warnings += 1
                total_dq_warnings += dq_result.warn_count

                # Record warning metrics
                logger.warning(
                    "DQ warnings detected",
                    event="monitoring_dq_warnings",
                    dataset=dataset,
                    warning_count=dq_result.warn_count,
                )

    logger.info(
        "Ingestion quality monitoring completed",
        event="monitoring_complete",
        trade_date=trade_date,
        total_datasets=total_datasets,
        successful_datasets=successful_datasets,
        datasets_with_errors=datasets_with_errors,
        datasets_with_warnings=datasets_with_warnings,
        total_rows_fetched=total_rows_fetched,
        total_rows_written=total_rows_written,
        total_new_securities=total_new_securities,
        total_dq_errors=total_dq_errors,
        total_dq_warnings=total_dq_warnings,
    )

    return {
        "total_datasets": total_datasets,
        "successful_datasets": successful_datasets,
        "datasets_with_errors": datasets_with_errors,
        "datasets_with_warnings": datasets_with_warnings,
        "total_rows_fetched": total_rows_fetched,
        "total_rows_written": total_rows_written,
        "total_new_securities": total_new_securities,
        "total_api_calls": total_api_calls,
        "total_duration_sec": total_duration_sec,
        "total_dq_errors": total_dq_errors,
        "total_dq_warnings": total_dq_warnings,
    }
