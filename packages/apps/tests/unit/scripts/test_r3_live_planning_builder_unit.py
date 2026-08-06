"""Unit contracts for reusable live R3 planning artifacts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from types import MappingProxyType, SimpleNamespace
from typing import cast

import orjson
import pytest
from ditto_application.commands.strategy import (
    UpdateStrategyCommand,
    UpdateStrategyHandler,
)
from ditto_application.processes.experiments.execution_bundle import (
    CodeEnvironmentLock,
)
from ditto_application.processes.experiments.planning import (
    ExperimentBudgetSpec,
    ResourceCostModel,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_apps.registry.live.r3_live_planning_builder import _identity, _requirements
from ditto_apps.registry.live.r3_live_snapshot_builder import (
    LiveDatasetSnapshotBinding,
    LiveResearchSnapshotBuild,
)
from ditto_apps.scripts.r3_live_planning_builder import (
    ensure_research_candidate,
    planning_request_document,
)
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
def test_live_experiment_identity_is_bound_to_code_environment() -> None:
    candidate = SimpleNamespace(
        strategy_id="strategy-1",
        version=2,
        spec_hash="a" * 64,
    )
    snapshot = SimpleNamespace(
        snapshot_id="snapshot-1",
        manifest_hash="b" * 64,
    )
    first = _identity(
        lane="stock",
        purpose="backend-stock",
        candidate=cast("StrategySpecRecord", candidate),
        snapshot=cast("LiveResearchSnapshotBuild", snapshot),
        environment=CodeEnvironmentLock("commit-1", "c" * 64),
    )

    same = _identity(
        lane="stock",
        purpose="backend-stock",
        candidate=cast("StrategySpecRecord", candidate),
        snapshot=cast("LiveResearchSnapshotBuild", snapshot),
        environment=CodeEnvironmentLock("commit-1", "c" * 64),
    )
    new_code = _identity(
        lane="stock",
        purpose="backend-stock",
        candidate=cast("StrategySpecRecord", candidate),
        snapshot=cast("LiveResearchSnapshotBuild", snapshot),
        environment=CodeEnvironmentLock("commit-2", "c" * 64),
    )
    new_lock = _identity(
        lane="stock",
        purpose="backend-stock",
        candidate=cast("StrategySpecRecord", candidate),
        snapshot=cast("LiveResearchSnapshotBuild", snapshot),
        environment=CodeEnvironmentLock("commit-1", "d" * 64),
    )

    assert same == first
    assert new_code != first
    assert new_lock != first


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


@pytest.mark.unit
def test_planning_document_thaws_frozen_strategy_json(mocker) -> None:
    mocker.patch(
        "ditto_apps.registry.live.r3_live_planning_builder."
        "canonical_validation_protocol_payload",
        return_value={},
    )
    mocker.patch(
        "ditto_apps.registry.live.r3_live_planning_builder."
        "candidate_matrix_spec_payload",
        return_value=MappingProxyType(
            {"baseline": MappingProxyType({"baseline_id": "baseline-1"})}
        ),
    )
    mocker.patch(
        "ditto_apps.registry.live.r3_live_planning_builder.promotion_objective_payload",
        return_value={},
    )
    frozen_spec = MappingProxyType(
        {"execution": MappingProxyType({"frequency": "daily"})}
    )
    request = SimpleNamespace(
        experiment_id="experiment-1",
        research_cycle_id="cycle-1",
        research_cycle_hash="a" * 64,
        strategy_record=SimpleNamespace(
            strategy_id="strategy-1",
            version=2,
            spec_hash="b" * 64,
            spec_json=frozen_spec,
        ),
        snapshot_identity=SimpleNamespace(
            snapshot_id="snapshot-1",
            manifest_hash="c" * 64,
        ),
        validation_request=object(),
        matrix_spec=object(),
        promotion_objective=object(),
        dataset_requirements=(),
        cost_model=ResourceCostModel(1, 1),
        budget=ExperimentBudgetSpec(1, 1, 1, 1),
        seed=1,
        worker_count=1,
        failure_policy=SimpleNamespace(value="continue_candidate_failures"),
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    document = planning_request_document(cast("ExperimentPlanningRequest", request))

    assert document["strategy"] == {
        "spec_hash": "b" * 64,
        "spec_json": {"execution": {"frequency": "daily"}},
        "strategy_id": "strategy-1",
        "version": 2,
    }
    assert document["matrix"] == {"baseline": {"baseline_id": "baseline-1"}}


@pytest.mark.unit
def test_dataset_requirements_start_at_actual_research_snapshot_boundary() -> None:
    binding = LiveDatasetSnapshotBinding(
        dataset_id="stock_daily",
        certification_report_id="certification-1",
        certified_at="2026-08-01T00:00:00+00:00",
        certified_from="2015-01-01",
        certified_through="2026-07-31",
        snapshot_ids=("provider-snapshot-1",),
    )
    snapshot = LiveResearchSnapshotBuild(
        lane="stock",
        snapshot_id="research-snapshot-1",
        manifest_hash="a" * 64,
        dataset_id="r3-live-stock-golden",
        snapshot_start="2015-02-01",
        snapshot_end="2026-07-31",
        source_snapshot_ids=("provider-snapshot-1",),
        dataset_bindings=(binding,),
        primary_authority_snapshot_id="provider-snapshot-1",
        input_evidence=(),
        row_count=1,
    )

    requirements = _requirements(snapshot, ("stock_daily",))

    assert requirements[0].certified_from == date(2015, 2, 1)
