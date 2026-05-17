"""Data metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "data_update_duration",
        "instrument_name": "ditto.data.update.duration",
        "type": "histogram",
        "description": "Data update operation duration in seconds",
    },
    {
        "name": "data_records",
        "instrument_name": "ditto.data.records_total",
        "type": "counter",
        "description": "Total data records processed",
    },
    {
        "name": "data_freshness",
        "instrument_name": "ditto.data.freshness_days",
        "type": "gauge",
        "description": "Data freshness in days since last update",
    },
    {
        "name": "data_errors",
        "instrument_name": "ditto.data.errors_total",
        "type": "counter",
        "description": "Total data processing errors",
    },
    {
        "name": "dq_batch_checks",
        "instrument_name": "ditto.dq.batch.checks_total",
        "type": "counter",
        "description": "Total DQ batch checks executed",
    },
    {
        "name": "dq_batch_issues",
        "instrument_name": "ditto.dq.batch.issues_total",
        "type": "counter",
        "description": "Total DQ batch issues found",
    },
    {
        "name": "dq_batch_alerts",
        "instrument_name": "ditto.dq.batch.alerts_total",
        "type": "counter",
        "description": "Total DQ batch alerts generated",
    },
]


def register_metrics() -> None:
    """Register data-owned metric definitions with the platform meter."""
    from ditto_platform.foundation import (  # noqa: PLC0415
        register_metric_definitions,
    )

    register_metric_definitions(METRIC_DEFINITIONS)


__all__ = ["METRIC_DEFINITIONS", "register_metrics"]
