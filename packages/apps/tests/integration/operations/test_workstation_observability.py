"""OPS-02/05 correlation trace and dashboard integration tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from ditto_apps.operations.workstation_metrics import (
    WORKSTATION_DASHBOARD,
    WORKSTATION_METRIC_DEFINITIONS,
)
from ditto_apps.operations.workstation_trace import (
    WorkstationTraceError,
    run_correlated_workstation_trace,
)
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


def test_one_correlation_id_links_ingest_agent_and_ledger_spans() -> None:
    calls: list[str] = []

    def stage(name: str, evidence_ref: str):
        def run() -> str:
            calls.append(name)
            return evidence_ref

        return run

    receipt = run_correlated_workstation_trace(
        correlation_id="corr-20260831-001",
        ingest=stage("ingest", "ingestion:run-1"),
        agent=stage("agent", "agent:run-1"),
        ledger=stage("ledger", "ledger:event-1"),
        monotonic=iter((10.0, 10.2)).__next__,
    )

    assert calls == ["ingest", "agent", "ledger"]
    assert receipt.correlation_id == "corr-20260831-001"
    assert tuple(item.stage for item in receipt.stages) == (
        "ingest",
        "agent",
        "ledger",
    )
    spans = get_recorded_spans()
    stage_spans = [item for item in spans if item.name.startswith("ditto.workstation.")]
    assert {dict(item.attributes)["correlation_id"] for item in stage_spans} == {
        receipt.correlation_id
    }
    assert len({item.context.trace_id for item in stage_spans}) == 1
    assert get_recorded_metrics()["metrics_recorded"] is True


def test_trace_stops_before_downstream_side_effect_after_failure() -> None:
    called = False

    def fail_agent() -> str:
        raise RuntimeError("agent unavailable")

    def ledger() -> str:
        nonlocal called
        called = True
        return "ledger:event-1"

    with pytest.raises(WorkstationTraceError, match="agent"):
        run_correlated_workstation_trace(
            correlation_id="corr-failed",
            ingest=lambda: "ingestion:run-1",
            agent=fail_agent,
            ledger=ledger,
        )

    assert called is False


def test_dashboard_contract_covers_all_required_operational_signals() -> None:
    assert set(WORKSTATION_DASHBOARD) == {
        "freshness",
        "dq",
        "run",
        "paper",
        "agent",
        "e2e",
    }
    known = {
        "ditto.data.freshness_days",
        "ditto.dq.batch.issues_total",
        "ditto.agent.runs_total",
        *(item["instrument_name"] for item in WORKSTATION_METRIC_DEFINITIONS),
    }
    assert all(metric in known for metric in WORKSTATION_DASHBOARD.values())
