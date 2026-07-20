"""Fail-closed tests for production experiment preflight probes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_application.builders.research_executor_probe import (
    BuilderBackedResearchExecutorProbe,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppProcessError
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
    base_spec_hash: str = "a" * 64
    resolved_spec_hash: str = "b" * 64
    parameter_hash: str = "c" * 64
    node_registry_manifest_hash: str = "e" * 64
    legacy_spec: _LegacySpec = _LegacySpec()
    resolved_spec: _ResolvedSpec = _ResolvedSpec()
    compiled_expressions: object = field(
        default_factory=lambda: SimpleNamespace(
            expressions=(SimpleNamespace(analysis=SimpleNamespace(lookback=21)),)
        )
    )


class _Builder:
    def __init__(self) -> None:
        self.calls = 0

    def build(self, **_kwargs: object) -> ResearchStrategyRuntime:
        self.calls += 1
        return cast("ResearchStrategyRuntime", _RuntimeEvidence())


def test_production_probe_blocks_until_task9_baseline_runner_is_registered() -> None:
    builder = _Builder()
    probe = BuilderBackedResearchExecutorProbe(
        cast("ResearchRuntimeBuilder", builder),
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
                payload={"strategy_id": "seed_etf_rotation", "version": 2},
            ),
            candidates=(candidate,),
        )
    )

    assert builder.calls == 1
    assert result.available is False
    assert result.code == "EXECUTOR_UNAVAILABLE"
    assert result.reason == "baseline_executor_unavailable"
    assert result.strategy_spec_hash == "a" * 64
    assert result.node_registry_manifest_hash == "e" * 64
    assert result.required_datasets == ("etf_daily",)
    assert result.candidates[0].candidate_hash == candidate.candidate_hash
    assert result.runtime_validation_evidence == RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily",),
        max_lookback_sessions=21,
        requires_pit_universe=True,
    )


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
