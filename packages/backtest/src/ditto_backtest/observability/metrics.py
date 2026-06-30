"""Backtest metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "backtest_duration",
        "instrument_name": "ditto.backtest.duration",
        "type": "histogram",
        "description": "Backtest run duration in seconds",
    },
    {
        "name": "backtest_trading_days",
        "instrument_name": "ditto.backtest.trading_days_total",
        "type": "counter",
        "description": "Total trading days processed in backtest",
    },
    {
        "name": "backtest_step_duration",
        "instrument_name": "ditto.backtest.step.duration",
        "type": "histogram",
        "description": "Individual backtest step duration in seconds",
    },
    {
        "name": "backtest_step_failures",
        "instrument_name": "ditto.backtest.step.failures_total",
        "type": "counter",
        "description": "Total backtest step failures",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
