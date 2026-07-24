"""Fail-closed tests for production experiment preflight probes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_executor_probe import (
    BuilderBackedResearchExecutorProbe,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactStrategyIdentity,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    BinderCandidatePlan,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    PlanningIdentityInput,
    ResearchCertificationRequest,
    ResearchDatasetRequirement,
    ResearchExecutorProbeRequest,
    validate_planning_identity,
)
from ditto_application.queries.research_certification import (
    DataReadinessCertificationProbe,
)
from ditto_application.research_validation_contracts import RuntimeValidationEvidence
from ditto_strategy.models import StrategySpecRecord


def test_dataset_requirement_rejects_non_string_dataset_id() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDatasetRequirement(
            cast("str", 1),
            ("provider-snapshot-1",),
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_dataset_requirement",
    }


def test_dataset_requirement_rejects_non_tuple_snapshot_ids() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDatasetRequirement(
            "etf_daily",
            cast("tuple[str, ...]", ["provider-snapshot-1"]),
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_dataset_requirement",
    }


def test_dataset_requirement_rejects_non_string_snapshot_id() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDatasetRequirement(
            "etf_daily",
            cast("tuple[str, ...]", (1,)),
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_dataset_requirement",
    }


def test_dataset_requirement_rejects_non_bool_pit_flag() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDatasetRequirement(
            "etf_daily",
            ("provider-snapshot-1",),
            requires_pit_universe=cast("bool", 1),
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_dataset_requirement",
    }


@pytest.mark.parametrize(
    "snapshot_ids",
    [(), ("provider-snapshot-1", "provider-snapshot-1")],
    ids=("missing", "duplicate"),
)
def test_dataset_requirement_rejects_missing_or_duplicate_snapshot_ids(
    snapshot_ids: tuple[str, ...],
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDatasetRequirement("etf_daily", snapshot_ids)

    assert exc_info.value.details["reason"] == "invalid_dataset_requirement"


def test_dataset_requirement_canonicalizes_snapshot_id_order() -> None:
    requirement = ResearchDatasetRequirement(
        "etf_daily",
        ("provider-snapshot-2", "provider-snapshot-1"),
    )

    assert requirement.expected_snapshot_ids == (
        "provider-snapshot-1",
        "provider-snapshot-2",
    )


def test_planning_identity_rejects_non_tuple_requirements_container() -> None:
    requirement = ResearchDatasetRequirement(
        "etf_daily",
        ("provider-snapshot-1",),
    )

    with pytest.raises(AppProcessError) as exc_info:
        validate_planning_identity(
            PlanningIdentityInput(
                experiment_id="exp-plan-1",
                research_cycle_id="cycle-plan-1",
                research_cycle_hash="c" * 64,
                strategy_record=StrategySpecRecord(
                    strategy_id="seed_etf_rotation",
                    name="ETF rotation",
                    spec_json={"strategy_id": "seed_etf_rotation"},
                    version=3,
                    status="draft",
                ),
                snapshot_identity=ExperimentSnapshotIdentity(
                    snapshot_id="certified-snapshot-1",
                    manifest_hash="d" * 64,
                ),
                dataset_requirements=cast(
                    "tuple[ResearchDatasetRequirement, ...]",
                    [requirement],
                ),
                created_at=datetime(2026, 7, 20, tzinfo=UTC),
            )
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_planning_identity",
    }


@dataclass(frozen=True)
class _LegacySpec:
    required_datasets: tuple[str, ...] = ("etf_daily",)
    universe: str = "csi_etf_broad"


@dataclass(frozen=True)
class _StrategyKind:
    value: str = "etf_rotation"


@dataclass(frozen=True)
class _ResolvedSpec:
    strategy_kind: _StrategyKind = _StrategyKind()


@dataclass(frozen=True)
class _RuntimeEvidence:
    strategy_id: str = "seed_etf_rotation"
    strategy_version: int = 3
    base_spec_hash: str = "a" * 64
    resolved_spec_hash: str = "b" * 64
    parameter_hash: str = "c" * 64
    node_registry_manifest_hash: str = "e" * 64
    pipeline_execution_hash: str = "d" * 64
    factor_registry_manifest_hash: str = "f" * 64
    used_factor_bindings: tuple[object, ...] = field(
        default_factory=lambda: (SimpleNamespace(binding_hash="9" * 64),)
    )
    legacy_spec: _LegacySpec = _LegacySpec()
    resolved_spec: _ResolvedSpec = _ResolvedSpec()
    compiled_expressions: CompiledExpressions | None = None


class _Builder:
    def __init__(
        self,
        *,
        baseline_strategy_id: str = "seed_etf_rotation",
        baseline_strategy_version: int = 2,
        candidate_lane: str = "etf_rotation",
        candidate_universe: str = "csi_etf_broad",
        candidate_datasets: tuple[str, ...] = ("etf_daily",),
        candidate_compiled_expressions: CompiledExpressions | None = None,
        baseline_compiled_expressions: CompiledExpressions | None = None,
    ) -> None:
        self.calls: list[int] = []
        self._baseline_strategy_id = baseline_strategy_id
        self._baseline_strategy_version = baseline_strategy_version
        self._candidate_lane = candidate_lane
        self._candidate_universe = candidate_universe
        self._candidate_datasets = candidate_datasets
        self._candidate_compiled_expressions = candidate_compiled_expressions
        self._baseline_compiled_expressions = baseline_compiled_expressions

    def build(self, **kwargs: object) -> ResearchStrategyRuntime:
        record = cast("StrategySpecRecord", kwargs["record"])
        self.calls.append(record.version)
        if record.version == 2:
            return cast(
                "ResearchStrategyRuntime",
                _RuntimeEvidence(
                    strategy_id=self._baseline_strategy_id,
                    strategy_version=self._baseline_strategy_version,
                    base_spec_hash="f" * 64,
                    resolved_spec_hash="1" * 64,
                    parameter_hash="2" * 64,
                    node_registry_manifest_hash="3" * 64,
                    pipeline_execution_hash="4" * 64,
                    factor_registry_manifest_hash="5" * 64,
                    used_factor_bindings=(SimpleNamespace(binding_hash="6" * 64),),
                    compiled_expressions=self._baseline_compiled_expressions,
                ),
            )
        return cast(
            "ResearchStrategyRuntime",
            _RuntimeEvidence(
                legacy_spec=_LegacySpec(
                    required_datasets=self._candidate_datasets,
                    universe=self._candidate_universe,
                ),
                resolved_spec=_ResolvedSpec(
                    strategy_kind=_StrategyKind(self._candidate_lane),
                ),
                compiled_expressions=self._candidate_compiled_expressions,
            ),
        )


class _StrategyReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def get_spec(self, strategy_id: str, version: int) -> StrategySpecRecord | None:
        self.calls.append((strategy_id, version))
        if (strategy_id, version) != ("seed_etf_rotation", 2):
            return None
        return StrategySpecRecord(
            strategy_id=strategy_id,
            name="ETF rotation baseline",
            spec_json={"strategy_id": strategy_id},
            version=version,
            status="published",
        )

    def get_version_state(self, strategy_id: str, version: int) -> str | None:
        if (strategy_id, version) == ("seed_etf_rotation", 2):
            return "published"
        return "draft"


def test_production_probe_returns_exact_registered_baseline_evidence() -> None:
    candidate_builder = _Builder()
    baseline_builder = _Builder()
    strategy_reader = _StrategyReader()
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", candidate_builder),
        published_baseline_builder=cast(
            "PublishedBaselineRuntimeBuilder",
            baseline_builder,
        ),
        strategy_reader=cast("object", strategy_reader),
    )
    candidate = BinderCandidatePlan(ordinal=2, binder_parameters=())

    result = probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_etf_rotation",
                name="ETF rotation",
                spec_json={"strategy_id": "seed_etf_rotation"},
                version=3,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                snapshot_id="snapshot-1",
                manifest_hash="d" * 64,
            ),
            baseline=BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={
                    "strategy_id": "seed_etf_rotation",
                    "version": 2,
                    "spec_hash": "f" * 64,
                },
            ),
            candidates=(candidate,),
        )
    )

    assert candidate_builder.calls == [3]
    assert baseline_builder.calls == [2]
    assert strategy_reader.calls == [("seed_etf_rotation", 2)]
    assert result.available is True
    assert result.code is None
    assert result.reason is None
    assert result.strategy_spec_hash == "a" * 64
    assert result.node_registry_manifest_hash == "e" * 64
    assert result.factor_registry_manifest_hash == "f" * 64
    assert result.factor_binding_hashes == ("9" * 64,)
    assert result.candidates[0].pipeline_execution_hash == "d" * 64
    assert result.required_datasets == ("etf_daily",)
    assert result.candidates[0].candidate_hash == candidate.candidate_hash
    assert result.runtime_validation_evidence == RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily",),
        max_lookback_sessions=0,
        requires_pit_universe=True,
    )
    registry = default_baseline_registry()
    assert result.baseline_ref == "etf_current_active.v1"
    assert (
        result.baseline_descriptor_hash
        == registry.lookup(
            BaselineRef("etf_current_active", 1)
        ).descriptor.canonical_hash
    )
    assert result.baseline_registry_manifest_hash == registry.manifest_hash
    assert (
        result.baseline_exact_strategy_hash
        == ExactStrategyIdentity(
            "seed_etf_rotation",
            2,
            "f" * 64,
        ).canonical_hash
    )
    assert result.baseline_runtime is not None
    assert result.baseline_runtime.base_spec_hash == "f" * 64
    assert result.baseline_runtime.resolved_spec_hash == "1" * 64
    assert result.baseline_runtime.parameter_hash == "2" * 64
    assert result.baseline_runtime.node_registry_manifest_hash == "3" * 64
    assert result.baseline_runtime.pipeline_execution_hash == "4" * 64
    assert result.baseline_runtime.factor_registry_manifest_hash == "5" * 64
    assert result.baseline_runtime.factor_binding_hashes == ("6" * 64,)
    assert len(result.baseline_runtime.compiled_factor_set_hash) == 64


def test_production_probe_includes_longer_published_baseline_lookback() -> None:
    bridge = FactorBridge()
    candidate_builder = _Builder(
        candidate_compiled_expressions=bridge.compile_and_validate(
            expressions=("ts_mean(close, 4)",),
            weights=(1.0,),
        )
    )
    baseline_builder = _Builder(
        baseline_compiled_expressions=bridge.compile_and_validate(
            expressions=("ts_mean(close, 63)",),
            weights=(1.0,),
        )
    )
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", candidate_builder),
        published_baseline_builder=cast(
            "PublishedBaselineRuntimeBuilder",
            baseline_builder,
        ),
        strategy_reader=cast("object", _StrategyReader()),
    )

    result = probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_etf_rotation",
                name="ETF rotation",
                spec_json={"strategy_id": "seed_etf_rotation"},
                version=3,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                snapshot_id="snapshot-1",
                manifest_hash="d" * 64,
            ),
            baseline=BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={
                    "strategy_id": "seed_etf_rotation",
                    "version": 2,
                    "spec_hash": "f" * 64,
                },
            ),
            candidates=(BinderCandidatePlan(ordinal=2, binder_parameters=()),),
        )
    )

    assert result.available is True
    assert result.runtime_validation_evidence is not None
    assert result.runtime_validation_evidence.max_lookback_sessions == 64
    assert result.baseline_runtime is not None
    assert result.baseline_runtime.max_lookback_sessions == 64


@pytest.mark.parametrize(
    ("strategy_id", "strategy_version"),
    [
        pytest.param("wrong-baseline", 2, id="strategy-id"),
        pytest.param("seed_etf_rotation", 99, id="strategy-version"),
    ],
)
def test_production_probe_rejects_rebuilt_baseline_strategy_identity_drift(
    strategy_id: str,
    strategy_version: int,
) -> None:
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", _Builder()),
        published_baseline_builder=cast(
            "PublishedBaselineRuntimeBuilder",
            _Builder(
                baseline_strategy_id=strategy_id,
                baseline_strategy_version=strategy_version,
            ),
        ),
        strategy_reader=cast("object", _StrategyReader()),
    )

    result = probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_etf_rotation",
                name="ETF rotation",
                spec_json={"strategy_id": "seed_etf_rotation"},
                version=3,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                snapshot_id="snapshot-1",
                manifest_hash="d" * 64,
            ),
            baseline=BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={
                    "strategy_id": "seed_etf_rotation",
                    "version": 2,
                    "spec_hash": "f" * 64,
                },
            ),
            candidates=(BinderCandidatePlan(ordinal=2, binder_parameters=()),),
        )
    )

    assert result.available is False
    assert result.reason == "baseline_runtime_identity_drift"


def test_production_probe_keeps_synthetic_stock_baseline_runtime_identity_empty() -> (
    None
):
    candidate_builder = _Builder(
        candidate_lane="stock_selection",
        candidate_universe="all_a_shares",
        candidate_datasets=("stock_daily",),
    )
    baseline_builder = _Builder()
    strategy_reader = _StrategyReader()
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", candidate_builder),
        published_baseline_builder=cast(
            "PublishedBaselineRuntimeBuilder",
            baseline_builder,
        ),
        strategy_reader=cast("object", strategy_reader),
    )

    result = probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_stock_selection",
                name="Stock selection",
                spec_json={"strategy_id": "seed_stock_selection"},
                version=3,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                snapshot_id="snapshot-1",
                manifest_hash="d" * 64,
            ),
            baseline=BaselineDescriptor(
                descriptor_type="stock-universe-equal-weight",
                payload={},
            ),
            candidates=(BinderCandidatePlan(ordinal=2, binder_parameters=()),),
        )
    )

    assert result.available is True
    assert result.reason is None
    assert result.baseline_runtime is None
    assert strategy_reader.calls == []
    assert baseline_builder.calls == []


def test_production_probe_rejects_moving_etf_baseline_identity() -> None:
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", _Builder()),
        strategy_reader=cast("object", _StrategyReader()),
    )

    result = probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_etf_rotation",
                name="ETF rotation",
                spec_json={"strategy_id": "seed_etf_rotation"},
                version=3,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                snapshot_id="snapshot-1",
                manifest_hash="d" * 64,
            ),
            baseline=BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={"strategy_id": "seed_etf_rotation", "version": 2},
            ),
            candidates=(BinderCandidatePlan(ordinal=2, binder_parameters=()),),
        )
    )

    assert result.available is False
    assert result.code == "SPEC_INVALID"
    assert result.reason == "invalid_etf_baseline_payload"
    assert len(result.candidates) == 1


def test_production_probe_rejects_baseline_runtime_lane_mismatch() -> None:
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", _Builder()),
        strategy_reader=cast("object", _StrategyReader()),
    )

    result = probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=StrategySpecRecord(
                strategy_id="seed_etf_rotation",
                name="ETF rotation",
                spec_json={"strategy_id": "seed_etf_rotation"},
                version=3,
                status="draft",
            ),
            snapshot_identity=ExperimentSnapshotIdentity(
                snapshot_id="snapshot-1",
                manifest_hash="d" * 64,
            ),
            baseline=BaselineDescriptor(
                descriptor_type="stock-universe-equal-weight",
                payload={},
            ),
            candidates=(BinderCandidatePlan(ordinal=2, binder_parameters=()),),
        )
    )

    assert result.available is False
    assert result.code == "REPRODUCIBILITY_FAILED"
    assert result.reason == "baseline_runtime_lane_mismatch"
    assert len(result.candidates) == 1


class _ReadinessFacade:
    def assess(self, **kwargs: object) -> object:
        requirements = cast("tuple[object, ...]", kwargs["requirements"])
        return SimpleNamespace(
            status="ready",
            profile=kwargs["profile"],
            datasets=tuple(
                SimpleNamespace(
                    dataset_id=cast("object", item).dataset_id,
                    certification_report_id="cert-report-1",
                    reason_codes=(),
                )
                for item in requirements
            ),
        )


class _ResearchCatalog:
    def get_dataset_snapshot(self, snapshot_id: str) -> object:
        assert snapshot_id == "research-snapshot-1"
        return SimpleNamespace(
            snapshot_id=snapshot_id,
            dataset_id="research-etf-rotation",
            manifest_hash="d" * 64,
            source_snapshot_ids=("provider-snapshot-1",),
            snapshot_start="2016-01-01",
            snapshot_end="2025-12-31",
            known_at_policy="sample_time",
            builder_version="research-builder-v1",
        )


def test_certification_probe_reads_authoritative_research_snapshot_identity() -> None:
    probe = DataReadinessCertificationProbe(
        cast("object", _ReadinessFacade()),
        cast("object", _ResearchCatalog()),
    )
    identity = ExperimentSnapshotIdentity("research-snapshot-1", "d" * 64)

    result = probe.assess(
        ResearchCertificationRequest(
            profile="r2-modern-a-share-v1",
            required_from=date(2016, 1, 1),
            required_to=date(2025, 12, 31),
            requirements=(
                ResearchDatasetRequirement(
                    "etf_daily",
                    ("provider-snapshot-1",),
                ),
            ),
            snapshot_identity=identity,
        )
    )

    assert result.ready is True
    assert result.snapshot_evidence is not None
    assert result.snapshot_evidence.snapshot_id == identity.snapshot_id
    assert result.snapshot_evidence.manifest_hash == identity.manifest_hash
    assert result.snapshot_evidence.source_snapshot_ids == ("provider-snapshot-1",)
