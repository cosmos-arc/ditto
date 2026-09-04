"""Real in-memory OTel wiring for redacted Agent telemetry."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    ModelProfile,
    RunStatus,
)
from ditto_agent.observability import AgentBudgetTelemetry
from ditto_apps.registry.agent.observability import build_agent_observability
from ditto_apps.registry.infra.observability import register_app_metric_definitions
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    get_recorded_metrics,
    get_recorded_spans,
    init,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def _recording_otel() -> Generator[None]:
    reset_for_testing()
    register_app_metric_definitions()
    init(
        ObservabilityConfig(
            environment=Environment.TESTING,
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            tracing_enabled=True,
            tracing_sample_rate=1.0,
            metrics_enabled=True,
        ),
        force=True,
    )
    yield
    reset_for_testing()


def _manifest() -> AgentManifest:
    return AgentManifest(
        manifest_id="manifest-otel-v1",
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
        run_id="run-otel-1",
        session_id="session-otel-1",
        status=RunStatus.QUEUED,
        objective="Do not export bearer secret-token-value.",
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
        tool_calls=0,
        retries=0,
        total_tokens=2,
        model_spend_usd=Decimal("0.00001"),
        elapsed_seconds=0.1,
        exhausted_reason=None,
    )


def test_explicit_agent_otel_wiring_exports_redacted_spans_and_metrics() -> None:
    observer = build_agent_observability(enabled=True, monotonic=lambda: 10.0)
    manifest = _manifest()
    run = _run(manifest)

    observer.start_run(
        run=run,
        manifest=manifest,
        temporal_context_hash="d" * 64,
    )
    observer.finish_run(
        run_id=run.run_id,
        status=RunStatus.COMPLETED,
        budget=_budget(),
        failure_code=None,
    )

    spans = get_recorded_spans()
    assert [item.name for item in spans] == ["ditto.agent.run"]
    attributes = dict(spans[0].attributes)
    assert attributes["agent.run_id"] == run.run_id
    assert "secret-token-value" not in repr(attributes)
    assert get_recorded_metrics()["metrics_recorded"] is True


def test_agent_otel_exporter_is_noop_until_explicitly_enabled() -> None:
    observer = build_agent_observability(enabled=False, monotonic=lambda: 10.0)
    manifest = _manifest()
    run = _run(manifest)

    observer.start_run(
        run=run,
        manifest=manifest,
        temporal_context_hash="d" * 64,
    )
    observer.finish_run(
        run_id=run.run_id,
        status=RunStatus.COMPLETED,
        budget=_budget(),
        failure_code=None,
    )

    assert get_recorded_spans() == []
