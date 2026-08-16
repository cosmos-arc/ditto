"""Privacy and failure-isolation contracts for Agent observability."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    ModelProfile,
    RunStatus,
)
from ditto_agent.models.port import ModelUsage
from ditto_agent.observability import (
    AgentBudgetTelemetry,
    AgentObservability,
    AgentToolTelemetry,
    InMemoryAgentTelemetrySink,
)


def _manifest() -> AgentManifest:
    return AgentManifest(
        manifest_id="manifest-observability-v1",
        agent_version="r5.5.0",
        prompt_version="prompt-v1",
        prompt_hash="b" * 64,
        tool_schema_version="tools-v1",
        tool_schema_hash="c" * 64,
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-v1",
    )


def _run(manifest: AgentManifest) -> AgentRun:
    return AgentRun(
        run_id="run-observability-1",
        session_id="session-observability-1",
        status=RunStatus.QUEUED,
        objective="Never export sk-future-secret or a full position payload.",
        authority_hash="a" * 64,
        max_model_tokens=1_000,
        max_model_spend_usd=Decimal("0.10"),
        model_profile=ModelProfile.BALANCED,
        manifest_hash=manifest.manifest_hash,
        created_at=datetime(2026, 8, 17, 9, tzinfo=UTC),
    )


def _budget() -> AgentBudgetTelemetry:
    return AgentBudgetTelemetry(
        model_attempts=1,
        model_turns=1,
        tool_calls=1,
        retries=0,
        total_tokens=130,
        model_spend_usd=Decimal("0.00022"),
        elapsed_seconds=0.125,
        exhausted_reason=None,
    )


def test_agent_observability_exports_only_redacted_hash_bound_records() -> None:
    sink = InMemoryAgentTelemetrySink()
    observer = AgentObservability(sink=sink, monotonic=lambda: 10.0)
    manifest = _manifest()
    run = _run(manifest)

    observer.start_run(
        run=run,
        manifest=manifest,
        temporal_context_hash="d" * 64,
    )
    assert "sk-future-secret" not in repr(observer._runs)
    assert "full position payload" not in repr(observer._runs)
    observer.record_model(
        run_id=run.run_id,
        usage=ModelUsage(requests=1, input_tokens=100, output_tokens=30),
        budget=_budget(),
        latency_seconds=0.1,
    )
    observer.record_tool(
        run_id=run.run_id,
        tool=AgentToolTelemetry(
            call_id="call-1",
            tool_name="research_experiment_evidence",
            arguments_hash="e" * 64,
            result_hash="f" * 64,
            evidence_refs_hash="1" * 64,
            artifact_refs_hash="2" * 64,
            latency_seconds=0.02,
        ),
    )
    observer.record_approval(
        run_id=run.run_id,
        provider="scripted",
        action_hash="3" * 64,
        approval_count=1,
    )
    observer.finish_run(
        run_id=run.run_id,
        status=RunStatus.COMPLETED,
        budget=_budget(),
        failure_code=None,
    )

    assert {record.name for record in sink.spans} == {
        "ditto.agent.run",
        "ditto.agent.model",
        "ditto.agent.tool",
        "ditto.agent.approval",
        "ditto.agent.cost",
    }
    exported = repr((sink.spans, sink.metrics)).lower()
    assert "sk-future-secret" not in exported
    assert "full position payload" not in exported
    assert "objective" not in exported
    assert "response" not in exported
    assert "agent.prompt_hash" in exported
    assert "arguments_hash" in exported
    assert "result_hash" in exported
    assert {metric.name for metric in sink.metrics} >= {
        "ditto.agent.runs_total",
        "ditto.agent.run_latency_seconds",
        "ditto.agent.model_cost_usd",
        "ditto.agent.model_tokens",
    }


class _FailingSink:
    def emit_span(self, record: object) -> None:
        del record
        raise RuntimeError("span exporter unavailable")

    def emit_metric(self, record: object) -> None:
        del record
        raise RuntimeError("metric exporter unavailable")


def test_exporter_failure_is_counted_and_never_raised_to_business_code() -> None:
    observer = AgentObservability(sink=_FailingSink(), monotonic=lambda: 10.0)
    manifest = _manifest()
    run = _run(manifest)

    observer.start_run(
        run=run,
        manifest=manifest,
        temporal_context_hash="d" * 64,
    )
    observer.record_model(
        run_id=run.run_id,
        usage=ModelUsage(requests=1, input_tokens=1, output_tokens=1),
        budget=_budget(),
        latency_seconds=0.1,
    )
    observer.finish_run(
        run_id=run.run_id,
        status=RunStatus.COMPLETED,
        budget=_budget(),
        failure_code=None,
    )

    assert observer.export_failures >= 1
