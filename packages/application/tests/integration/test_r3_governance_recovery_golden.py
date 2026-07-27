"""R3 governance recovery integration golden test.

Covers the recovery semantics of the strategy governance state machine across
the SQLiteStrategyGovernanceStore + GovernanceService + command-handler seam:

1. **Append-only review decisions** — ``submit_review`` → ``approve`` →
   ``publish`` records each transition as an immutable
   :class:`StrategyDecisionEvent` row keyed by a unique ``event_id``; the
   rebuildable state projection advances via compare-and-swap revision while
   the event log only ever grows.
2. **Active pointer CAS swap** — ``publish_and_activate`` v1 → v2 bumps
   ``pointer_revision`` (1 → 2) and the catalog resolves v2 as the active
   payload; v1's per-version lifecycle state stays ``PUBLISHED`` (the pointer
   is independent of version lifecycle).
3. **Reactivate respects expected_pointer_revision** — switching the pointer
   back to a still-published v1 with the correct CAS guard succeeds and bumps
   ``pointer_revision`` once more (2 → 3), appending a ``reactivate``
   activation event with ``activation_kind=REACTIVATE``.
4. **Stale pointer conflict** — a stale ``expected_pointer_revision`` surfaces
   as :class:`StrategyGovernanceCasConflict` at the store seam and is mapped by
   :class:`ReactivateStrategyHandler` into a typed
   :class:`AppCommandError` whose ``details.code`` is
   ``STRATEGY_REVISION_CONFLICT`` (the keyword the API error mapper keys off
   for HTTP 409). A deprecated target is mapped as
   ``STRATEGY_INVALID_TRANSITION``.

The fixture inlines the ``_build_services`` wiring from
``test_strategy_governance_active_pointer_integration`` so this golden stays
self-contained for recovery semantics.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

import pytest
from ditto_application.commands.strategy_governance import (
    ReactivateStrategyCommand,
    ReactivateStrategyHandler,
)
from ditto_application.contracts import StrategyActivePointerInfo
from ditto_application.exceptions import AppCommandError
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.governance.models import (
    StrategyActivationEvent,
    StrategyDecision,
)
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
    StrategyGovernanceCasConflict,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)


def _build_services(
    tmp_path: Path,
) -> tuple[
    GovernanceService,
    StrategyCatalogService,
    SQLiteStrategyGovernanceStore,
    SQLitePool,
]:
    """Wire governance + catalog over one shared metadata pool (isolated)."""
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    governance_store = SQLiteStrategyGovernanceStore(pool)
    governance_store.init_schema()
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=SQLiteStrategySpecWriter(pool),
        active_pointer_reader=governance_store,
    )
    return GovernanceService(governance_store), catalog, governance_store, pool


def _make_record(
    strategy_id: str,
    seed: object,
    version: int,
    created_at: str,
) -> StrategySpecRecord:
    """Build a content-addressed StrategySpecRecord for one version."""
    spec_json = asdict(seed)  # type: ignore[arg-type]
    base = StrategySpecRecord(
        strategy_id=strategy_id,
        name=seed.name,  # type: ignore[union-attr]
        spec_json=spec_json,
        version=version,
        parent_version=None if version == 1 else 1,
        created_at=created_at,
        tags=seed.tags,  # type: ignore[union-attr]
    )
    return replace(base, spec_hash=canonical_spec_hash_for_record(base))


def _list_decision_events(
    pool: SQLitePool, strategy_id: str, version: int
) -> list[dict[str, object]]:
    """Read append-only decision events for one version (test-only read)."""
    conn = pool.get_connection()
    rows = conn.execute(
        "SELECT event_id, decision, actor, reason, decided_at "
        "FROM strategy_decision_event "
        "WHERE strategy_id = ? AND version = ? "
        "ORDER BY rowid",
        (strategy_id, version),
    ).fetchall()
    return [dict(row) for row in rows]


def _list_activation_events(
    pool: SQLitePool, strategy_id: str
) -> list[dict[str, object]]:
    """Read append-only activation events in insertion order (test-only read)."""
    conn = pool.get_connection()
    rows = conn.execute(
        "SELECT event_id, target_version, activation_kind, actor, reason, "
        "activated_at FROM strategy_activation_event "
        "WHERE strategy_id = ? ORDER BY rowid",
        (strategy_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _seed_v1_active(
    governance: GovernanceService, strategy_id: str, seed: object
) -> None:
    """Create + publish_and_activate v1 (pointer_revision ends at 1)."""
    v1 = _make_record(strategy_id, seed, 1, "2026-07-24T00:00:00Z")
    governance.create_draft(
        strategy_id=strategy_id,
        version=1,
        spec_record=v1,
        created_at="2026-07-24T00:00:00Z",
    )
    governance.publish_and_activate(
        strategy_id=strategy_id,
        version=1,
        actor="seed",
        reason="bootstrap",
        decided_at="2026-07-24T00:00:01Z",
    )


def _seed_v2_active(
    governance: GovernanceService, strategy_id: str, seed: object
) -> None:
    """Create + publish_and_activate v2 (pointer_revision ends at 2)."""
    v2 = _make_record(strategy_id, seed, 2, "2026-07-24T00:00:02Z")
    governance.create_draft(
        strategy_id=strategy_id,
        version=2,
        spec_record=v2,
        created_at="2026-07-24T00:00:02Z",
    )
    governance.publish_and_activate(
        strategy_id=strategy_id,
        version=2,
        actor="seed",
        reason="rotate",
        decided_at="2026-07-24T00:00:03Z",
    )


# ---------------------------------------------------------------------------
# Goal 1: review decisions are append-only
# ---------------------------------------------------------------------------


def test_review_decisions_are_append_only(tmp_path: Path) -> None:
    """submit_review → approve → publish appends 3 immutable decision rows.

    The projection advances via CAS revision (0 → 1 → 2 → 3); the event log
    only grows (each row keyed by a unique event_id, no UPDATE/DELETE path
    exists in the store). The actor/reason provenance of every decision is
    preserved verbatim.
    """
    governance, _catalog, _store, pool = _build_services(tmp_path)
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    record = _make_record(strategy_id, seed, 1, "2026-07-24T00:00:00Z")
    governance.create_draft(
        strategy_id=strategy_id,
        version=1,
        spec_record=record,
        created_at="2026-07-24T00:00:00Z",
    )

    after_submit = governance.submit_review(
        strategy_id,
        1,
        event_id="s:1:submit_review:01",
        actor="alice",
        reason="submit v1",
        decided_at="2026-07-24T00:00:01Z",
    )
    assert after_submit.state.value == "review"
    assert after_submit.review_outcome.value == "pending"
    assert after_submit.state_revision == 1

    after_approve = governance.approve(
        strategy_id,
        1,
        event_id="s:1:approve:02",
        actor="bob",
        reason="approve v1",
        decided_at="2026-07-24T00:00:02Z",
    )
    assert after_approve.state.value == "review"
    assert after_approve.review_outcome.value == "approved"
    assert after_approve.state_revision == 2

    after_publish = governance.publish(
        strategy_id,
        1,
        event_id="s:1:publish:03",
        actor="carol",
        reason="publish v1",
        decided_at="2026-07-24T00:00:03Z",
    )
    assert after_publish.state.value == "published"
    assert after_publish.review_outcome.value == "approved"
    assert after_publish.state_revision == 3

    events = _list_decision_events(pool, strategy_id, 1)
    assert [e["decision"] for e in events] == [
        "submit_review",
        "approve",
        "publish",
    ]
    assert [e["actor"] for e in events] == ["alice", "bob", "carol"]
    assert [e["reason"] for e in events] == [
        "submit v1",
        "approve v1",
        "publish v1",
    ]
    assert [e["event_id"] for e in events] == [
        "s:1:submit_review:01",
        "s:1:approve:02",
        "s:1:publish:03",
    ]


# ---------------------------------------------------------------------------
# Goal 2: active pointer CAS swap to a new version
# ---------------------------------------------------------------------------


def test_active_pointer_switches_to_new_version(tmp_path: Path) -> None:
    """publish_and_activate v1 → v2 swaps pointer (revision 1 → 2)."""
    governance, catalog, store, _pool = _build_services(tmp_path)
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))

    _seed_v1_active(governance, strategy_id, seed)
    pointer_v1 = store.get_active_pointer(strategy_id)
    assert pointer_v1 is not None
    assert pointer_v1.active_version == 1
    assert pointer_v1.pointer_revision == 1

    _seed_v2_active(governance, strategy_id, seed)
    pointer_v2 = store.get_active_pointer(strategy_id)
    assert pointer_v2 is not None
    assert pointer_v2.active_version == 2
    assert pointer_v2.pointer_revision == 2

    # Catalog resolves v2 as the active payload; v1 still resolvable as
    # published (lifecycle state is per-version, independent of the pointer).
    active = catalog.get_active_published(strategy_id)
    assert active is not None
    assert active.version == 2
    assert active.parent_version == 1
    v1_state = governance._store.get_state(strategy_id, 1)
    assert v1_state is not None
    assert v1_state.state.value == "published"


# ---------------------------------------------------------------------------
# Goal 3: reactivate respects expected_pointer_revision
# ---------------------------------------------------------------------------


def test_reactivate_switches_pointer_back_with_correct_cas(
    tmp_path: Path,
) -> None:
    """reactivate v1 (still PUBLISHED) with correct CAS: pointer v2 → v1."""
    governance, _catalog, store, pool = _build_services(tmp_path)
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))

    _seed_v1_active(governance, strategy_id, seed)
    _seed_v2_active(governance, strategy_id, seed)
    pointer_before = store.get_active_pointer(strategy_id)
    assert pointer_before is not None
    assert pointer_before.pointer_revision == 2

    handler = ReactivateStrategyHandler(governance)
    result = handler.handle(
        ReactivateStrategyCommand(
            strategy_id=strategy_id,
            version=1,
            actor="ops",
            reason="rollback",
            expected_pointer_revision=2,
        )
    )

    assert isinstance(result, StrategyActivePointerInfo)
    assert result.active_version == 1
    assert result.pointer_revision == 3

    # Activation log records the recovery with kind=reactivate; the two prior
    # publish activations remain in place (append-only provenance).
    activations = _list_activation_events(pool, strategy_id)
    assert [a["activation_kind"] for a in activations] == [
        "publish",
        "publish",
        "reactivate",
    ]
    assert activations[-1]["target_version"] == 1
    assert activations[-1]["actor"] == "ops"
    assert activations[-1]["reason"] == "rollback"

    # Pointer now resolves to v1; v1 state stays PUBLISHED (no lifecycle
    # transition — reactivate is a pointer-only operation).
    pointer_after = store.get_active_pointer(strategy_id)
    assert pointer_after is not None
    assert pointer_after.active_version == 1
    v1_state = governance._store.get_state(strategy_id, 1)
    assert v1_state is not None
    assert v1_state.state.value == "published"


# ---------------------------------------------------------------------------
# Goal 4: stale expected_pointer_revision surfaces as a typed conflict
# ---------------------------------------------------------------------------


def test_stale_pointer_revision_raises_conflict_at_store_seam(
    tmp_path: Path,
) -> None:
    """Direct store.activate with stale CAS raises StrategyGovernanceCasConflict."""
    governance, _catalog, store, _pool = _build_services(tmp_path)
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    _seed_v1_active(governance, strategy_id, seed)
    _seed_v2_active(governance, strategy_id, seed)

    stale_event = StrategyActivationEvent(
        "s:1:reactivate:stale",
        strategy_id,
        1,
        StrategyDecision.REACTIVATE,
        "ops",
        "rollback",
        "2026-07-24T00:00:04Z",
    )
    with pytest.raises(StrategyGovernanceCasConflict):
        store.activate(strategy_id, 1, stale_event, expected_pointer_revision=1)


def test_stale_pointer_revision_is_mapped_to_typed_command_error(
    tmp_path: Path,
) -> None:
    """Handler maps StrategyGovernanceCasConflict → AppCommandError(code=...)."""
    governance, _catalog, _store, _pool = _build_services(tmp_path)
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    _seed_v1_active(governance, strategy_id, seed)
    _seed_v2_active(governance, strategy_id, seed)

    handler = ReactivateStrategyHandler(governance)
    with pytest.raises(AppCommandError) as info:
        handler.handle(
            ReactivateStrategyCommand(
                strategy_id=strategy_id,
                version=1,
                actor="ops",
                reason="rollback",
                expected_pointer_revision=1,
            )
        )

    assert "conflict" in str(info.value).lower()
    assert info.value.details["code"] == "STRATEGY_REVISION_CONFLICT"
    assert info.value.details["strategy_id"] == strategy_id
    assert info.value.details["version"] == 1


def test_reactivate_deprecated_target_is_invalid_transition(
    tmp_path: Path,
) -> None:
    """Reactivate rejects a deprecated version (lifecycle guard, not CAS)."""
    governance, _catalog, store, _pool = _build_services(tmp_path)
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    _seed_v1_active(governance, strategy_id, seed)
    _seed_v2_active(governance, strategy_id, seed)

    governance.deprecate(
        strategy_id,
        1,
        event_id="s:1:deprecate:04",
        actor="ops",
        reason="retire",
        decided_at="2026-07-24T00:00:04Z",
    )
    current = store.get_active_pointer(strategy_id)
    assert current is not None
    assert current.pointer_revision == 2

    handler = ReactivateStrategyHandler(governance)
    with pytest.raises(AppCommandError) as info:
        handler.handle(
            ReactivateStrategyCommand(
                strategy_id=strategy_id,
                version=1,
                actor="ops",
                reason="rollback",
                expected_pointer_revision=2,
            )
        )

    assert info.value.details["code"] == "STRATEGY_INVALID_TRANSITION"
    assert info.value.details["strategy_id"] == strategy_id
