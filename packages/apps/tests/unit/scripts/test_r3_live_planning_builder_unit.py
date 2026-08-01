"""Unit contracts for reusable live R3 planning artifacts."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import orjson
import pytest
from ditto_application.commands.strategy import (
    UpdateStrategyCommand,
    UpdateStrategyHandler,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_apps.scripts.r3_live_planning_builder import ensure_research_candidate
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)


def _seed_record(strategy_id: str, version: int) -> StrategySpecRecord:
    seed = SEED_STRATEGY_SPECS[strategy_id]
    spec_json = cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(seed)),
    )
    record = StrategySpecRecord(
        strategy_id=strategy_id,
        name=seed.name,
        spec_json=spec_json,
        version=version,
        parent_version=None if version == 1 else version - 1,
        created_at=f"2026-08-01T00:00:0{version}Z",
        tags=seed.tags,
    )
    return replace(record, spec_hash=canonical_spec_hash_for_record(record))


@pytest.mark.unit
def test_research_candidate_is_created_once_then_reused() -> None:
    strategy_id = "seed_stock_selection_rotation"

    class _Catalog:
        def __init__(self) -> None:
            self.records = [_seed_record(strategy_id, 1)]
            self.states = {1: "published"}

        def get_spec(
            self, requested_id: str, version: int | None = None
        ) -> StrategySpecRecord | None:
            assert requested_id == strategy_id
            if version is None:
                return self.records[-1]
            return next(
                (item for item in self.records if item.version == version),
                None,
            )

        def get_version_state(self, requested_id: str, version: int) -> str | None:
            assert requested_id == strategy_id
            return self.states.get(version)

    catalog = _Catalog()

    class _Update:
        calls = 0

        def handle(self, command: UpdateStrategyCommand) -> object:
            self.calls += 1
            source = catalog.records[-1]
            catalog.records.append(
                replace(
                    source,
                    version=source.version + 1,
                    parent_version=source.version,
                    created_at="2026-08-01T00:00:02Z",
                )
            )
            catalog.states[source.version + 1] = "draft"
            return object()

    update = _Update()
    first = ensure_research_candidate(
        lane="stock",
        catalog=cast("StrategyCatalogService", catalog),
        update_handler=cast("UpdateStrategyHandler", update),
    )
    second = ensure_research_candidate(
        lane="stock",
        catalog=cast("StrategyCatalogService", catalog),
        update_handler=cast("UpdateStrategyHandler", update),
    )

    assert first.version == 2
    assert second == first
    assert update.calls == 1
