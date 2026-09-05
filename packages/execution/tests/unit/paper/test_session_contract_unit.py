"""Lifecycle, idempotency, and recovery contracts for paper sessions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperRealityResult,
)
from ditto_execution.paper.session import (
    InMemoryPaperSessionStore,
    PaperExecutionRecord,
    PaperReconciliation,
    PaperSession,
    PaperSessionConflictError,
    PaperSessionMutation,
    PaperSessionStatus,
)

_NOW = datetime(2026, 9, 4, 9, tzinfo=UTC)


def _session(**changes: object) -> PaperSession:
    values: dict[str, object] = {
        "session_id": "session-1",
        "account_id": "account-1",
        "strategy_id": "strategy-1",
        "trade_date": "2026-09-04",
        "status": PaperSessionStatus.CREATED,
        "revision": 0,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    values.update(changes)
    return PaperSession(
        session_id=cast(str, values["session_id"]),
        account_id=cast(str, values["account_id"]),
        strategy_id=cast(str, values["strategy_id"]),
        trade_date=cast(str, values["trade_date"]),
        status=cast(PaperSessionStatus, values["status"]),
        revision=cast(int, values["revision"]),
        created_at=cast(datetime, values["created_at"]),
        updated_at=cast(datetime, values["updated_at"]),
    )


def _mutation(
    session: PaperSession,
    *,
    key: str = "mutation-1",
    action: str = "create",
) -> PaperSessionMutation:
    return PaperSessionMutation(
        session_id=session.session_id,
        idempotency_key=key,
        action=action,
        request_hash=f"hash:{action}",
        resulting_session=session,
    )


def _execution(
    *,
    execution_id: str = "execution-1",
    session_id: str = "session-1",
    key: str = "execution-key-1",
    request_hash: str = "request-hash-1",
) -> PaperExecutionRecord:
    return PaperExecutionRecord(
        execution_id=execution_id,
        session_id=session_id,
        account_id="account-1",
        idempotency_key=key,
        request_hash=request_hash,
        result=cast(PaperRealityResult, object()),
        assumption=cast(FillAssumption, object()),
        lineage=cast(MarketSnapshotLineage, object()),
        created_at=_NOW,
    )


def _reconciliation(
    *,
    reconciliation_id: str = "reconciliation-1",
    session_id: str = "session-1",
    checksum: str = "checksum-1",
) -> PaperReconciliation:
    return PaperReconciliation(
        reconciliation_id=reconciliation_id,
        session_id=session_id,
        trade_date="2026-09-04",
        order_count=1,
        fill_count=1,
        ledger_fill_count=1,
        balanced=True,
        checksum=checksum,
        reconciled_at=_NOW,
    )


@pytest.mark.parametrize("field", ["session_id", "account_id", "strategy_id"])
def test_session_identity_fields_are_non_empty(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        _session(**{field: " "})


def test_session_revision_and_timestamps_fail_closed() -> None:
    with pytest.raises(ValueError, match="revision"):
        _session(revision=-1)
    with pytest.raises(ValueError, match="created_at"):
        _session(created_at=_NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="updated_at"):
        _session(updated_at=_NOW.replace(tzinfo=None))


def test_session_lifecycle_allows_only_created_or_paused_to_start() -> None:
    running = _session().start(updated_at=_NOW)
    assert running.status is PaperSessionStatus.RUNNING
    paused = running.pause(updated_at=_NOW, reason="operator pause")
    assert paused.start(updated_at=_NOW).status is PaperSessionStatus.RUNNING

    with pytest.raises(PaperSessionConflictError, match="created or paused"):
        running.start(updated_at=_NOW)
    with pytest.raises(ValueError, match="reason"):
        running.pause(updated_at=_NOW, reason=" ")
    with pytest.raises(PaperSessionConflictError, match="running"):
        _session().pause(updated_at=_NOW, reason="operator pause")


def test_execution_ledger_identity_is_idempotent_but_not_replaceable() -> None:
    record = _execution()
    ledgered = record.with_ledger_event("event-1")
    assert ledgered.with_ledger_event("event-1") == ledgered
    with pytest.raises(PaperSessionConflictError, match="ledger event conflict"):
        ledgered.with_ledger_event("event-2")


def test_session_store_enforces_identity_revision_and_mutation_idempotency() -> None:
    store = InMemoryPaperSessionStore()
    created = _session()
    create_mutation = _mutation(created)
    assert store.create_session(created, create_mutation) == created
    assert store.create_session(created) == created
    assert store.get_mutation(created.session_id, "mutation-1") == create_mutation

    with pytest.raises(PaperSessionConflictError, match="identity conflict"):
        store.create_session(replace(created, strategy_id="other"))
    with pytest.raises(PaperSessionConflictError, match="not found"):
        store.update_session(
            _session(session_id="missing", revision=1),
            expected_revision=0,
            mutation=_mutation(created, key="missing"),
        )
    with pytest.raises(PaperSessionConflictError, match="revision conflict"):
        store.update_session(
            created.start(updated_at=_NOW),
            expected_revision=9,
            mutation=_mutation(created, key="start"),
        )
    with pytest.raises(PaperSessionConflictError, match="idempotency conflict"):
        store.update_session(
            created.start(updated_at=_NOW),
            expected_revision=0,
            mutation=_mutation(created, action="different"),
        )

    started = created.start(updated_at=_NOW)
    start_mutation = _mutation(started, key="start", action="start")
    assert (
        store.update_session(
            started,
            expected_revision=0,
            mutation=start_mutation,
        )
        == started
    )


def test_execution_store_replays_exact_request_and_rejects_identity_conflicts() -> None:
    store = InMemoryPaperSessionStore()
    record = _execution()
    assert store.append_execution(record) == record
    assert store.append_execution(record) == record
    assert store.get_execution("session-1", "execution-key-1") == record
    assert store.get_execution("session-1", "missing") is None

    with pytest.raises(PaperSessionConflictError, match="idempotency conflict"):
        store.append_execution(replace(record, request_hash="different"))
    with pytest.raises(PaperSessionConflictError, match="identity conflict"):
        store.append_execution(
            _execution(key="execution-key-2", request_hash="request-hash-2")
        )

    other = _execution(
        execution_id="execution-2",
        session_id="session-2",
        key="execution-key-2",
        request_hash="request-hash-2",
    )
    store.append_execution(other)
    assert store.list_executions("session-1") == (record,)
    with pytest.raises(PaperSessionConflictError, match="not found"):
        store.mark_execution_ledgered("missing", "event-1")
    assert store.mark_execution_ledgered("execution-1", "event-1").ledger_event_id == (
        "event-1"
    )


def test_reconciliation_store_is_append_only_and_queryable() -> None:
    store = InMemoryPaperSessionStore()
    first = _reconciliation()
    assert store.latest_reconciliation("session-1") is None
    assert store.get_reconciliation("missing") is None
    assert store.append_reconciliation(first) == first
    assert store.append_reconciliation(first) == first
    assert store.get_reconciliation(first.reconciliation_id) == first
    assert store.latest_reconciliation("session-1") == first

    with pytest.raises(PaperSessionConflictError, match="identity conflict"):
        store.append_reconciliation(replace(first, checksum="different"))

    second = _reconciliation(
        reconciliation_id="reconciliation-2",
        checksum="checksum-2",
    )
    store.append_reconciliation(second)
    assert store.latest_reconciliation("session-1") == second
