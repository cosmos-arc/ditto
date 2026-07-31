"""Unit tests for the append-only strategy governance SQLite store."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest
from ditto_platform.foundation import SQLitePool
from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    ReviewOutcome,
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecision,
    StrategyDecisionEvent,
    StrategyVersion,
    StrategyVersionState,
    StrategyVersionStateRecord,
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
    created_at: str = "2026-07-23T00:00:00Z",
) -> StrategyVersion:
    return StrategyVersion(
        strategy_id=strategy_id,
        version=version,
        parent_version=None,
        schema_version=GOVERNANCE_SCHEMA_VERSION,
        spec_hash=spec_hash,
        created_at=created_at,
    )


def _decision(
    *,
    event_id: str = "event-1",
    decision: StrategyDecision = StrategyDecision.SUBMIT_REVIEW,
    version: int = 1,
    strategy_id: str = "strategy-1",
) -> StrategyDecisionEvent:
    return StrategyDecisionEvent(
        event_id=event_id,
        strategy_id=strategy_id,
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


def _advance_to_approved(
    store: SQLiteStrategyGovernanceStore,
    *,
    version: int,
) -> None:
    store.append_decision(
        _decision(
            event_id=f"strategy-1:{version}:submit",
            decision=StrategyDecision.SUBMIT_REVIEW,
            version=version,
        ),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )
    store.append_decision(
        _decision(
            event_id=f"strategy-1:{version}:approve",
            decision=StrategyDecision.APPROVE,
            version=version,
        ),
        StrategyVersionState.REVIEW,
        ReviewOutcome.APPROVED,
        expected_revision=1,
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


def test_append_decision_returns_exact_state_selected_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    durable_get_state = store.get_state
    later_state = StrategyVersionStateRecord(
        strategy_id="strategy-1",
        version=1,
        state=StrategyVersionState.REVIEW,
        review_outcome=ReviewOutcome.APPROVED,
        state_revision=2,
    )
    monkeypatch.setattr(store, "get_state", lambda *_args: later_state)

    first = store.append_decision(
        _decision(),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )

    persisted = durable_get_state("strategy-1", 1)
    assert persisted is not None
    assert persisted.state_revision == 1
    assert first == persisted


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


def test_activate_returns_exact_pointer_selected_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    store.activate("strategy-1", 1, _activation(), expected_pointer_revision=0)
    durable_get_pointer = store.get_active_pointer
    later_pointer = StrategyActivePointer(
        strategy_id="strategy-1",
        active_version=1,
        pointer_revision=3,
        activation_event_id="activation-3",
    )
    monkeypatch.setattr(store, "get_active_pointer", lambda *_args: later_pointer)

    first = store.activate(
        "strategy-1",
        1,
        _activation(event_id="activation-2", kind=StrategyDecision.REACTIVATE),
        expected_pointer_revision=1,
    )

    persisted = durable_get_pointer("strategy-1")
    assert persisted is not None
    assert persisted.pointer_revision == 2
    assert first == persisted


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


def test_publish_reviewed_and_activate_commits_one_atomic_transition(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    _advance_to_approved(store, version=1)

    pointer = store.publish_reviewed_and_activate(
        _decision(
            event_id="publish-1",
            decision=StrategyDecision.PUBLISH,
        ),
        _activation(event_id="activation-1"),
        expected_state_revision=2,
        expected_pointer_revision=0,
    )

    state = store.get_state("strategy-1", 1)
    assert state is not None
    assert state.state is StrategyVersionState.PUBLISHED
    assert state.review_outcome is ReviewOutcome.APPROVED
    assert pointer.active_version == 1
    assert pointer.activation_event_id == "activation-1"


def test_publish_reviewed_and_activate_returns_pointer_from_its_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    _advance_to_approved(store, version=1)

    def fail_post_commit_read(_strategy_id: str) -> None:
        raise AssertionError("atomic promotion must not re-read after commit")

    monkeypatch.setattr(store, "get_active_pointer", fail_post_commit_read)

    pointer = store.publish_reviewed_and_activate(
        _decision(
            event_id="publish-1",
            decision=StrategyDecision.PUBLISH,
        ),
        _activation(event_id="activation-1"),
        expected_state_revision=2,
        expected_pointer_revision=0,
    )

    assert pointer.active_version == 1
    assert pointer.pointer_revision == 1
    assert pointer.activation_event_id == "activation-1"


def test_publish_reviewed_and_activate_rolls_back_every_write_on_pointer_conflict(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version(version=1))
    store.activate("strategy-1", 1, _activation(), expected_pointer_revision=0)
    store.insert_version(_version(version=2, spec_hash="b" * 64))
    _advance_to_approved(store, version=2)
    publish = _decision(
        event_id="publish-2",
        decision=StrategyDecision.PUBLISH,
        version=2,
    )
    activation = _activation(event_id="activation-2", target_version=2)

    with pytest.raises(StrategyGovernanceCasConflict):
        store.publish_reviewed_and_activate(
            publish,
            activation,
            expected_state_revision=2,
            expected_pointer_revision=0,
        )

    state = store.get_state("strategy-1", 2)
    pointer = store.get_active_pointer("strategy-1")
    assert state is not None
    assert state.state is StrategyVersionState.REVIEW
    assert state.review_outcome is ReviewOutcome.APPROVED
    assert state.state_revision == 2
    assert pointer is not None
    assert pointer.active_version == 1

    # Reusing both event ids proves the failed transaction left no history row.
    recovered = store.publish_reviewed_and_activate(
        publish,
        activation,
        expected_state_revision=2,
        expected_pointer_revision=pointer.pointer_revision,
    )
    assert recovered.active_version == 2


def test_list_versions_returns_newest_first(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version(version=1))
    store.insert_version(_version(version=2, spec_hash="c" * 64))

    versions = store.list_versions("strategy-1")
    assert [item.version for item in versions] == [2, 1]


def test_list_versions_by_state_filters_across_strategies_newest_first(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(
        _version(
            strategy_id="alpha",
            version=1,
            spec_hash="a" * 64,
            created_at="2026-07-23T00:00:00Z",
        )
    )
    store.append_decision(
        _decision(
            strategy_id="alpha",
            event_id="alpha:1:submit",
            decision=StrategyDecision.SUBMIT_REVIEW,
            version=1,
        ),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )
    store.insert_version(
        _version(
            strategy_id="beta",
            version=1,
            spec_hash="b" * 64,
            created_at="2026-07-24T00:00:00Z",
        )
    )
    store.append_decision(
        _decision(
            strategy_id="beta",
            event_id="beta:1:submit",
            decision=StrategyDecision.SUBMIT_REVIEW,
            version=1,
        ),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )
    store.insert_version(_version(strategy_id="gamma", version=1, spec_hash="c" * 64))

    reviews = store.list_versions_by_state(StrategyVersionState.REVIEW)
    assert [(v.strategy_id, v.version) for v in reviews] == [
        ("beta", 1),
        ("alpha", 1),
    ]


def test_list_versions_by_state_returns_empty_when_no_match(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_version(_version(strategy_id="solo", version=1, spec_hash="a" * 64))

    reviews = store.list_versions_by_state(StrategyVersionState.REVIEW)
    assert reviews == ()


def test_list_governance_events_merges_append_only_streams_with_stable_cursor(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())
    store.append_decision(
        StrategyDecisionEvent(
            event_id="decision-b",
            strategy_id="strategy-1",
            version=1,
            decision=StrategyDecision.SUBMIT_REVIEW,
            actor="alice",
            reason="review",
            decided_at="2026-07-23T00:00:01Z",
        ),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )
    store.activate(
        "strategy-1",
        1,
        StrategyActivationEvent(
            event_id="activation-a",
            strategy_id="strategy-1",
            target_version=1,
            activation_kind=StrategyDecision.REACTIVATE,
            actor="bob",
            reason="switch",
            activated_at="2026-07-23T00:00:01Z",
        ),
        expected_pointer_revision=0,
    )

    events = store.list_governance_events("strategy-1", after_event_id=None, limit=20)

    assert [item.event_id for item in events] == ["activation-a", "decision-b"]
    assert asdict(events[0]) == {
        "event_id": "activation-a",
        "strategy_id": "strategy-1",
        "event_type": "activation",
        "target_version": 1,
        "decision_or_activation_kind": "reactivate",
        "actor": "bob",
        "reason": "switch",
        "occurred_at": "2026-07-23T00:00:01Z",
    }
    forbidden = {
        "bundle_hash",
        "evidence_hash",
        "previous_version",
        "pointer_revision",
    }
    assert forbidden.isdisjoint(asdict(events[0]))
    assert store.list_governance_events(
        "strategy-1", after_event_id="activation-a", limit=1
    ) == (events[1],)


def test_list_governance_events_rejects_missing_or_cross_strategy_cursor(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version(strategy_id="strategy-1"))
    store.insert_version(_version(strategy_id="strategy-2", spec_hash="b" * 64))
    store.append_decision(
        _decision(event_id="strategy-2:event", strategy_id="strategy-2"),
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        expected_revision=0,
    )

    for cursor in ("missing", "strategy-2:event"):
        with pytest.raises(ValueError, match="INVALID_EVENT_CURSOR"):
            store.list_governance_events("strategy-1", after_event_id=cursor, limit=20)


def test_list_governance_events_distinguishes_missing_strategy(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    with pytest.raises(LookupError, match="STRATEGY_NOT_FOUND"):
        store.list_governance_events("missing", after_event_id=None, limit=20)


def test_list_governance_events_returns_empty_for_existing_strategy_without_events(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.insert_version(_version())

    assert (
        store.list_governance_events("strategy-1", after_event_id=None, limit=20) == ()
    )


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
