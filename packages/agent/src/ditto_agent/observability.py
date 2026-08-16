"""Redacted, exporter-neutral telemetry for governed Agent runs."""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from types import MappingProxyType
from typing import Protocol, cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    RunStatus,
)
from ditto_agent.models.port import ModelUsage

type AgentTelemetryValue = str | bool | int | float

_SECRET_PATTERN = re.compile(
    r"(?i)(?:bearer\s+\S+|sk-[a-z0-9_-]+|api[_-]?key|password|secret)"
)
_SPAN_NAMES = frozenset(
    {
        "ditto.agent.run",
        "ditto.agent.model",
        "ditto.agent.tool",
        "ditto.agent.approval",
        "ditto.agent.cost",
        "ditto.agent.guardrail",
    }
)
_SPAN_ATTRIBUTE_KEYS = frozenset(
    {
        "agent.action_hash",
        "agent.approval_count",
        "agent.arguments_hash",
        "agent.artifact_refs_hash",
        "agent.authority_hash",
        "agent.campaign_id",
        "agent.evidence_refs_hash",
        "agent.export_failure",
        "agent.failure_code",
        "agent.image_digest",
        "agent.input_tokens",
        "agent.latency_seconds",
        "agent.manifest_hash",
        "agent.model_attempts",
        "agent.model_profile",
        "agent.model_snapshot",
        "agent.model_spend_usd",
        "agent.model_turns",
        "agent.output_tokens",
        "agent.prompt_hash",
        "agent.provider",
        "agent.result_hash",
        "agent.retries",
        "agent.run_id",
        "agent.session_id",
        "agent.status",
        "agent.temporal_context_hash",
        "agent.tool_calls",
        "agent.tool_name",
        "agent.tool_schema_hash",
        "agent.total_tokens",
    }
)
_METRIC_NAMES = frozenset(
    {
        "ditto.agent.runs_total",
        "ditto.agent.run_latency_seconds",
        "ditto.agent.model_cost_usd",
        "ditto.agent.model_tokens",
        "ditto.agent.tool_calls_total",
        "ditto.agent.approvals_total",
    }
)
_METRIC_ATTRIBUTE_KEYS = frozenset(
    {
        "agent.model_profile",
        "agent.status",
        "agent.tool_name",
    }
)

METRIC_DEFINITIONS: list[dict[str, str]] = [
    {
        "name": "agent_runs",
        "instrument_name": "ditto.agent.runs_total",
        "type": "counter",
        "description": "Total governed Agent runs by terminal status",
    },
    {
        "name": "agent_run_latency",
        "instrument_name": "ditto.agent.run_latency_seconds",
        "type": "histogram",
        "description": "Governed Agent run latency in seconds",
    },
    {
        "name": "agent_model_cost",
        "instrument_name": "ditto.agent.model_cost_usd",
        "type": "histogram",
        "description": "Governed Agent model spend in USD",
    },
    {
        "name": "agent_model_tokens",
        "instrument_name": "ditto.agent.model_tokens",
        "type": "histogram",
        "description": "Governed Agent aggregate model tokens",
    },
    {
        "name": "agent_tool_calls",
        "instrument_name": "ditto.agent.tool_calls_total",
        "type": "counter",
        "description": "Total governed Agent tool calls",
    },
    {
        "name": "agent_approvals",
        "instrument_name": "ditto.agent.approvals_total",
        "type": "counter",
        "description": "Total governed Agent approval actions",
    },
]


def _redacted_text(value: str) -> str:
    if _SECRET_PATTERN.search(value) is None:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"redacted:{digest}"


def _attributes(
    values: Mapping[str, AgentTelemetryValue],
    *,
    allowed_keys: frozenset[str],
) -> Mapping[str, AgentTelemetryValue]:
    if not set(values).issubset(allowed_keys):
        raise ValueError("Agent telemetry contains a prohibited attribute")
    normalized: dict[str, AgentTelemetryValue] = {}
    for key, value in values.items():
        raw = cast(object, value)
        if isinstance(raw, str):
            normalized[key] = _redacted_text(raw)
        elif isinstance(raw, (bool, int, float)):
            if isinstance(raw, float) and not math.isfinite(raw):
                raise ValueError("Agent telemetry numeric attributes must be finite")
            normalized[key] = raw
        else:
            raise TypeError("Agent telemetry attributes must be scalar")
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class AgentSpanRecord:
    """One already-redacted span record safe for an external exporter."""

    name: str
    attributes: Mapping[str, AgentTelemetryValue]

    def __post_init__(self) -> None:
        """Validate the span name and redact all scalar attributes."""
        if self.name not in _SPAN_NAMES:
            raise ValueError("Agent span name is not approved")
        object.__setattr__(
            self,
            "attributes",
            _attributes(self.attributes, allowed_keys=_SPAN_ATTRIBUTE_KEYS),
        )


@dataclass(frozen=True, slots=True)
class AgentMetricRecord:
    """One low-cardinality metric safe for an external exporter."""

    name: str
    value: int | float
    attributes: Mapping[str, AgentTelemetryValue]

    def __post_init__(self) -> None:
        """Validate metric identity, value, and low-cardinality attributes."""
        if self.name not in _METRIC_NAMES:
            raise ValueError("Agent metric name is not approved")
        raw_value = cast(object, self.value)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise TypeError("Agent metric value must be numeric")
        if not math.isfinite(float(self.value)) or self.value < 0:
            raise ValueError("Agent metric value must be finite and non-negative")
        object.__setattr__(
            self,
            "attributes",
            _attributes(self.attributes, allowed_keys=_METRIC_ATTRIBUTE_KEYS),
        )


class AgentTelemetrySink(Protocol):
    """Exporter boundary; implementations never receive raw Agent content."""

    def emit_span(self, record: AgentSpanRecord) -> None:
        """Export one already-redacted Agent span."""
        ...

    def emit_metric(self, record: AgentMetricRecord) -> None:
        """Export one already-redacted Agent metric."""
        ...


class NoopAgentTelemetrySink:
    """Default sink preserving zero-export behavior."""

    def emit_span(self, record: AgentSpanRecord) -> None:
        """Discard one span without side effects."""
        del record

    def emit_metric(self, record: AgentMetricRecord) -> None:
        """Discard one metric without side effects."""
        del record


class InMemoryAgentTelemetrySink:
    """Deterministic test sink storing only redacted records."""

    def __init__(self) -> None:
        self.spans: list[AgentSpanRecord] = []
        self.metrics: list[AgentMetricRecord] = []

    def emit_span(self, record: AgentSpanRecord) -> None:
        """Append one redacted span."""
        self.spans.append(record)

    def emit_metric(self, record: AgentMetricRecord) -> None:
        """Append one redacted metric."""
        self.metrics.append(record)


@dataclass(frozen=True, slots=True)
class AgentToolTelemetry:
    """Hash-only host observation for one successful tool call."""

    call_id: str | None
    tool_name: str
    arguments_hash: str
    result_hash: str
    evidence_refs_hash: str
    artifact_refs_hash: str
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class AgentBudgetTelemetry:
    """Runtime-independent aggregate counters safe for observability."""

    model_attempts: int
    model_turns: int
    tool_calls: int
    retries: int
    total_tokens: int
    model_spend_usd: Decimal
    elapsed_seconds: float
    exhausted_reason: str | None


@dataclass(slots=True)
class _RunTelemetryState:
    run_id: str
    session_id: str
    authority_hash: str
    manifest: AgentManifest
    temporal_context_hash: str
    campaign_id: str | None
    image_digest: str | None
    started_at: float
    seen_tool_calls: set[str]


class AgentObservability:
    """Create redacted Agent telemetry and isolate every exporter failure."""

    def __init__(
        self,
        *,
        sink: AgentTelemetrySink | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sink = sink or NoopAgentTelemetrySink()
        self._monotonic = monotonic
        self._lock = Lock()
        self._runs: dict[str, _RunTelemetryState] = {}
        self._export_failures = 0

    @property
    def export_failures(self) -> int:
        """Return isolated exporter errors for local health diagnostics."""
        with self._lock:
            return self._export_failures

    def start_run(
        self,
        *,
        run: AgentRun,
        manifest: AgentManifest,
        temporal_context_hash: str,
        campaign_id: str | None = None,
        image_digest: str | None = None,
    ) -> None:
        """Register only replay identities; raw objective is never retained."""
        with self._lock:
            self._runs[run.run_id] = _RunTelemetryState(
                run_id=run.run_id,
                session_id=run.session_id,
                authority_hash=run.authority_hash,
                manifest=manifest,
                temporal_context_hash=temporal_context_hash,
                campaign_id=campaign_id,
                image_digest=image_digest,
                started_at=self._monotonic(),
                seen_tool_calls=set(),
            )

    def record_model(
        self,
        *,
        run_id: str,
        usage: ModelUsage | None,
        budget: AgentBudgetTelemetry,
        latency_seconds: float,
        status: str = "completed",
        failure_code: str | None = None,
    ) -> None:
        """Export model identity, aggregate usage, cost, retry, and latency."""
        state = self._state(run_id)
        if state is None:
            return
        input_tokens = usage.input_tokens if usage is not None else 0
        output_tokens = usage.output_tokens if usage is not None else 0
        total_tokens = usage.total_tokens if usage is not None else 0
        attributes = self._base_attributes(state)
        attributes.update(
            {
                "agent.status": status,
                "agent.input_tokens": input_tokens,
                "agent.output_tokens": output_tokens,
                "agent.total_tokens": total_tokens,
                "agent.model_spend_usd": str(budget.model_spend_usd),
                "agent.model_attempts": budget.model_attempts,
                "agent.model_turns": budget.model_turns,
                "agent.retries": budget.retries,
                "agent.latency_seconds": latency_seconds,
            }
        )
        if failure_code is not None:
            attributes["agent.failure_code"] = failure_code
        self._emit_span(AgentSpanRecord("ditto.agent.model", attributes))
        self._emit_span(
            AgentSpanRecord(
                "ditto.agent.cost",
                {
                    "agent.run_id": run_id,
                    "agent.model_profile": state.manifest.model_profile.value,
                    "agent.model_spend_usd": str(budget.model_spend_usd),
                    "agent.total_tokens": budget.total_tokens,
                    "agent.status": status,
                },
            )
        )
        metric_attributes = {
            "agent.model_profile": state.manifest.model_profile.value,
            "agent.status": status,
        }
        self._emit_metric(
            AgentMetricRecord(
                "ditto.agent.model_cost_usd",
                float(budget.model_spend_usd),
                metric_attributes,
            )
        )
        self._emit_metric(
            AgentMetricRecord(
                "ditto.agent.model_tokens",
                total_tokens,
                metric_attributes,
            )
        )

    def record_tool(
        self,
        *,
        run_id: str,
        tool: AgentToolTelemetry,
    ) -> None:
        """Export only normalized tool name and content hashes."""
        state = self._state(run_id)
        if state is None:
            return
        deduplication_id = tool.call_id or canonical_sha256(
            (tool.tool_name, tool.arguments_hash, tool.result_hash)
        )
        with self._lock:
            if deduplication_id in state.seen_tool_calls:
                return
            state.seen_tool_calls.add(deduplication_id)
        self._emit_span(
            AgentSpanRecord(
                "ditto.agent.tool",
                {
                    "agent.run_id": run_id,
                    "agent.tool_name": tool.tool_name,
                    "agent.arguments_hash": tool.arguments_hash,
                    "agent.result_hash": tool.result_hash,
                    "agent.evidence_refs_hash": tool.evidence_refs_hash,
                    "agent.artifact_refs_hash": tool.artifact_refs_hash,
                    "agent.authority_hash": state.authority_hash,
                    "agent.temporal_context_hash": state.temporal_context_hash,
                    "agent.latency_seconds": tool.latency_seconds,
                    "agent.status": "completed",
                },
            )
        )
        self._emit_metric(
            AgentMetricRecord(
                "ditto.agent.tool_calls_total",
                1,
                {"agent.tool_name": tool.tool_name, "agent.status": "completed"},
            )
        )

    def record_approval(
        self,
        *,
        run_id: str,
        provider: str,
        action_hash: str,
        approval_count: int,
    ) -> None:
        """Export an aggregate approval identity without action parameters."""
        state = self._state(run_id)
        if state is None:
            return
        self._emit_span(
            AgentSpanRecord(
                "ditto.agent.approval",
                {
                    "agent.run_id": run_id,
                    "agent.provider": provider,
                    "agent.action_hash": action_hash,
                    "agent.approval_count": approval_count,
                    "agent.authority_hash": state.authority_hash,
                    "agent.status": "waiting_approval",
                },
            )
        )
        self._emit_metric(
            AgentMetricRecord(
                "ditto.agent.approvals_total",
                approval_count,
                {
                    "agent.model_profile": state.manifest.model_profile.value,
                    "agent.status": "waiting_approval",
                },
            )
        )

    def record_guardrail(self, *, run_id: str, failure_code: str) -> None:
        """Export one structured guardrail refusal without raw rejected input."""
        state = self._state(run_id)
        if state is None:
            return
        self._emit_span(
            AgentSpanRecord(
                "ditto.agent.guardrail",
                {
                    "agent.run_id": run_id,
                    "agent.authority_hash": state.authority_hash,
                    "agent.temporal_context_hash": state.temporal_context_hash,
                    "agent.failure_code": failure_code,
                    "agent.status": "blocked",
                },
            )
        )

    def finish_run(
        self,
        *,
        run_id: str,
        status: RunStatus,
        budget: AgentBudgetTelemetry,
        failure_code: str | None,
    ) -> None:
        """Export terminal/paused run aggregates and forget local timing state."""
        with self._lock:
            state = self._runs.pop(run_id, None)
        if state is None:
            return
        latency = max(0.0, self._monotonic() - state.started_at)
        attributes = self._base_attributes(state)
        attributes.update(
            {
                "agent.status": status.value,
                "agent.model_attempts": budget.model_attempts,
                "agent.model_turns": budget.model_turns,
                "agent.tool_calls": budget.tool_calls,
                "agent.retries": budget.retries,
                "agent.total_tokens": budget.total_tokens,
                "agent.model_spend_usd": str(budget.model_spend_usd),
                "agent.latency_seconds": latency,
            }
        )
        if failure_code is not None:
            attributes["agent.failure_code"] = failure_code
        if state.campaign_id is not None:
            attributes["agent.campaign_id"] = state.campaign_id
        if state.image_digest is not None:
            attributes["agent.image_digest"] = state.image_digest
        self._emit_span(AgentSpanRecord("ditto.agent.run", attributes))
        metric_attributes = {
            "agent.model_profile": state.manifest.model_profile.value,
            "agent.status": status.value,
        }
        self._emit_metric(
            AgentMetricRecord("ditto.agent.runs_total", 1, metric_attributes)
        )
        self._emit_metric(
            AgentMetricRecord(
                "ditto.agent.run_latency_seconds", latency, metric_attributes
            )
        )

    def _state(self, run_id: str) -> _RunTelemetryState | None:
        with self._lock:
            return self._runs.get(run_id)

    @staticmethod
    def _base_attributes(
        state: _RunTelemetryState,
    ) -> dict[str, AgentTelemetryValue]:
        return {
            "agent.run_id": state.run_id,
            "agent.session_id": state.session_id,
            "agent.authority_hash": state.authority_hash,
            "agent.temporal_context_hash": state.temporal_context_hash,
            "agent.manifest_hash": state.manifest.manifest_hash,
            "agent.model_profile": state.manifest.model_profile.value,
            "agent.model_snapshot": state.manifest.model_snapshot,
            "agent.prompt_hash": state.manifest.prompt_hash,
            "agent.tool_schema_hash": state.manifest.tool_schema_hash,
        }

    def _emit_span(self, record: AgentSpanRecord) -> None:
        try:
            self._sink.emit_span(record)
        except Exception:
            self._record_export_failure()

    def _emit_metric(self, record: AgentMetricRecord) -> None:
        try:
            self._sink.emit_metric(record)
        except Exception:
            self._record_export_failure()

    def _record_export_failure(self) -> None:
        with self._lock:
            self._export_failures += 1


__all__ = [
    "METRIC_DEFINITIONS",
    "AgentBudgetTelemetry",
    "AgentMetricRecord",
    "AgentObservability",
    "AgentSpanRecord",
    "AgentTelemetrySink",
    "AgentToolTelemetry",
    "InMemoryAgentTelemetrySink",
    "NoopAgentTelemetrySink",
]
