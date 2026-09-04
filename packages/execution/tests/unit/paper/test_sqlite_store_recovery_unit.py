"""Durability, CAS, and tamper-detection tests for paper session storage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import orjson
import pytest
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
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
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import MarketSnapshot
from ditto_platform.foundation import SQLiteClient

_NOW = datetime(2026, 9, 4, 7, 0, tzinfo=UTC)
_INSTRUMENT = InstrumentId(600519)


def _session(
    *, status: PaperSessionStatus = PaperSessionStatus.CREATED
) -> PaperSession:
    return PaperSession(
        session_id="session-1",
        account_id="account-1",
        strategy_id="strategy-1",
        trade_date="2026-09-04",
        status=status,
        revision=0,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _mutation(
    session: PaperSession,
    *,
    key: str,
    action: str,
) -> PaperSessionMutation:
    return PaperSessionMutation(
        session_id=session.session_id,
        idempotency_key=key,
        action=action,
        request_hash=f"request:{action}",
        resulting_session=session,
    )


def _paper_order() -> PaperOrder:
    order = Order(
        client_id=ClientOrderId(value="paper-order-1"),
        instrument_id=_INSTRUMENT,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=100,
        trade_date="2026-09-04",
    )
    return PaperOrder.create(
        session_id="session-1",
        account_id="account-1",
        idempotency_key="order-request-1",
        order=order,
        submitted_at=_NOW,
    ).submit()


def _lineage() -> MarketSnapshotLineage:
    return MarketSnapshotLineage.create(
        snapshot=MarketSnapshot(
            trade_date="2026-09-04",
            instrument_id=_INSTRUMENT,
            open=9.8,
            high=10.2,
            low=9.7,
            close=10.0,
            prev_close=10.0,
            volume=1_000_000.0,
            amount=10_000_000.0,
        ),
        dataset_id="a-share-daily-bars",
        source="tushare",
        source_snapshot_id="tushare:20260904:600519",
        observed_at=_NOW,
        publication_cutoff=_NOW,
    )


def _execution(
    *,
    execution_id: str = "execution-1",
    key: str = "execution-key-1",
    request_hash: str = "request-hash-1",
) -> PaperExecutionRecord:
    order = _paper_order()
    return PaperExecutionRecord(
        execution_id=execution_id,
        session_id="session-1",
        account_id="account-1",
        idempotency_key=key,
        request_hash=request_hash,
        result=PaperRealityResult(
            status=PaperRealityStatus.DEFERRED,
            order=order,
            reason="awaiting_market",
        ),
        assumption=FillAssumption(
            assumption_id="paper-v1",
            version=1,
            reference_price_field="close",
            slippage_bps=0.0,
        ),
        lineage=_lineage(),
        created_at=_NOW,
    )


def _reconciliation(*, checksum: str = "checksum-1") -> PaperReconciliation:
    return PaperReconciliation(
        reconciliation_id="reconciliation-1",
        session_id="session-1",
        trade_date="2026-09-04",
        order_count=1,
        fill_count=0,
        ledger_fill_count=0,
        balanced=True,
        checksum=checksum,
        reconciled_at=_NOW,
    )


def _execution_payload(client: SQLiteClient) -> dict[str, object]:
    row = client.conn.execute(
        "SELECT payload_json FROM paper_executions WHERE execution_id = ?",
        ("execution-1",),
    ).fetchone()
    assert row is not None
    return cast(dict[str, object], orjson.loads(cast(str, row["payload_json"])))


def _store_execution_payload(
    client: SQLiteClient,
    payload: dict[str, object] | list[object],
) -> None:
    client.conn.execute(
        "UPDATE paper_executions SET payload_json = ? WHERE execution_id = ?",
        (orjson.dumps(payload).decode(), "execution-1"),
    )
    client.conn.commit()


def test_sqlite_session_identity_and_revision_are_guarded_atomically(
    sqlite_client: SQLiteClient,
) -> None:
    store = SqlitePaperSessionStore(sqlite_client)
    session = _session()
    create = _mutation(session, key="create-1", action="create")

    assert store.get_session(session.session_id) is None
    assert store.get_mutation(session.session_id, "missing") is None
    assert store.create_session(session, create) == session
    assert store.create_session(session) == session
    assert store.get_mutation(session.session_id, create.idempotency_key) == create

    with pytest.raises(PaperSessionConflictError, match="identity conflict"):
        store.create_session(replace(session, strategy_id="other-strategy"))

    running = session.start(updated_at=_NOW)
    with pytest.raises(PaperSessionConflictError, match="revision conflict"):
        store.update_session(
            running,
            expected_revision=99,
            mutation=_mutation(running, key="start-1", action="start"),
        )
    assert store.get_session(session.session_id) == session

    start = _mutation(running, key="start-1", action="start")
    assert store.update_session(running, expected_revision=0, mutation=start) == running
    assert store.get_session(session.session_id) == running

    with pytest.raises(PaperSessionConflictError, match="idempotency conflict"):
        store.update_session(
            replace(running, revision=2),
            expected_revision=running.revision,
            mutation=_mutation(running, key="create-1", action="start"),
        )
    assert store.get_session(session.session_id) == running


def test_sqlite_execution_replay_and_ledger_link_are_exact(
    sqlite_client: SQLiteClient,
) -> None:
    store = SqlitePaperSessionStore(sqlite_client)
    store.create_session(_session())
    record = _execution()

    assert store.get_execution("session-1", "missing") is None
    assert store.append_execution(record) == record
    assert store.append_execution(record) == record
    assert store.list_executions("session-1") == (record,)

    with pytest.raises(PaperSessionConflictError, match="idempotency conflict"):
        store.append_execution(replace(record, request_hash="different"))
    with pytest.raises(PaperSessionConflictError, match="identity or idempotency"):
        store.append_execution(
            _execution(
                execution_id=record.execution_id,
                key="execution-key-2",
                request_hash="request-hash-2",
            )
        )
    with pytest.raises(PaperSessionConflictError, match="not found"):
        store.mark_execution_ledgered("missing", "ledger-event-1")

    linked = store.mark_execution_ledgered(record.execution_id, "ledger-event-1")
    assert linked.ledger_event_id == "ledger-event-1"
    assert (
        store.mark_execution_ledgered(record.execution_id, "ledger-event-1") == linked
    )
    with pytest.raises(PaperSessionConflictError, match="ledger event conflict"):
        store.mark_execution_ledgered(record.execution_id, "ledger-event-2")


def test_sqlite_reconciliation_is_append_only_and_recovers_latest(
    sqlite_client: SQLiteClient,
) -> None:
    store = SqlitePaperSessionStore(sqlite_client)
    store.create_session(_session())
    reconciliation = _reconciliation()

    assert store.latest_reconciliation("session-1") is None
    assert store.get_reconciliation("missing") is None
    assert store.append_reconciliation(reconciliation) == reconciliation
    assert store.append_reconciliation(reconciliation) == reconciliation
    assert store.get_reconciliation(reconciliation.reconciliation_id) == reconciliation
    assert store.latest_reconciliation("session-1") == reconciliation

    with pytest.raises(PaperSessionConflictError, match="identity conflict"):
        store.append_reconciliation(_reconciliation(checksum="different"))
    with pytest.raises(PaperSessionConflictError, match="identity conflict"):
        store.append_reconciliation(
            replace(
                reconciliation,
                reconciliation_id="missing-session",
                session_id="missing",
            )
        )


def test_sqlite_recovery_rejects_malformed_payload_shapes(
    sqlite_client: SQLiteClient,
) -> None:
    store = SqlitePaperSessionStore(sqlite_client)
    store.create_session(_session())
    record = _execution()
    store.append_execution(record)
    valid = _execution_payload(sqlite_client)

    _store_execution_payload(sqlite_client, [])
    with pytest.raises(PaperSessionConflictError, match="must be an object"):
        store.get_execution("session-1", record.idempotency_key)

    malformed = dict(valid)
    malformed["execution_id"] = 1
    _store_execution_payload(sqlite_client, malformed)
    with pytest.raises(PaperSessionConflictError, match="must be text"):
        store.get_execution("session-1", record.idempotency_key)

    malformed = dict(valid)
    malformed["result"] = "not-an-object"
    _store_execution_payload(sqlite_client, malformed)
    with pytest.raises(PaperSessionConflictError, match="must be object"):
        store.get_execution("session-1", record.idempotency_key)

    malformed = dict(valid)
    malformed["ledger_event_id"] = 1
    _store_execution_payload(sqlite_client, malformed)
    with pytest.raises(PaperSessionConflictError, match="must be text"):
        store.get_execution("session-1", record.idempotency_key)

    malformed = orjson.loads(orjson.dumps(valid))
    assert isinstance(malformed, dict)
    assumption = malformed["assumption"]
    assert isinstance(assumption, dict)
    assumption["slippage_bps"] = True
    _store_execution_payload(sqlite_client, cast(dict[str, object], malformed))
    with pytest.raises(PaperSessionConflictError, match="must be numeric"):
        store.get_execution("session-1", record.idempotency_key)


def test_sqlite_recovery_rejects_tampered_lineage_and_order_payloads(
    sqlite_client: SQLiteClient,
) -> None:
    store = SqlitePaperSessionStore(sqlite_client)
    store.create_session(_session())
    record = _execution()
    store.append_execution(record)
    valid = _execution_payload(sqlite_client)

    malformed = orjson.loads(orjson.dumps(valid))
    assert isinstance(malformed, dict)
    lineage = malformed["lineage"]
    assert isinstance(lineage, dict)
    lineage["snapshot_hash"] = "market-snapshot:sha256:tampered"
    _store_execution_payload(sqlite_client, cast(dict[str, object], malformed))
    with pytest.raises(PaperSessionConflictError, match="lineage hash mismatch"):
        store.get_execution("session-1", record.idempotency_key)

    malformed = orjson.loads(orjson.dumps(valid))
    result = malformed["result"]
    assert isinstance(result, dict)
    order = result["order"]
    assert isinstance(order, dict)
    ticket = order["ticket"]
    assert isinstance(ticket, dict)
    ticket["order_events"] = "not-a-list"
    _store_execution_payload(sqlite_client, cast(dict[str, object], malformed))
    with pytest.raises(PaperSessionConflictError, match="must be a list"):
        store.get_execution("session-1", record.idempotency_key)

    malformed = orjson.loads(orjson.dumps(valid))
    result = malformed["result"]
    assert isinstance(result, dict)
    order = result["order"]
    assert isinstance(order, dict)
    ticket = order["ticket"]
    assert isinstance(ticket, dict)
    order_payload = ticket["order"]
    assert isinstance(order_payload, dict)
    order_payload["price"] = True
    _store_execution_payload(sqlite_client, cast(dict[str, object], malformed))
    with pytest.raises(PaperSessionConflictError, match="must be numeric"):
        store.get_execution("session-1", record.idempotency_key)


def test_owned_store_fails_closed_after_close() -> None:
    store = SqlitePaperSessionStore(":memory:")
    store.close()
    with pytest.raises(PaperSessionConflictError, match="closed"):
        store.get_session("session-1")
