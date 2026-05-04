"""Risk metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "kill_switch_level",
        "instrument_name": "ditto.risk.kill_switch_level",
        "type": "gauge",
        "description": "Current kill switch level (0-3)",
    },
    {
        "name": "kill_switch_total",
        "instrument_name": "ditto.risk.kill_switch_total",
        "type": "counter",
        "description": "Total kill switch triggers",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
