"""R4 SQLite risk event/snapshot/report adapter tests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from ditto_application.processes.risk.persistence import (
    DailyRiskProjectionRecord,
    RiskEventRecord,
    RiskPersistenceConflict,
)
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3Projection,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_apps.registry.infra.risk_persistence import (
    SQLiteRiskPersistence,
    initialize_r4_risk_schema,
)
from ditto_risk.continuous_gate import RiskStateSnapshot


@pytest.fixture
def database(tmp_path: Path) -> Path:
    value = tmp_path / "risk.sqlite"
    with closing(sqlite3.connect(value)) as connection:
        initialize_r4_risk_schema(connection)
    return value


@pytest.fixture
def store(database: Path) -> SQLiteRiskPersistence:
    return SQLiteRiskPersistence(lambda: sqlite3.connect(database))


def _snapshot(sequence: int = 0) -> RiskStateSnapshot:
    return RiskStateSnapshot(
        schema_version=1,
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        peak_nav=100_000.0,
        current_drawdown=0.0,
        daily_turnover_notional=0.0,
        locked=False,
        lock_reasons=(),
        event_sequence=sequence,
        processed_event_ids=(),
        processed_event_digests=(),
        position_fingerprint="sha256:positions",
        integrity_hash="sha256:state",
    )


def _projection() -> DailyDecisionV3Projection:
    return DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status="optimal",
            mode="mvo",
            policy_digest="digest",
            solver="OSQP",
            solver_version="1.1.3",
            solver_status="optimal",
            duration_ms=10.0,
        ),
        tail_risk=TailRiskSection(0.04, 0.03, 0.02, 0.025, 42),
        factor_risk=FactorRiskSection(
            "partial",
            0.1,
            {"size": 0.2},
            {"size": 1.0},
            0.0,
        ),
        stress_tests=StressTestSection("r4-v1", {"market": 0.1}),
        reconciliation=ReconciliationSection("reconciled", (), None),
        provenance=ProvenanceSection(
            "2026-04-01T00:00:00Z",
            "2026-03-31T23:00:00Z",
            "2026-03-31T23:00:00Z",
            ("snap-1",),
            "2026-04-01T00:01:00Z",
        ),
    )


def test_risk_events_are_append_only_and_idempotent(
    store: SQLiteRiskPersistence,
) -> None:
    record = RiskEventRecord(
        event_id="risk-event-1",
        account_id="paper-1",
        sleeve_id="core",
        event_sequence=1,
        event_type="fill_applied",
        payload={"fill_id": "fill-1"},
        occurred_at="2026-04-01T02:00:00Z",
    )

    assert store.append_event(record) is True
    assert store.append_event(record) is False
    with pytest.raises(RiskPersistenceConflict):
        store.append_event(replace(record, event_type="different"))


def test_snapshot_cas_rejects_stale_expected_sequence(
    store: SQLiteRiskPersistence,
) -> None:

    store.compare_and_swap_snapshot(_snapshot(), expected_event_sequence=0)
    store.compare_and_swap_snapshot(_snapshot(1), expected_event_sequence=0)

    with pytest.raises(RiskPersistenceConflict, match="CAS"):
        store.compare_and_swap_snapshot(_snapshot(2), expected_event_sequence=0)

    assert store.load_latest_snapshot("paper-1", "core") == _snapshot(1)


def test_snapshot_cas_acquires_write_lock_before_reading_state(
    database: Path,
) -> None:
    statements: list[str] = []

    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(database)
        connection.set_trace_callback(statements.append)
        return connection

    store = SQLiteRiskPersistence(factory)

    store.compare_and_swap_snapshot(_snapshot(), expected_event_sequence=0)

    assert any(statement == "BEGIN IMMEDIATE" for statement in statements)


def test_daily_projection_is_append_only_and_read_by_exact_identity(
    store: SQLiteRiskPersistence,
) -> None:
    record = DailyRiskProjectionRecord(
        report_id="report-1",
        strategy_id="s1",
        account_id="paper-1",
        sleeve_id="core",
        trade_date="2026-04-01",
        projection=_projection(),
        created_at="2026-04-01T00:01:00Z",
    )

    assert store.append_daily_report(record) is True
    assert store.append_daily_report(record) is False
    assert (
        store.get_latest(
            strategy_id="s1",
            trade_date="2026-04-01",
            account_id="paper-1",
            sleeve_id="core",
        )
        == _projection()
    )
    assert (
        store.get_latest(
            strategy_id="s1",
            trade_date="2026-04-02",
            account_id="paper-1",
            sleeve_id="core",
        )
        is None
    )
    assert (
        store.get_latest(
            strategy_id="s1",
            trade_date="2026-04-01",
            account_id="paper-1",
            sleeve_id="satellite",
        )
        is None
    )


def test_adapter_closes_factory_owned_connections(database: Path) -> None:
    opened: list[sqlite3.Connection] = []

    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(database)
        opened.append(connection)
        return connection

    store = SQLiteRiskPersistence(factory)
    store.get_latest(
        strategy_id="missing",
        trade_date=None,
        account_id=None,
        sleeve_id=None,
    )

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")
