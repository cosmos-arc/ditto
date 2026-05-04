"""Strategy metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "signal_total",
        "instrument_name": "ditto.signal.total",
        "type": "counter",
        "description": "Total trading signals generated",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
