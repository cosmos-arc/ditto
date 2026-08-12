"""Portfolio metric definitions."""

from __future__ import annotations

type MetricDefinition = dict[str, str]

METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "rebalance_total",
        "instrument_name": "ditto.rebalance.total",
        "type": "counter",
        "description": "Total portfolio rebalances executed",
    },
    {
        "name": "portfolio_value",
        "instrument_name": "ditto.portfolio.value",
        "type": "gauge",
        "description": "Current portfolio value",
    },
    {
        "name": "portfolio_drawdown",
        "instrument_name": "ditto.portfolio.drawdown",
        "type": "gauge",
        "description": "Current portfolio drawdown",
    },
    {
        "name": "portfolio_drawdown_3d",
        "instrument_name": "ditto.portfolio.drawdown_3d",
        "type": "gauge",
        "description": "3-day rolling portfolio drawdown",
    },
    {
        "name": "optimizer_runs",
        "instrument_name": "ditto.portfolio.optimizer.runs_total",
        "type": "counter",
        "description": "Portfolio optimization outcomes by method and status",
    },
    {
        "name": "optimizer_duration",
        "instrument_name": "ditto.portfolio.optimizer.duration",
        "type": "histogram",
        "description": "Portfolio optimization duration in seconds",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
