"""Apps-owned bridge from redacted Agent records to the existing OTel stack."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import cast

from ditto_agent.observability import (
    AgentMetricRecord,
    AgentObservability,
    AgentSpanRecord,
    NoopAgentTelemetrySink,
)
from ditto_platform.foundation import Metrics, span
from ditto_platform.foundation.observability.metrics import SafeCounter, SafeHistogram

_COUNTER_NAMES = {
    "ditto.agent.runs_total": "agent_runs",
    "ditto.agent.tool_calls_total": "agent_tool_calls",
    "ditto.agent.approvals_total": "agent_approvals",
}
_HISTOGRAM_NAMES = {
    "ditto.agent.run_latency_seconds": "agent_run_latency",
    "ditto.agent.model_cost_usd": "agent_model_cost",
    "ditto.agent.model_tokens": "agent_model_tokens",
}


class OTelAgentTelemetrySink:
    """Export pre-redacted Agent records through Ditto's OTel primitives."""

    def emit_span(self, record: AgentSpanRecord) -> None:
        """Bridge one redacted record into a Ditto OTel span."""
        with span(record.name, **dict(record.attributes)):
            pass

    def emit_metric(self, record: AgentMetricRecord) -> None:
        """Bridge one low-cardinality record into a Ditto OTel metric."""
        attributes = dict(record.attributes)
        counter_name = _COUNTER_NAMES.get(record.name)
        if counter_name is not None:
            counter = cast(SafeCounter, getattr(Metrics, counter_name))
            counter.add(record.value, attributes)
            return
        histogram_name = _HISTOGRAM_NAMES.get(record.name)
        if histogram_name is not None:
            histogram = cast(SafeHistogram, getattr(Metrics, histogram_name))
            histogram.record(record.value, attributes)
            return
        raise ValueError("Agent metric is not wired to OTel")


def build_agent_observability(
    *,
    enabled: bool,
    monotonic: Callable[[], float] = time.monotonic,
) -> AgentObservability:
    """Build an explicitly enabled OTel observer or the default no-op observer."""
    sink = OTelAgentTelemetrySink() if enabled else NoopAgentTelemetrySink()
    return AgentObservability(sink=sink, monotonic=monotonic)


__all__ = ["OTelAgentTelemetrySink", "build_agent_observability"]
