"""SQLite adapters for append-only R4 risk evidence and snapshot CAS."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import cast

from dishka import Provider, Scope, provide
from ditto_application.processes.risk.persistence import (
    DailyRiskProjectionRecord,
    RiskEventRecord,
    RiskPersistenceConflict,
)
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3Projection,
    DailyDecisionV3ProjectionReader,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_risk.continuous_gate import RiskStateSnapshot

__all__ = [
    "RiskPersistenceProvider",
    "SQLiteRiskPersistence",
    "initialize_r4_risk_schema",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS risk_events (
    event_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    sleeve_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(account_id, sleeve_id, event_sequence)
);
CREATE TABLE IF NOT EXISTS risk_state_snapshots (
    snapshot_version INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    sleeve_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    UNIQUE(account_id, sleeve_id, event_sequence)
);
CREATE TABLE IF NOT EXISTS daily_risk_reports (
    report_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    sleeve_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    projection_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_risk_report_identity
ON daily_risk_reports(strategy_id, trade_date, account_id, created_at, report_id);
"""
_PAIR_SIZE = 2


def initialize_r4_risk_schema(connection: sqlite3.Connection) -> None:
    """Create R4 tables on an explicitly supplied database connection."""
    connection.executescript(_SCHEMA)
    connection.commit()


class SQLiteRiskPersistence:
    """Append-only SQLite adapter; schema creation is an explicit separate action."""

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection],
    ) -> None:
        """Store a connection factory without creating or migrating any database."""
        self._connection_factory = connection_factory

    def append_event(self, record: RiskEventRecord) -> bool:
        """Append one event or recognize an exact idempotent replay."""
        payload = _json(record.payload)
        with closing(self._connection_factory()) as connection:
            existing = connection.execute(
                """
                SELECT account_id, sleeve_id, event_sequence, event_type,
                       payload_json, occurred_at
                FROM risk_events WHERE event_id = ?
                """,
                (record.event_id,),
            ).fetchone()
            values = (
                record.account_id,
                record.sleeve_id,
                record.event_sequence,
                record.event_type,
                payload,
                record.occurred_at,
            )
            if existing is not None:
                if tuple(existing) == values:
                    return False
                raise RiskPersistenceConflict(
                    f"risk event identity conflict: {record.event_id}"
                )
            try:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO risk_events(
                            event_id, account_id, sleeve_id, event_sequence,
                            event_type, payload_json, occurred_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (record.event_id, *values),
                    )
            except sqlite3.IntegrityError as exc:
                raise RiskPersistenceConflict("risk event sequence conflict") from exc
        return True

    def compare_and_swap_snapshot(
        self,
        snapshot: RiskStateSnapshot,
        *,
        expected_event_sequence: int,
    ) -> None:
        """Append a snapshot when the previously persisted sequence matches."""
        with closing(self._connection_factory()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    """
                    SELECT event_sequence FROM risk_state_snapshots
                    WHERE account_id = ? AND sleeve_id = ?
                    ORDER BY snapshot_version DESC LIMIT 1
                    """,
                    (snapshot.account_id, snapshot.sleeve_id),
                ).fetchone()
                current_sequence = (
                    0 if current is None else _required_int_value(current[0])
                )
                if current_sequence != expected_event_sequence:
                    raise RiskPersistenceConflict(
                        " ".join(
                            (
                                "risk state CAS missed:",
                                f"expected {expected_event_sequence},",
                                f"got {current_sequence}",
                            )
                        )
                    )
                try:
                    connection.execute(
                        """
                        INSERT INTO risk_state_snapshots(
                            account_id, sleeve_id, event_sequence, snapshot_json
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            snapshot.account_id,
                            snapshot.sleeve_id,
                            snapshot.event_sequence,
                            _json(asdict(snapshot)),
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise RiskPersistenceConflict(
                        "risk state CAS insert conflict"
                    ) from exc
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def load_latest_snapshot(
        self,
        account_id: str,
        sleeve_id: str,
    ) -> RiskStateSnapshot | None:
        """Read the latest snapshot without changing its domain evidence."""
        with closing(self._connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT snapshot_json FROM risk_state_snapshots
                WHERE account_id = ? AND sleeve_id = ?
                ORDER BY snapshot_version DESC LIMIT 1
                """,
                (account_id, sleeve_id),
            ).fetchone()
        if row is None:
            return None
        data = _mapping(json.loads(str(row[0])))
        return RiskStateSnapshot(
            schema_version=_required_int(data, "schema_version"),
            account_id=_required_str(data, "account_id"),
            sleeve_id=_required_str(data, "sleeve_id"),
            trade_date=_optional_str(data.get("trade_date")),
            peak_nav=_required_float(data, "peak_nav"),
            current_drawdown=_required_float(data, "current_drawdown"),
            daily_turnover_notional=_required_float(
                data,
                "daily_turnover_notional",
            ),
            locked=_required_bool(data, "locked"),
            lock_reasons=_string_tuple(data["lock_reasons"]),
            event_sequence=_required_int(data, "event_sequence"),
            processed_event_ids=_string_tuple(data["processed_event_ids"]),
            processed_event_digests=_string_pair_tuple(data["processed_event_digests"]),
            position_fingerprint=_optional_str(data.get("position_fingerprint")),
            integrity_hash=str(data["integrity_hash"]),
        )

    def append_daily_report(self, record: DailyRiskProjectionRecord) -> bool:
        """Append a V3 projection or recognize an exact report replay."""
        payload = _json(asdict(record.projection))
        values = (
            record.strategy_id,
            record.account_id,
            record.sleeve_id,
            record.trade_date,
            payload,
            record.created_at,
        )
        with closing(self._connection_factory()) as connection:
            existing = connection.execute(
                """
                SELECT strategy_id, account_id, sleeve_id, trade_date,
                       projection_json, created_at
                FROM daily_risk_reports WHERE report_id = ?
                """,
                (record.report_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == values:
                    return False
                raise RiskPersistenceConflict(
                    f"daily risk report identity conflict: {record.report_id}"
                )
            with connection:
                connection.execute(
                    """
                    INSERT INTO daily_risk_reports(
                        report_id, strategy_id, account_id, sleeve_id,
                        trade_date, projection_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (record.report_id, *values),
                )
        return True

    def get_latest(
        self,
        *,
        strategy_id: str,
        trade_date: str | None,
        account_id: str | None,
        sleeve_id: str | None,
    ) -> DailyDecisionV3Projection | None:
        """Read the latest projection matching every provided identity field."""
        with closing(self._connection_factory()) as connection:
            try:
                row = connection.execute(
                    """
                    SELECT projection_json FROM daily_risk_reports
                    WHERE strategy_id = ?
                      AND (? IS NULL OR trade_date = ?)
                      AND (? IS NULL OR account_id = ?)
                      AND (? IS NULL OR sleeve_id = ?)
                    ORDER BY trade_date DESC, created_at DESC, report_id DESC
                    LIMIT 1
                    """,
                    (
                        strategy_id,
                        trade_date,
                        trade_date,
                        account_id,
                        account_id,
                        sleeve_id,
                        sleeve_id,
                    ),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc):
                    return None
                raise
        return None if row is None else _projection_from_json(str(row[0]))


class RiskPersistenceProvider(Provider):
    """Composition-root binding for the read-only V3 projection port."""

    scope = Scope.APP

    @provide
    def daily_decision_v3_projection_reader(
        self,
        data_root: Path,
    ) -> DailyDecisionV3ProjectionReader:
        """Bind metadata SQLite without implicitly creating R4 schema."""
        database = data_root / "metadata" / "metadata.sqlite"
        return SQLiteRiskPersistence(lambda: sqlite3.connect(database))


def _projection_from_json(payload: str) -> DailyDecisionV3Projection:
    data = _mapping(json.loads(payload))
    portfolio = _mapping(data["portfolio_construction"])
    tail = _mapping(data["tail_risk"])
    factor = _mapping(data["factor_risk"])
    stress = _mapping(data["stress_tests"])
    reconciliation = _mapping(data["reconciliation"])
    provenance = _mapping(data["provenance"])
    return DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status=_required_str(portfolio, "status"),
            mode=_optional_str(portfolio.get("mode")),
            policy_digest=_optional_str(portfolio.get("policy_digest")),
            solver=_optional_str(portfolio.get("solver")),
            solver_version=_optional_str(portfolio.get("solver_version")),
            solver_status=_optional_str(portfolio.get("solver_status")),
            duration_ms=_optional_float(portfolio.get("duration_ms")),
            failure_code=_optional_str(portfolio.get("failure_code")),
        ),
        tail_risk=TailRiskSection(
            historical_es99=_optional_float(tail.get("historical_es99")),
            historical_var99=_optional_float(tail.get("historical_var99")),
            parametric_var99=_optional_float(tail.get("parametric_var99")),
            monte_carlo_var99=_optional_float(tail.get("monte_carlo_var99")),
            monte_carlo_seed=_optional_int(tail.get("monte_carlo_seed")),
        ),
        factor_risk=FactorRiskSection(
            availability=_required_str(factor, "availability"),
            total_risk=_optional_float(factor.get("total_risk")),
            marginal_contributions={
                key: _required_float_value(value)
                for key, value in _mapping(factor["marginal_contributions"]).items()
            },
            percentage_contributions={
                key: _required_float_value(value)
                for key, value in _mapping(factor["percentage_contributions"]).items()
            },
            euler_residual=_optional_float(factor.get("euler_residual")),
        ),
        stress_tests=StressTestSection(
            catalog_version=_required_str(stress, "catalog_version"),
            losses={
                key: _required_float_value(value)
                for key, value in _mapping(stress["losses"]).items()
            },
            unavailable_scenarios=_string_tuple(
                stress.get("unavailable_scenarios", ())
            ),
        ),
        reconciliation=ReconciliationSection(
            status=_required_str(reconciliation, "status"),
            differences=_string_tuple(reconciliation["differences"]),
            alert_idempotency_key=_optional_str(
                reconciliation.get("alert_idempotency_key")
            ),
        ),
        provenance=ProvenanceSection(
            decision_time=_optional_str(provenance.get("decision_time")),
            knowledge_cutoff=_optional_str(provenance.get("knowledge_cutoff")),
            publication_cutoff=_optional_str(provenance.get("publication_cutoff")),
            source_snapshot_ids=_string_tuple(provenance["source_snapshot_ids"]),
            generated_at=_optional_str(provenance.get("generated_at")),
        ),
        blocking_reasons=_string_tuple(data.get("blocking_reasons", ())),
    )


def _json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("persisted risk payload must be an object")
    mapping = cast(Mapping[object, object], value)
    return {str(key): item for key, item in mapping.items()}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("persisted risk payload must contain a string sequence")
    items = cast("list[object] | tuple[object, ...]", value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError("persisted risk payload must contain a string sequence")
    return tuple(cast("list[str] | tuple[str, ...]", items))


def _string_pair_tuple(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("persisted risk payload must contain string pairs")
    items = cast("list[object] | tuple[object, ...]", value)
    result: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, (list, tuple)):
            raise ValueError("persisted risk payload must contain string pairs")
        pair = cast("list[object] | tuple[object, ...]", item)
        if len(pair) != _PAIR_SIZE or not all(isinstance(part, str) for part in pair):
            raise ValueError("persisted risk payload must contain string pairs")
        strings = cast("list[str] | tuple[str, ...]", pair)
        result.append((strings[0], strings[1]))
    return tuple(result)


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("persisted risk payload value must be a string or null")
    return value


def _optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    return _required_float_value(value)


def _optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    return _required_int_value(value)


def _required_str(data: Mapping[str, object], name: str) -> str:
    value = data[name]
    if not isinstance(value, str):
        raise ValueError(f"persisted risk field {name!r} must be a string")
    return value


def _required_int(data: Mapping[str, object], name: str) -> int:
    return _required_int_value(data[name])


def _required_int_value(value: object) -> int:
    if type(value) is not int:
        raise ValueError("persisted risk payload value must be an integer")
    return value


def _required_float(data: Mapping[str, object], name: str) -> float:
    return _required_float_value(data[name])


def _required_float_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("persisted risk payload value must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("persisted risk payload value must be finite")
    return result


def _required_bool(data: Mapping[str, object], name: str) -> bool:
    value = data[name]
    if type(value) is not bool:
        raise ValueError(f"persisted risk field {name!r} must be boolean")
    return value
