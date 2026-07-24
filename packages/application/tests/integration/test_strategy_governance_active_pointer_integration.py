"""End-to-end governance integration: draft → publish → active pointer → catalog read.

Proves the governance control plane (Task 15/16a) closes a full loop with the
catalog bridge (Task 16b): a version created and activated through governance is
resolvable as the active published payload via ``StrategyCatalogService``, with a
content-addressed ``spec_hash`` that matches the backtest manifest hash.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)


def _build_services(tmp_path: Path) -> tuple[GovernanceService, StrategyCatalogService]:
    """Wire governance + catalog over one shared metadata pool."""
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    SQLiteStrategySpecWriter(pool).init_schema()
    governance_store = SQLiteStrategyGovernanceStore(pool)
    governance_store.init_schema()
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=SQLiteStrategySpecWriter(pool),
        active_pointer_reader=governance_store,
    )
    return GovernanceService(governance_store), catalog


def test_governance_publish_makes_spec_resolvable_as_active(tmp_path: Path) -> None:
    """create_draft → publish_and_activate → catalog resolves active payload."""
    governance, catalog = _build_services(tmp_path)

    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    spec_json = asdict(seed)
    record = StrategySpecRecord(
        strategy_id=strategy_id,
        name=seed.name,
        spec_json=spec_json,
        version=1,
        created_at="2026-07-24T00:00:00Z",
        tags=seed.tags,
    )
    record = replace(record, spec_hash=canonical_spec_hash_for_record(record))

    # No pointer yet → catalog reports no active published spec.
    assert catalog.get_active_published(strategy_id) is None

    governance.create_draft(
        strategy_id=strategy_id,
        version=1,
        spec_record=record,
        created_at="2026-07-24T00:00:00Z",
    )
    governance.publish_and_activate(
        strategy_id=strategy_id,
        version=1,
        actor="seed",
        reason="bootstrap",
        decided_at="2026-07-24T00:00:01Z",
    )

    active = catalog.get_active_published(strategy_id)
    assert active is not None
    assert active.strategy_id == strategy_id
    assert active.version == 1
    assert active.spec_hash == record.spec_hash
    # spec_json round-trips through orjson (tuple -> list); spec_hash already
    # proves canonical equivalence via deserialize -> V2 -> hash.
    assert active.spec_json["template"] == spec_json["template"]


def test_active_pointer_switches_to_new_version(tmp_path: Path) -> None:
    """Activating v2 swaps the active pointer; catalog resolves v2 payload."""
    governance, catalog = _build_services(tmp_path)

    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    spec_json = asdict(seed)

    def _record(version: int, created_at: str) -> StrategySpecRecord:
        base = StrategySpecRecord(
            strategy_id=strategy_id,
            name=seed.name,
            spec_json=spec_json,
            version=version,
            parent_version=None if version == 1 else 1,
            created_at=created_at,
            tags=seed.tags,
        )
        return replace(base, spec_hash=canonical_spec_hash_for_record(base))

    v1 = _record(1, "2026-07-24T00:00:00Z")
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

    v2 = _record(2, "2026-07-24T00:00:02Z")
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

    active = catalog.get_active_published(strategy_id)
    assert active is not None
    assert active.version == 2
    assert active.parent_version == 1
