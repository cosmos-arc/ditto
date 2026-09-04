"""Apps-owned metrics and dashboard contract for workstation operations."""

from __future__ import annotations

from types import MappingProxyType

type MetricDefinition = dict[str, str]

WORKSTATION_METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "workstation_runs",
        "instrument_name": "ditto.workstation.runs_total",
        "type": "counter",
        "description": "Total personal workstation daily runs by terminal status",
    },
    {
        "name": "workstation_paper_eod",
        "instrument_name": "ditto.workstation.paper_eod_total",
        "type": "counter",
        "description": "Total Paper EOD reconciliations by terminal status",
    },
    {
        "name": "workstation_trace_stages",
        "instrument_name": "ditto.workstation.trace_stages_total",
        "type": "counter",
        "description": "Total correlated workstation stages by status",
    },
    {
        "name": "workstation_e2e_latency",
        "instrument_name": "ditto.workstation.e2e_latency_seconds",
        "type": "histogram",
        "description": "End-to-end workstation trace latency in seconds",
    },
]

WORKSTATION_DASHBOARD = MappingProxyType(
    {
        "freshness": "ditto.data.freshness_days",
        "dq": "ditto.dq.batch.issues_total",
        "run": "ditto.workstation.runs_total",
        "paper": "ditto.workstation.paper_eod_total",
        "agent": "ditto.agent.runs_total",
        "e2e": "ditto.workstation.e2e_latency_seconds",
    }
)

__all__ = ["WORKSTATION_DASHBOARD", "WORKSTATION_METRIC_DEFINITIONS"]
