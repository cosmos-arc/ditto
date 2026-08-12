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
    {
        "name": "daily_scan_duration",
        "instrument_name": "ditto.risk.daily_scan.duration",
        "type": "histogram",
        "description": "Daily risk scan duration in seconds",
    },
    {
        "name": "tail_limit_breaches",
        "instrument_name": "ditto.risk.tail_limit_breaches_total",
        "type": "counter",
        "description": "VaR or ES limit breaches by metric",
    },
    {
        "name": "state_restore_failures",
        "instrument_name": "ditto.risk.state_restore_failures_total",
        "type": "counter",
        "description": "Continuous risk state restore failures",
    },
    {
        "name": "reconciliation_mismatches",
        "instrument_name": "ditto.risk.reconciliation_mismatches_total",
        "type": "counter",
        "description": "EOD reconciliation mismatches by layer",
    },
    {
        "name": "daily_report_freshness",
        "instrument_name": "ditto.risk.daily_report.freshness",
        "type": "histogram",
        "description": "Age of the latest Daily Decision V3 report in seconds",
    },
    {
        "name": "daily_decision_v3_duration",
        "instrument_name": "ditto.risk.daily_decision_v3.duration",
        "type": "histogram",
        "description": "Daily Decision V3 query duration in seconds",
    },
]

__all__ = ["METRIC_DEFINITIONS"]
