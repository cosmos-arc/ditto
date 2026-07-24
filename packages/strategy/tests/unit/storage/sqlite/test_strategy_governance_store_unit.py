"""Unit tests for the append-only strategy governance SQLite store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ditto_platform.foundation import SQLitePool
from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    ReviewOutcome,
    StrategyActivationEvent,
    StrategyDecision,
    StrategyDecisionEvent,
    StrategyVersion,
    StrategyVersionState,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
    StrategyGovernanceCasConflict,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)


def _store(tmp_path: Path) -> SQLiteStrategyGovernanceStore:
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    return store


def _version(
    *,
    strategy_id: str = "strategy-1",
    version: int = 1,
    spec_hash: str = "a" * 64,
) -> StrategyVersion:
    return StrategyVersion(
        strategy_id=strategy_id,
        version=version,
        parent_version=None,
        schema_version=GOVERNANCE_SCHEMA_VERSION,
        spec_hash=spec_hash,
        created_at="2026-07-23T00:00:00Z",
    )


def _decision(
    *,
    event_id: str = "event-1",
    decision: StrategyDecision = StrategyDecision.SUBMIT_REVIEW,
    version: int = 1,
) -> StrategyDecisionEvent:
    return StrategyDecisionEvent(
        event_id=event_id,
        strategy_id="strategy-1",
        version=version,
        decision=decision,
        actor="reviewer-1",
        reason="initial review",
        decided_at="2026-07-23T00:00:01Z",
    )


def _activation(
    *,
    event_id: str = "activation-1",
    kind: StrategyDecision = StrategyDecision.PUBLISH,
    target_version: int = 1,
) -> StrategyActivationEvent:
    return StrategyActivationEvent(
        event_id=event_id,
        strategy_id="strategy-1",
        target_version=target_version,
        activation_kind=kind,
        actor="publisher-1",
        reason="go live",
        activated_at="2026-07-23T00:00:02Z",
    )


def test_insert_version_persists_immutable_payload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version(spec_hash="b" * 64))

    fetched = store.get_version("strategy-1", 1)
    assert fetched is not None
    assert fetched.spec_hash == "b" * 64


def test_insert_version_rejects_duplicate_primary_key(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())

    with pytest.raises(sqlite3.IntegrityError):
        store.insert_version(_version())


def test_initial_state_is_draft_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())

    state = store.get_state("strategy-1", 1)
    assert state is not None
    assert state.state is StrategyVersionState.DRAFT
    assert state.review_outcome is ReviewOutcome.PENDING
    assert state.state_revision == 0


def test_append_decision_advances_state_with_cas(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())

    record = store.append_decision(
        _decision(),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )

    assert record.state is StrategyVersionState.REVIEW
    assert record.state_revision == 1


def test_append_decision_rejects_stale_state_revision(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())

    with pytest.raises(StrategyGovernanceCasConflict):
        store.append_decision(
            _decision(),
            StrategyVersionState.REVIEW,
            ReviewOutcome.PENDING,
            expected_revision=99,
        )


def test_append_decision_rolls_back_event_on_cas_conflict(tmp_path: Path) -> None:
    """A conflicted decision must not leave a dangling event behind."""

    store = _store(tmp_path)
    store.insert_version(_version())

    with pytest.raises(StrategyGovernanceCasConflict):
        store.append_decision(
            _decision(event_id="event-conflict"),
            StrategyVersionState.REVIEW,
            ReviewOutcome.PENDING,
            expected_revision=99,
        )
    # retry with the right revision must still succeed using the same event_id
    record = store.append_decision(
        _decision(event_id="event-conflict"),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )
    assert record.state_revision == 1


def test_activate_inserts_first_pointer(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())

    pointer = store.activate(
        "strategy-1", 1, _activation(), expected_pointer_revision=0
    )

    assert pointer.active_version == 1
    assert pointer.pointer_revision == 1


def test_activate_swaps_pointer_with_cas(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    store.activate("strategy-1", 1, _activation(), expected_pointer_revision=0)

    pointer = store.activate(
        "strategy-1",
        1,
        _activation(event_id="activation-2", kind=StrategyDecision.REACTIVATE),
        expected_pointer_revision=1,
    )

    assert pointer.pointer_revision == 2
    assert pointer.activation_event_id == "activation-2"


def test_activate_rejects_stale_pointer_revision(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    store.activate("strategy-1", 1, _activation(), expected_pointer_revision=0)

    with pytest.raises(StrategyGovernanceCasConflict):
        store.activate(
            "strategy-1",
            1,
            _activation(event_id="activation-2"),
            expected_pointer_revision=99,
        )


def test_first_activation_conflicts_when_pointer_already_exists(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    store.activate("strategy-1", 1, _activation(), expected_pointer_revision=0)

    with pytest.raises(StrategyGovernanceCasConflict):
        store.activate(
            "strategy-1",
            1,
            _activation(event_id="activation-2"),
            expected_pointer_revision=0,
        )


def test_list_versions_returns_newest_first(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version(version=1))
    store.insert_version(_version(version=2, spec_hash="c" * 64))

    versions = store.list_versions("strategy-1")
    assert [item.version for item in versions] == [2, 1]


def test_create_draft_version_writes_payload_and_governance_atomically(
    tmp_path: Path,
) -> None:
    """create_draft_version persists spec payload + governance version in one tx."""
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()

    spec_record = StrategySpecRecord(
        strategy_id="strategy-1",
        name="Test",
        spec_json={"version": 1},
        spec_hash="d" * 64,
        version=1,
    )
    version = _version(spec_hash="d" * 64)
    store.create_draft_version(spec_record, version)

    fetched = store.get_version("strategy-1", 1)
    assert fetched is not None
    assert fetched.spec_hash == "d" * 64
    state = store.get_state("strategy-1", 1)
    assert state is not None
    assert state.state is StrategyVersionState.DRAFT

    payload = SQLiteStrategySpecReader(pool).get_spec("strategy-1", 1)
    assert payload is not None
    assert payload.spec_hash == "d" * 64
    assert payload.spec_json == {"version": 1}


def test_create_draft_version_rejects_duplicate_primary_key(
    tmp_path: Path,
) -> None:
    """create_draft_version rejects duplicate (strategy_id, version) atomically."""
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()

    spec_record = StrategySpecRecord(
        strategy_id="strategy-1",
        name="Test",
        spec_json={"version": 1},
        spec_hash="d" * 64,
        version=1,
    )
    version = _version(spec_hash="d" * 64)
    store.create_draft_version(spec_record, version)

    with pytest.raises(sqlite3.IntegrityError):
        store.create_draft_version(spec_record, version)
