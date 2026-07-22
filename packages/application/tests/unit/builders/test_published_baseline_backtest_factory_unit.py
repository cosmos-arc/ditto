"""Runtime-lane selection tests for the frozen numerical factory."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest
from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_backtest_factory import (
    FrozenAuditResearchBacktestFactory,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchSnapshotIdentity,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselinePlanKind,
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    ResearchExecutionAudit,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactUniverseIdentity,
)
from ditto_strategy.alpha.specs import (
    ExecutionSpec,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.models import StrategySpecRecord
from packages.application.tests.unit.process.experiments import (
    test_research_backtest_factory_unit as factory_fixtures,
)


class _NeverBuilder:
    def __init__(self) -> None:
        self.calls = 0

    def build(self, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("the candidate builder crossed into the baseline lane")


def test_factory_uses_candidate_builder_only_for_non_baseline_runtime() -> None:
    _, audit, reader, candidate_builder, loader = factory_fixtures._fixture()
    published_builder = _NeverBuilder()
    checkpoints = factory_fixtures._CheckpointStore()
    factory = FrozenAuditResearchBacktestFactory(
        strategy_reader=reader,
        runtime_builder=candidate_builder,
        published_baseline_builder=published_builder,
        artifact_loader=loader,
        environment=audit.semantics.environment,
        checkpoint_reader=checkpoints,
        checkpoint_writer=checkpoints,
    )

    factory.build(audit, external_should_stop=factory_fixtures._never_stop)

    assert candidate_builder.calls == 1
    assert published_builder.calls == 0


def test_factory_uses_published_builder_only_for_exact_etf_baseline() -> None:
    _, candidate_audit, _, _, loader = factory_fixtures._fixture()
    snapshot = candidate_audit.semantics.snapshot
    spec = StrategySpec(
        strategy_id="published-etf-baseline",
        name="Published ETF baseline",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        execution=ExecutionSpec(frequency="D"),
        params={
            "allocation_method": "equal_weight",
            "scoring_ascending": False,
            "top_k": 3,
        },
        required_datasets=("etf_daily",),
    )
    record = StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=7,
        status="published",
    )
    runtime = PublishedBaselineRuntimeBuilder().build(
        record=record,
        candidate_parameters=(),
        snapshot_identity=ResearchSnapshotIdentity(
            snapshot.exact_snapshot.snapshot_id,
            snapshot.exact_snapshot.manifest_hash,
        ),
    )
    binding = factory_fixtures._binding(runtime)
    registry = default_baseline_registry()
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=BaselineRef("etf_current_active", 1),
            snapshot=snapshot.exact_snapshot,
            universe=ExactUniverseIdentity(
                runtime.legacy_spec.universe,
                candidate_audit.semantics.membership_hash,
            ),
            exact_strategy=binding.exact_strategy,
        )
    )
    semantics = replace(
        candidate_audit.semantics,
        is_baseline=True,
        strategy=binding,
        backtest=replace(
            candidate_audit.semantics.backtest,
            benchmark=None,
            policy_hash=plan.execution_policy.canonical_hash,
        ),
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=plan,
        policy=plan.execution_policy,
    )
    candidate_builder = _NeverBuilder()
    published_builder = factory_fixtures._Builder(runtime)
    checkpoints = factory_fixtures._CheckpointStore()
    factory = FrozenAuditResearchBacktestFactory(
        strategy_reader=factory_fixtures._Reader(record),
        runtime_builder=candidate_builder,
        published_baseline_builder=published_builder,
        artifact_loader=loader,
        environment=semantics.environment,
        checkpoint_reader=checkpoints,
        checkpoint_writer=checkpoints,
    )

    built = factory._build_strategy(semantics, loader.rules)

    assert built.binding == binding
    assert candidate_builder.calls == 0
    assert published_builder.calls == 1


@pytest.mark.parametrize(
    ("status", "expected_reason", "expected_builder_calls"),
    [
        pytest.param(
            "published",
            "published_baseline_lane_not_supported",
            1,
            id="wrong-lane",
        ),
        pytest.param(
            "draft",
            "published_baseline_version_required",
            0,
            id="wrong-status",
        ),
    ],
)
def test_factory_rejects_invalid_published_baseline_lane_or_status(
    status: str,
    expected_reason: str,
    expected_builder_calls: int,
) -> None:
    _, candidate_audit, reader, candidate_builder, loader = factory_fixtures._fixture()
    runtime = replace(candidate_builder.runtime, version_status=status)
    reader.record = replace(reader.record, status=status)
    binding = candidate_audit.semantics.strategy
    plan = BaselineExecutionPlan(
        baseline_ref=BaselineRef("test_exact_stock_extension", 1),
        kind=BaselinePlanKind.CODE_REGISTERED_EXTENSION,
        implementation_key="research.baseline.test_exact_stock_extension.v1",
        executor_contract_version=1,
        descriptor_hash="8" * 64,
        snapshot=candidate_audit.semantics.snapshot.exact_snapshot,
        universe=ExactUniverseIdentity(
            "all_a_shares",
            candidate_audit.semantics.membership_hash,
        ),
        execution_policy=candidate_audit.semantics.policy,
        exact_strategy=binding.exact_strategy,
        semantics=(("source", "published_strategy"),),
    )
    semantics = replace(
        candidate_audit.semantics,
        is_baseline=True,
        baseline_plan=plan,
    )
    audit = ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id=candidate_audit.attempt_id,
        attempt_ordinal=candidate_audit.attempt_ordinal,
        backtest_run_id=candidate_audit.backtest_run_id,
        parent_attempt_id=candidate_audit.parent_attempt_id,
        resume_from_run_id=candidate_audit.resume_from_run_id,
        created_at=candidate_audit.created_at,
    )
    published_builder = factory_fixtures._Builder(runtime)
    checkpoints = factory_fixtures._CheckpointStore()
    factory = FrozenAuditResearchBacktestFactory(
        strategy_reader=reader,
        runtime_builder=_NeverBuilder(),
        published_baseline_builder=published_builder,
        artifact_loader=loader,
        environment=audit.semantics.environment,
        checkpoint_reader=checkpoints,
        checkpoint_writer=checkpoints,
    )

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=factory_fixtures._never_stop)

    assert exc_info.value.details["reason"] == expected_reason
    assert published_builder.calls == expected_builder_calls
