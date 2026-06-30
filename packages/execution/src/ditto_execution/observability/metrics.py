"""Execution metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "order_submitted_total",
        "instrument_name": "ditto.execution.order.submitted_total",
        "type": "counter",
        "description": "Total orders submitted",
    },
    {
        "name": "order_filled_total",
        "instrument_name": "ditto.execution.order.filled_total",
        "type": "counter",
        "description": "Total orders filled",
    },
    {
        "name": "order_rejected_total",
        "instrument_name": "ditto.execution.order.rejected_total",
        "type": "counter",
        "description": "Total orders rejected or blocked",
    },
    {
        "name": "planning_duration",
        "instrument_name": "ditto.execution.planning.duration",
        "type": "histogram",
        "description": "Execution planning duration in seconds",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
