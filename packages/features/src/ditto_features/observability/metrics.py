"""Feature metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "factor_calc_duration",
        "instrument_name": "ditto.factor.calc.duration",
        "type": "histogram",
        "description": "Factor calculation duration in seconds",
    },
    {
        "name": "factor_ic",
        "instrument_name": "ditto.factor.ic",
        "type": "gauge",
        "description": "Factor Information Coefficient (IC)",
    },
    {
        "name": "factor_health",
        "instrument_name": "ditto.factor.health",
        "type": "gauge",
        "description": "Factor health score (0-100)",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
