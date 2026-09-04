"""SQLite persistence for recoverable formal paper sessions."""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from datetime import datetime
from types import TracebackType
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import MarketSnapshot
from ditto_platform.foundation import SQLiteClient, SQLitePool

from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperFill,
    PaperOrder,
    PaperRealityResult,
    PaperRealityStatus,
)
from ditto_execution.paper.session import (
    PaperExecutionRecord,
    PaperReconciliation,
    PaperSession,
    PaperSessionConflictError,
    PaperSessionMutation,
    PaperSessionStatus,
)

__all__ = ["SqlitePaperSessionStore"]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_sessions (
    session_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_session_mutations (
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    action TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (session_id, idempotency_key),
    FOREIGN KEY (session_id) REFERENCES paper_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS paper_executions (
    execution_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    ledger_event_id TEXT,
    payload_json TEXT NOT NULL,
    UNIQUE (session_id, idempotency_key),
    FOREIGN KEY (session_id) REFERENCES paper_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS ix_paper_executions_session_seq
    ON paper_executions(session_id, execution_seq);

CREATE TABLE IF NOT EXISTS paper_reconciliations (
    reconciliation_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES paper_sessions(session_id)
);
"""


class SqlitePaperSessionStore(AbstractContextManager["SqlitePaperSessionStore"]):
    """Durable session store with CAS transitions and exact execution replay."""

    _client: SQLiteClient | None

    def __init__(self, database: str | SQLiteClient) -> None:
        if isinstance(database, str):
            owned_pool = SQLitePool(database)
            client = SQLiteClient(owned_pool)
        else:
            owned_pool = None
            client = database
        client.conn.executescript(_SCHEMA)
        client.conn.commit()
        self._client = client
        self._owned_pool = owned_pool

    @property
    def _db(self) -> sqlite3.Connection:
        if self._client is None:
            raise PaperSessionConflictError("paper session store is closed")
        return self._client.conn

    def create_session(
        self,
        session: PaperSession,
        mutation: PaperSessionMutation | None = None,
    ) -> PaperSession:
        """Create one session and optional command receipt atomically."""
        existing = self.get_session(session.session_id)
        if existing is not None:
            if existing != session:
                raise PaperSessionConflictError("paper session identity conflict")
            return existing
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute(
                "INSERT INTO paper_sessions VALUES (?, ?, ?)",
                (session.session_id, session.revision, _dump(session)),
            )
            if mutation is not None:
                self._insert_mutation(mutation)
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise PaperSessionConflictError("paper session identity conflict") from exc
        except Exception:
            self._db.rollback()
            raise
        return session

    def get_session(self, session_id: str) -> PaperSession | None:
        """Read and validate one persisted session."""
        row = self._db.execute(
            "SELECT payload_json FROM paper_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return _session(_load(row[0])) if row is not None else None

    def update_session(
        self,
        session: PaperSession,
        *,
        expected_revision: int,
        mutation: PaperSessionMutation,
    ) -> PaperSession:
        """Apply a revision-guarded lifecycle mutation atomically."""
        try:
            self._db.execute("BEGIN IMMEDIATE")
            cursor = self._db.execute(
                """
                UPDATE paper_sessions
                SET revision = ?, payload_json = ?
                WHERE session_id = ? AND revision = ?
                """,
                (
                    session.revision,
                    _dump(session),
                    session.session_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise PaperSessionConflictError("paper session revision conflict")
            self._insert_mutation(mutation)
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise PaperSessionConflictError(
                "paper session idempotency conflict"
            ) from exc
        except Exception:
            self._db.rollback()
            raise
        return session

    def _insert_mutation(self, mutation: PaperSessionMutation) -> None:
        self._db.execute(
            """
            INSERT INTO paper_session_mutations
                (session_id, idempotency_key, action, request_hash, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                mutation.session_id,
                mutation.idempotency_key,
                mutation.action,
                mutation.request_hash,
                _dump(mutation),
            ),
        )

    def get_mutation(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> PaperSessionMutation | None:
        """Read one exact persisted lifecycle receipt."""
        row = self._db.execute(
            """
            SELECT payload_json FROM paper_session_mutations
            WHERE session_id = ? AND idempotency_key = ?
            """,
            (session_id, idempotency_key),
        ).fetchone()
        return _mutation(_load(row[0])) if row is not None else None

    def append_execution(self, record: PaperExecutionRecord) -> PaperExecutionRecord:
        """Append or exactly replay one persisted execution."""
        existing = self.get_execution(record.session_id, record.idempotency_key)
        if existing is not None:
            if existing.request_hash != record.request_hash:
                raise PaperSessionConflictError("paper execution idempotency conflict")
            return existing
        try:
            self._db.execute(
                """
                INSERT INTO paper_executions
                    (execution_id, session_id, idempotency_key, request_hash,
                     ledger_event_id, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.execution_id,
                    record.session_id,
                    record.idempotency_key,
                    record.request_hash,
                    record.ledger_event_id,
                    _dump(record),
                ),
            )
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise PaperSessionConflictError(
                "paper execution identity or idempotency conflict"
            ) from exc
        return record

    def get_execution(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> PaperExecutionRecord | None:
        """Resolve one persisted execution idempotency key."""
        row = self._db.execute(
            """
            SELECT payload_json FROM paper_executions
            WHERE session_id = ? AND idempotency_key = ?
            """,
            (session_id, idempotency_key),
        ).fetchone()
        return _execution(_load(row[0])) if row is not None else None

    def list_executions(self, session_id: str) -> tuple[PaperExecutionRecord, ...]:
        """List persisted executions in append order."""
        rows = self._db.execute(
            """
            SELECT payload_json FROM paper_executions
            WHERE session_id = ? ORDER BY execution_seq ASC
            """,
            (session_id,),
        ).fetchall()
        return tuple(_execution(_load(row[0])) for row in rows)

    def mark_execution_ledgered(
        self,
        execution_id: str,
        event_id: str,
    ) -> PaperExecutionRecord:
        """Attach one exact account event to a persisted execution."""
        row = self._db.execute(
            """
            SELECT payload_json FROM paper_executions WHERE execution_id = ?
            """,
            (execution_id,),
        ).fetchone()
        if row is None:
            raise PaperSessionConflictError("paper execution not found")
        existing = _execution(_load(row[0]))
        updated = existing.with_ledger_event(event_id)
        cursor = self._db.execute(
            """
            UPDATE paper_executions
            SET ledger_event_id = ?, payload_json = ?
            WHERE execution_id = ? AND (ledger_event_id IS NULL OR ledger_event_id = ?)
            """,
            (event_id, _dump(updated), execution_id, event_id),
        )
        if cursor.rowcount != 1:
            self._db.rollback()
            raise PaperSessionConflictError("paper execution ledger event conflict")
        self._db.commit()
        return updated

    def append_reconciliation(
        self,
        reconciliation: PaperReconciliation,
    ) -> PaperReconciliation:
        """Append or exactly replay one EOD reconciliation."""
        row = self._db.execute(
            """
            SELECT payload_json FROM paper_reconciliations
            WHERE reconciliation_id = ?
            """,
            (reconciliation.reconciliation_id,),
        ).fetchone()
        if row is not None:
            existing = _reconciliation(_load(row[0]))
            if existing != reconciliation:
                raise PaperSessionConflictError(
                    "paper reconciliation identity conflict"
                )
            return existing
        try:
            self._db.execute(
                """
                INSERT INTO paper_reconciliations
                    (reconciliation_id, session_id, payload_json)
                VALUES (?, ?, ?)
                """,
                (
                    reconciliation.reconciliation_id,
                    reconciliation.session_id,
                    _dump(reconciliation),
                ),
            )
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise PaperSessionConflictError(
                "paper reconciliation identity conflict"
            ) from exc
        return reconciliation

    def latest_reconciliation(self, session_id: str) -> PaperReconciliation | None:
        """Read the latest persisted reconciliation for a session."""
        row = self._db.execute(
            """
            SELECT payload_json FROM paper_reconciliations
            WHERE session_id = ? ORDER BY reconciliation_seq DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return _reconciliation(_load(row[0])) if row is not None else None

    def get_reconciliation(
        self,
        reconciliation_id: str,
    ) -> PaperReconciliation | None:
        """Read a persisted reconciliation by identity."""
        row = self._db.execute(
            """
            SELECT payload_json FROM paper_reconciliations
            WHERE reconciliation_id = ?
            """,
            (reconciliation_id,),
        ).fetchone()
        return _reconciliation(_load(row[0])) if row is not None else None

    def close(self) -> None:
        """Close only resources owned by this store instance."""
        self._client = None
        if self._owned_pool is not None:
            self._owned_pool.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close owned resources when leaving a context manager."""
        self.close()


def _dump(value: object) -> str:
    return orjson.dumps(
        value,
        option=orjson.OPT_SERIALIZE_DATACLASS | orjson.OPT_SORT_KEYS,
    ).decode()


def _load(value: str) -> dict[str, object]:
    decoded = orjson.loads(value)
    if not isinstance(decoded, dict):
        raise PaperSessionConflictError("paper payload must be an object")
    return cast(dict[str, object], decoded)


def _text(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise PaperSessionConflictError(f"paper payload field {key} must be text")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise PaperSessionConflictError(f"paper payload field {key} must be integer")
    return value


def _number(payload: dict[str, object], key: str) -> float:
    value = payload[key]
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise PaperSessionConflictError(f"paper payload field {key} must be numeric")
    return float(value)


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if not isinstance(value, dict):
        raise PaperSessionConflictError(f"paper payload field {key} must be object")
    return cast(dict[str, object], value)


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PaperSessionConflictError(f"paper payload field {key} must be text")
    return value


def _session(payload: dict[str, object]) -> PaperSession:
    return PaperSession(
        session_id=_text(payload, "session_id"),
        account_id=_text(payload, "account_id"),
        strategy_id=_text(payload, "strategy_id"),
        trade_date=_text(payload, "trade_date"),
        status=PaperSessionStatus(_text(payload, "status")),
        revision=_integer(payload, "revision"),
        created_at=datetime.fromisoformat(_text(payload, "created_at")),
        updated_at=datetime.fromisoformat(_text(payload, "updated_at")),
        pause_reason=_optional_text(payload, "pause_reason"),
    )


def _mutation(payload: dict[str, object]) -> PaperSessionMutation:
    return PaperSessionMutation(
        session_id=_text(payload, "session_id"),
        idempotency_key=_text(payload, "idempotency_key"),
        action=_text(payload, "action"),
        request_hash=_text(payload, "request_hash"),
        resulting_session=_session(_object(payload, "resulting_session")),
    )


def _execution(payload: dict[str, object]) -> PaperExecutionRecord:
    return PaperExecutionRecord(
        execution_id=_text(payload, "execution_id"),
        session_id=_text(payload, "session_id"),
        account_id=_text(payload, "account_id"),
        idempotency_key=_text(payload, "idempotency_key"),
        request_hash=_text(payload, "request_hash"),
        result=_reality_result(_object(payload, "result")),
        assumption=_assumption(_object(payload, "assumption")),
        lineage=_lineage(_object(payload, "lineage")),
        created_at=datetime.fromisoformat(_text(payload, "created_at")),
        ledger_event_id=_optional_text(payload, "ledger_event_id"),
    )


def _assumption(payload: dict[str, object]) -> FillAssumption:
    return FillAssumption(
        assumption_id=_text(payload, "assumption_id"),
        version=_integer(payload, "version"),
        reference_price_field=_text(payload, "reference_price_field"),
        slippage_bps=_number(payload, "slippage_bps"),
    )


def _lineage(payload: dict[str, object]) -> MarketSnapshotLineage:
    snapshot_payload = _object(payload, "snapshot")
    snapshot = MarketSnapshot(
        trade_date=_text(snapshot_payload, "trade_date"),
        instrument_id=InstrumentId(_integer(snapshot_payload, "instrument_id")),
        open=_number(snapshot_payload, "open"),
        high=_number(snapshot_payload, "high"),
        low=_number(snapshot_payload, "low"),
        close=_number(snapshot_payload, "close"),
        prev_close=_number(snapshot_payload, "prev_close"),
        volume=_number(snapshot_payload, "volume"),
        amount=_number(snapshot_payload, "amount"),
        is_suspended=bool(snapshot_payload.get("is_suspended", False)),
        limit_up=_optional_number(snapshot_payload, "limit_up"),
        limit_down=_optional_number(snapshot_payload, "limit_down"),
        avg_volume_20d=_optional_number(snapshot_payload, "avg_volume_20d"),
    )
    rebuilt = MarketSnapshotLineage.create(
        snapshot=snapshot,
        dataset_id=_text(payload, "dataset_id"),
        source=_text(payload, "source"),
        source_snapshot_id=_text(payload, "source_snapshot_id"),
        observed_at=datetime.fromisoformat(_text(payload, "observed_at")),
        publication_cutoff=datetime.fromisoformat(_text(payload, "publication_cutoff")),
    )
    if rebuilt.snapshot_hash != _text(
        payload, "snapshot_hash"
    ) or rebuilt.lineage_hash != _text(payload, "lineage_hash"):
        raise PaperSessionConflictError("paper market lineage hash mismatch")
    return rebuilt


def _optional_number(payload: dict[str, object], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise PaperSessionConflictError(f"paper payload field {key} must be numeric")
    return float(value)


def _reality_result(payload: dict[str, object]) -> PaperRealityResult:
    fill_payload = payload.get("fill")
    return PaperRealityResult(
        status=PaperRealityStatus(_text(payload, "status")),
        order=_paper_order(_object(payload, "order")),
        reason=_optional_text(payload, "reason"),
        fill=(
            _paper_fill(cast(dict[str, object], fill_payload))
            if isinstance(fill_payload, dict)
            else None
        ),
    )


def _paper_order(payload: dict[str, object]) -> PaperOrder:
    ticket_payload = _object(payload, "ticket")
    order_payload = _object(ticket_payload, "order")
    client_payload = _object(order_payload, "client_id")
    events_raw = ticket_payload.get("order_events", [])
    if not isinstance(events_raw, list):
        raise PaperSessionConflictError("paper order_events must be a list")
    raw_items = cast(list[object], events_raw)
    events = tuple(
        _order_event(cast(dict[str, object], raw_item))
        for raw_item in raw_items
        if isinstance(raw_item, dict)
    )
    order = Order(
        client_id=ClientOrderId(value=_text(client_payload, "value")),
        instrument_id=InstrumentId(_integer(order_payload, "instrument_id")),
        order_type=OrderType(_text(order_payload, "order_type")),
        direction=OrderSide(_text(order_payload, "direction")),
        quantity=_integer(order_payload, "quantity"),
        price=_optional_number(order_payload, "price"),
        stop_price=_optional_number(order_payload, "stop_price"),
        trade_date=_optional_text(order_payload, "trade_date"),
    )
    ticket = OrderTicket(
        order=order,
        status=OrderStatus(_text(ticket_payload, "status")),
        filled_quantity=_integer(ticket_payload, "filled_quantity"),
        filled_price=_optional_number(ticket_payload, "filled_price"),
        average_fill_price=_optional_number(ticket_payload, "average_fill_price"),
        broker_order_id=_optional_text(ticket_payload, "broker_order_id"),
        order_events=events,
    )
    return PaperOrder(
        session_id=_text(payload, "session_id"),
        account_id=_text(payload, "account_id"),
        idempotency_key=_text(payload, "idempotency_key"),
        submitted_at=datetime.fromisoformat(_text(payload, "submitted_at")),
        ticket=ticket,
    )


def _order_event(payload: dict[str, object]) -> OrderEvent:
    client_payload = _object(payload, "client_id")
    return OrderEvent(
        client_id=ClientOrderId(value=_text(client_payload, "value")),
        trigger=OrderTrigger(_text(payload, "trigger")),
        status=OrderStatus(_text(payload, "status")),
        fill_price=_optional_number(payload, "fill_price"),
        fill_quantity=_integer(payload, "fill_quantity"),
        fee=_number(payload, "fee"),
        message=_optional_text(payload, "message"),
        timestamp=datetime.fromisoformat(_text(payload, "timestamp")),
    )


def _paper_fill(payload: dict[str, object]) -> PaperFill:
    return PaperFill(
        fill_id=_text(payload, "fill_id"),
        session_id=_text(payload, "session_id"),
        account_id=_text(payload, "account_id"),
        order_id=_text(payload, "order_id"),
        instrument_id=InstrumentId(_integer(payload, "instrument_id")),
        direction=OrderSide(_text(payload, "direction")),
        quantity=_integer(payload, "quantity"),
        trade_date=_text(payload, "trade_date"),
        settlement_date=_text(payload, "settlement_date"),
        event_time=datetime.fromisoformat(_text(payload, "event_time")),
        reference_price=_number(payload, "reference_price"),
        fill_price=_number(payload, "fill_price"),
        slippage=_number(payload, "slippage"),
        commission=_number(payload, "commission"),
        transfer_fee=_number(payload, "transfer_fee"),
        tax=_number(payload, "tax"),
        total_cost=_number(payload, "total_cost"),
        assumption_hash=_text(payload, "assumption_hash"),
        market_snapshot_hash=_text(payload, "market_snapshot_hash"),
        market_lineage_hash=_text(payload, "market_lineage_hash"),
    )


def _reconciliation(payload: dict[str, object]) -> PaperReconciliation:
    return PaperReconciliation(
        reconciliation_id=_text(payload, "reconciliation_id"),
        session_id=_text(payload, "session_id"),
        trade_date=_text(payload, "trade_date"),
        order_count=_integer(payload, "order_count"),
        fill_count=_integer(payload, "fill_count"),
        ledger_fill_count=_integer(payload, "ledger_fill_count"),
        balanced=bool(payload["balanced"]),
        checksum=_text(payload, "checksum"),
        reconciled_at=datetime.fromisoformat(_text(payload, "reconciled_at")),
    )
