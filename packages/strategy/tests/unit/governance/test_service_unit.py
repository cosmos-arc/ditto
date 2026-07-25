"""Unit tests for the governance service orchestration over a real store."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_platform.foundation import SQLitePool
from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    ReviewOutcome,
    StrategyActivationEvent,
    StrategyDecision,
    StrategyVersion,
    StrategyVersionState,
)
from ditto_strategy.governance.service import (
    GovernanceService,
    StrategyGovernanceError,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
    StrategyGovernanceCasConflict,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import SQLiteStrategySpecWriter


def _service(tmp_path: Path) -> GovernanceService:
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    return GovernanceService(store)


def _seed_version(service: GovernanceService, version: int = 1) -> None:
    service._store.insert_version(
        StrategyVersion(
            strategy_id="strategy-1",
            version=version,
            parent_version=None,
            schema_version=GOVERNANCE_SCHEMA_VERSION,
            spec_hash="a" * 64,
            created_at="2026-07-23T00:00:00Z",
        )
    )


def test_submit_review_moves_draft_to_review(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _seed_version(service)

    record = service.submit_review(
        "strategy-1", 1, event_id="e1", actor="r", reason="ok", decided_at="t1"
    )

    assert record.state is StrategyVersionState.REVIEW
    assert record.review_outcome is ReviewOutcome.PENDING


def test_approve_then_publish(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _seed_version(service)
    service.submit_review(
        "strategy-1", 1, event_id="e1", actor="r", reason="ok", decided_at="t1"
    )
    service.approve(
        "strategy-1", 1, event_id="e2", actor="r", reason="ok", decided_at="t2"
    )

    published = service.publish(
        "strategy-1", 1, event_id="e3", actor="r", reason="go", decided_at="t3"
    )

    assert published.state is StrategyVersionState.PUBLISHED


def test_rejected_review_cannot_be_published(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _seed_version(service)
    service.submit_review(
        "strategy-1", 1, event_id="e1", actor="r", reason="ok", decided_at="t1"
    )
    service.reject(
        "strategy-1", 1, event_id="e2", actor="r", reason="no", decided_at="t2"
    )

    with pytest.raises(ValueError):
        service.publish(
            "strategy-1", 1, event_id="e3", actor="r", reason="go", decided_at="t3"
        )


def test_activate_switches_active_pointer(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _seed_version(service)
    service.submit_review(
        "strategy-1", 1, event_id="e1", actor="r", reason="ok", decided_at="t1"
    )
    service.approve(
        "strategy-1", 1, event_id="e2", actor="r", reason="ok", decided_at="t2"
    )
    service.publish(
        "strategy-1", 1, event_id="e3", actor="r", reason="go", decided_at="t3"
    )

    pointer = service.activate(
        "strategy-1", 1, _activation_event(kind=StrategyDecision.PUBLISH)
    )

    assert pointer.active_version == 1


def test_deprecated_version_cannot_be_activated(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _seed_version(service)
    service.submit_review(
        "strategy-1", 1, event_id="e1", actor="r", reason="ok", decided_at="t1"
    )
    service.approve(
        "strategy-1", 1, event_id="e2", actor="r", reason="ok", decided_at="t2"
    )
    service.publish(
        "strategy-1", 1, event_id="e3", actor="r", reason="go", decided_at="t3"
    )
    service.deprecate(
        "strategy-1", 1, event_id="e4", actor="r", reason="retire", decided_at="t4"
    )

    with pytest.raises(ValueError):
        service.activate(
            "strategy-1", 1, _activation_event(reason="revive", decided_at="t5")
        )


def test_unknown_version_raises(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(StrategyGovernanceError):
        service.submit_review(
            "strategy-missing",
            1,
            event_id="e1",
            actor="r",
            reason="ok",
            decided_at="t1",
        )


def test_create_draft_persists_payload_and_draft_version(tmp_path: Path) -> None:
    """create_draft writes spec payload + draft governance version atomically."""
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    service = GovernanceService(store)

    spec_record = StrategySpecRecord(
        strategy_id="strategy-1",
        name="Test",
        spec_json={"version": 1},
        spec_hash="e" * 64,
        version=1,
    )
    service.create_draft(
        strategy_id="strategy-1",
        version=1,
        spec_record=spec_record,
        created_at="2026-07-24T00:00:00Z",
    )

    state = store.get_state("strategy-1", 1)
    assert state is not None
    assert state.state is StrategyVersionState.DRAFT
    version = store.get_version("strategy-1", 1)
    assert version is not None
    assert version.spec_hash == "e" * 64


def test_publish_and_activate_advances_draft_to_active(tmp_path: Path) -> None:
    """publish_and_activate walks draft→published→active (seed fast-path)."""
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    service = GovernanceService(store)

    spec_record = StrategySpecRecord(
        strategy_id="strategy-1",
        name="Test",
        spec_json={"version": 1},
        spec_hash="f" * 64,
        version=1,
    )
    service.create_draft(
        strategy_id="strategy-1",
        version=1,
        spec_record=spec_record,
        created_at="2026-07-24T00:00:00Z",
    )

    pointer = service.publish_and_activate(
        strategy_id="strategy-1",
        version=1,
        actor="seed",
        reason="bootstrap",
        decided_at="2026-07-24T00:00:01Z",
    )

    assert pointer.active_version == 1
    state = store.get_state("strategy-1", 1)
    assert state is not None
    assert state.state is StrategyVersionState.PUBLISHED


def test_publish_and_activate_is_idempotent(tmp_path: Path) -> None:
    """Repeated publish_and_activate on an active version is a no-op."""
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    service = GovernanceService(store)

    spec_record = StrategySpecRecord(
        strategy_id="strategy-1",
        name="Test",
        spec_json={"version": 1},
        spec_hash="f" * 64,
        version=1,
    )
    service.create_draft(
        strategy_id="strategy-1",
        version=1,
        spec_record=spec_record,
        created_at="2026-07-24T00:00:00Z",
    )
    first = service.publish_and_activate(
        strategy_id="strategy-1",
        version=1,
        actor="seed",
        reason="bootstrap",
        decided_at="2026-07-24T00:00:01Z",
    )
    second = service.publish_and_activate(
        strategy_id="strategy-1",
        version=1,
        actor="seed",
        reason="bootstrap",
        decided_at="2026-07-24T00:00:02Z",
    )

    assert second.active_version == first.active_version


def _advance_to_published(service: GovernanceService, *, version: int = 1) -> None:
    """Walk one seeded version through submit→approve→publish."""
    prefix = f"strategy-1:{version}"
    service.submit_review(
        "strategy-1",
        version,
        event_id=f"{prefix}:submit",
        actor="r",
        reason="ok",
        decided_at="t1",
    )
    service.approve(
        "strategy-1",
        version,
        event_id=f"{prefix}:approve",
        actor="r",
        reason="ok",
        decided_at="t2",
    )
    service.publish(
        "strategy-1",
        version,
        event_id=f"{prefix}:publish",
        actor="r",
        reason="go",
        decided_at="t3",
    )


def _activation_event(
    event_id: str = "a1",
    *,
    kind: StrategyDecision = StrategyDecision.REACTIVATE,
    reason: str = "go live",
    decided_at: str = "t4",
) -> StrategyActivationEvent:
    """Build one activation event for the seeded strategy-1/version-1 target."""
    return StrategyActivationEvent(
        event_id, "strategy-1", 1, kind, "r", reason, decided_at
    )


def test_activate_with_expected_pointer_revision_match(tmp_path: Path) -> None:
    """activate accepts a client-supplied expected_pointer_revision that matches."""
    service = _service(tmp_path)
    _seed_version(service)
    _advance_to_published(service)

    pointer = service.activate(
        "strategy-1", 1, _activation_event(), expected_pointer_revision=0
    )

    assert pointer.active_version == 1
    assert pointer.pointer_revision == 1


def test_activate_with_stale_expected_pointer_revision_conflicts(
    tmp_path: Path,
) -> None:
    """activate with a stale expected_pointer_revision raises a CAS conflict."""
    service = _service(tmp_path)
    _seed_version(service)
    _advance_to_published(service)
    service.activate("strategy-1", 1, _activation_event(), expected_pointer_revision=0)

    with pytest.raises(StrategyGovernanceCasConflict):
        service.activate(
            "strategy-1",
            1,
            _activation_event(event_id="a2", reason="reapply", decided_at="t5"),
            expected_pointer_revision=0,
        )


def test_activate_without_expected_reads_current(tmp_path: Path) -> None:
    """activate without expected_pointer_revision keeps the legacy read-current path."""
    service = _service(tmp_path)
    _seed_version(service)
    _advance_to_published(service)

    pointer = service.activate("strategy-1", 1, _activation_event())

    assert pointer.active_version == 1
