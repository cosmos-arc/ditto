"""Deterministic research execution-bundle tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from inspect import signature

import orjson
import pytest
from ditto_analysis.experiments import ContentHash
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanKind,
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchExecutionAudit,
    ResearchExecutionSemantics,
    ResearchFactorExecutionBinding,
    ResearchFillMode,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
    VersionedExecutionComponent,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ExactUniverseIdentity,
    default_stock_execution_policy,
)
from ditto_application.processes.experiments.research_data_feed import (
    research_data_feed_manifest_hash,
)
from ditto_features.expression.contracts import CompileIdentity
from ditto_strategy.alpha.parameters import CandidateParameter


def _sha(character: str) -> str:
    return character * 64


def _factor_binding(
    factor_id: str,
    version: int,
    character: str,
) -> ResearchFactorExecutionBinding:
    return ResearchFactorExecutionBinding(
        factor_id=factor_id,
        version=version,
        spec_hash=_sha(character),
        compile_identity=CompileIdentity(
            compile_input_hash=_sha("a"),
            operator_fingerprint=_sha("b"),
            compiler_fingerprint=_sha("c"),
            cache_key=_sha("d"),
            engine_codegen_version="polars-codegen-v1",
            analysis_version="factor-analysis-v1",
            polars_version="1.0.0",
            expr_serialization_format="polars-expr-v1",
            operator_versions=(("rank", "1"),),
            global_compile_flags=("grain=1d",),
        ),
        compiled_expression_hash=_sha("8"),
        analysis_execution_hash=_sha("7"),
        artifact=ContentAddressedResearchInput(
            input_id=f"{factor_id}@{version}",
            artifact_kind="factor",
            content_hash=_sha(character),
            schema_hash=_sha("9"),
        ),
    )


def _backtest_binding() -> BacktestExecutionConfigBinding:
    fee_schedule = ContentAddressedResearchInput(
        input_id="fee_schedule",
        artifact_kind="parquet",
        content_hash=_sha("c"),
        schema_hash=_sha("d"),
    )
    instrument_rules = ContentAddressedResearchInput(
        input_id="instrument_rules",
        artifact_kind="instrument_rules",
        content_hash=_sha("e"),
        schema_hash=_sha("f"),
    )
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=100_000_000,
        currency="CNY",
        engine=VersionedExecutionComponent("ditto_backtest.engine", 1),
        engine_version="0.1.0",
        rebalance_policy=VersionedExecutionComponent(
            "ditto_strategy.rebalance_schedule",
            1,
        ),
        rebalance_frequency="daily",
        participation_rate_ppm=50_000,
        fill_mode=ResearchFillMode.PARTIAL,
        fill_model=VersionedExecutionComponent("ditto_backtest.a_share_fill", 1),
        brokerage_model=VersionedExecutionComponent(
            "ditto_backtest.brokerage",
            1,
        ),
        execution_planner=VersionedExecutionComponent(
            "ditto_execution.simple_planner",
            1,
        ),
        slippage_basis_points=1,
        benchmark=ExactBenchmarkBinding(
            instrument_id=3_000_001,
            instrument_identity_hash=_sha("1"),
            mapping_input=instrument_rules,
            bars_input=ContentAddressedResearchInput(
                input_id="benchmark_bars",
                artifact_kind="bars",
                content_hash=_sha("3"),
                schema_hash=_sha("4"),
            ),
        ),
        policy_hash=default_stock_execution_policy().canonical_hash,
        policy_model_evidence=(
            PolicyModelEvidenceBinding(
                role="fees",
                implementation=VersionedExecutionComponent(
                    "ditto_execution.a_share_fee",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                inputs=(fee_schedule,),
            ),
            PolicyModelEvidenceBinding(
                role="rules",
                implementation=VersionedExecutionComponent(
                    "ditto_kernel.instrument_rules",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                inputs=(instrument_rules,),
            ),
            PolicyModelEvidenceBinding(
                role="settlement",
                implementation=VersionedExecutionComponent(
                    "ditto_backtest.a_share_settlement",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                inputs=(instrument_rules,),
            ),
            PolicyModelEvidenceBinding(
                role="slippage",
                implementation=VersionedExecutionComponent(
                    "ditto_backtest.fixed_bps_slippage",
                    1,
                ),
                evidence_source=ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY,
                inputs=(),
            ),
        ),
        pre_trade_checks=(
            VersionedExecutionComponent("ditto_risk.lot_size", 1),
            VersionedExecutionComponent("ditto_risk.buying_power", 1),
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=_sha("5"),
    )


def _backtest_inputs(
    binding: BacktestExecutionConfigBinding,
) -> tuple[ContentAddressedResearchInput, ...]:
    inputs = {
        item.input_id: item
        for model in binding.policy_model_evidence
        for item in model.inputs
    }
    if binding.benchmark is not None:
        inputs[binding.benchmark.bars_input.input_id] = binding.benchmark.bars_input
    return tuple(sorted(inputs.values(), key=lambda item: item.input_id))


def _semantics() -> ResearchExecutionSemantics:
    backtest = _backtest_binding()
    factor_bindings = (
        _factor_binding("momentum_1m", 1, "6"),
        _factor_binding("quality_roe", 2, "7"),
    )
    snapshot = ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot("snapshot-1", _sha("2")),
        dataset_id="research-stock-selection",
        source_snapshot_ids=("provider-snapshot-1", "provider-snapshot-2"),
        known_at_policy="sample_time",
        builder_version="research-builder-v1",
        inputs=(
            ContentAddressedResearchInput(
                input_id="calendar",
                artifact_kind="calendar",
                content_hash=_sha("a"),
                schema_hash=_sha("b"),
            ),
            ContentAddressedResearchInput(
                input_id="membership",
                artifact_kind="membership",
                content_hash=_sha("5"),
                schema_hash=_sha("6"),
            ),
            *(item.artifact for item in factor_bindings),
            *_backtest_inputs(backtest),
        ),
    )
    backtest = replace(
        backtest,
        data_feed_manifest_hash=research_data_feed_manifest_hash(snapshot),
    )
    return ResearchExecutionSemantics(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        fold_id="fold-1",
        fold_role="walk_forward",
        is_baseline=False,
        plan_hash=_sha("a"),
        launch_spec_hash=_sha("b"),
        fold_spec_hash=_sha("c"),
        strategy=StrategyExecutionBinding(
            exact_strategy=ExactStrategyIdentity(
                "stock-selection",
                3,
                _sha("d"),
            ),
            resolved_spec_hash=_sha("e"),
            parameter_hash=_sha("f"),
            node_registry_manifest_hash=_sha("1"),
            pipeline_execution_hash=_sha("9"),
            factor_registry_manifest_hash=_sha("0"),
            compiled_factor_set_hash=_sha("a"),
            factor_bindings=factor_bindings,
        ),
        backtest=backtest,
        snapshot=snapshot,
        membership_hash=_sha("7"),
        membership_projection_hash=_sha("8"),
        train_start=date(2018, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        purge_sessions=5,
        embargo_sessions=5,
        seed=17,
        knowledge_lag_days=1,
        execution_delay_sessions=1,
        baseline_registry_manifest_hash=_sha("9"),
        baseline_plan=None,
        policy=default_stock_execution_policy(),
        environment=CodeEnvironmentLock(
            code_version="git:abc123",
            environment_lock_hash=_sha("e"),
        ),
    )


def _snapshot_without_factors(
    snapshot: ResearchSnapshotBinding,
) -> ResearchSnapshotBinding:
    return replace(
        snapshot,
        inputs=tuple(
            item for item in snapshot.inputs if item.artifact_kind != "factor"
        ),
    )


def test_strategy_binding_requires_registry_and_compiler_factor_identity() -> None:
    parameters = signature(StrategyExecutionBinding).parameters

    assert "factor_registry_manifest_hash" in parameters
    assert "pipeline_execution_hash" in parameters
    assert "factor_bindings" in parameters
    assert "candidate_parameters" in parameters
    assert "factor_versions" not in parameters


def test_factor_registry_compiler_and_artifact_identity_change_fingerprint() -> None:
    original = _semantics()
    assert type(original.strategy) is StrategyExecutionBinding
    strategy = original.strategy
    first = strategy.factor_bindings[0]
    changed_compile = replace(
        first,
        compile_identity=replace(
            first.compile_identity,
            cache_key=_sha("f"),
        ),
    )
    changed_artifact = replace(
        first.artifact,
        content_hash=_sha("e"),
    )
    changed_factor = replace(first, artifact=changed_artifact)
    changed_expression = replace(first, compiled_expression_hash=_sha("0"))
    changed_analysis = replace(first, analysis_execution_hash=_sha("2"))
    variants = (
        replace(
            original,
            strategy=replace(
                strategy,
                factor_registry_manifest_hash=_sha("f"),
            ),
        ),
        replace(
            original,
            strategy=replace(
                strategy,
                factor_bindings=(
                    changed_analysis,
                    *strategy.factor_bindings[1:],
                ),
            ),
        ),
        replace(
            original,
            strategy=replace(
                strategy,
                factor_bindings=(
                    changed_expression,
                    *strategy.factor_bindings[1:],
                ),
            ),
        ),
        replace(
            original,
            strategy=replace(
                strategy,
                factor_bindings=(
                    changed_compile,
                    *strategy.factor_bindings[1:],
                ),
            ),
        ),
        replace(
            original,
            strategy=replace(
                strategy,
                factor_bindings=(
                    changed_factor,
                    *strategy.factor_bindings[1:],
                ),
            ),
            snapshot=replace(
                original.snapshot,
                inputs=tuple(
                    changed_artifact if item == first.artifact else item
                    for item in original.snapshot.inputs
                ),
            ),
        ),
    )

    assert all(
        item.reproduction_fingerprint != original.reproduction_fingerprint
        for item in variants
    )


def test_typed_candidate_parameters_are_part_of_execution_fingerprint() -> None:
    original = _semantics()
    assert type(original.strategy) is StrategyExecutionBinding
    changed = replace(
        original,
        strategy=replace(
            original.strategy,
            candidate_parameters=(CandidateParameter("/candidate/top_k", 20),),
        ),
    )

    assert changed.reproduction_fingerprint != original.reproduction_fingerprint


def test_actual_pipeline_execution_hash_is_part_of_fingerprint() -> None:
    original = _semantics()
    assert type(original.strategy) is StrategyExecutionBinding

    changed = replace(
        original,
        strategy=replace(original.strategy, pipeline_execution_hash=_sha("2")),
    )

    assert changed.reproduction_fingerprint != original.reproduction_fingerprint


def test_compiled_factor_set_hash_is_part_of_fingerprint() -> None:
    original = _semantics()
    assert type(original.strategy) is StrategyExecutionBinding

    changed = replace(
        original,
        strategy=replace(original.strategy, compiled_factor_set_hash=_sha("2")),
    )

    assert changed.reproduction_fingerprint != original.reproduction_fingerprint


def test_semantics_rejects_factor_artifact_outside_authoritative_binding() -> None:
    original = _semantics()
    inputs = tuple(
        item for item in original.snapshot.inputs if item.input_id != "momentum_1m@1"
    )

    with pytest.raises(AppProcessError) as captured:
        replace(original, snapshot=replace(original.snapshot, inputs=inputs))

    assert captured.value.details["reason"] == "factor_input_binding_drift"


def test_candidate_consumes_only_bound_factor_subset_of_complete_snapshot() -> None:
    original = _semantics()
    unused_factor = _factor_binding("unused_value", 3, "4").artifact
    complete_snapshot = replace(
        original.snapshot,
        inputs=(*original.snapshot.inputs, unused_factor),
    )

    semantics = replace(original, snapshot=complete_snapshot)

    assert type(semantics.strategy) is StrategyExecutionBinding
    assert semantics.strategy.factor_versions == (
        ("momentum_1m", 1),
        ("quality_roe", 2),
    )
    assert unused_factor in semantics.snapshot.inputs
    assert semantics.reproduction_fingerprint != original.reproduction_fingerprint


def test_semantics_rejects_arbitrary_data_feed_manifest_hash() -> None:
    original = _semantics()

    with pytest.raises(AppProcessError) as captured:
        replace(
            original,
            backtest=replace(
                original.backtest,
                data_feed_manifest_hash=_sha("0"),
            ),
        )

    assert captured.value.details["reason"] == "data_feed_manifest_hash_drift"


def test_reproduction_fingerprint_is_canonical_and_stable() -> None:
    first = _semantics()
    second = _semantics()

    assert first.reproduction_fingerprint == second.reproduction_fingerprint
    assert isinstance(first.reproduction_fingerprint, ContentHash)
    assert first.canonical_payload == second.canonical_payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", 18),
        ("knowledge_lag_days", 2),
        ("execution_delay_sessions", 2),
        ("membership_hash", _sha("f")),
        ("plan_hash", _sha("0")),
    ],
)
def test_every_result_determining_control_changes_fingerprint(
    field: str,
    value: object,
) -> None:
    original = _semantics()
    changed = replace(original, **{field: value})

    assert changed.reproduction_fingerprint != original.reproduction_fingerprint


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("initial_cash_minor_units", 200_000_000),
        ("engine", VersionedExecutionComponent("ditto_backtest.engine", 2)),
        ("engine_version", "0.2.0"),
        (
            "rebalance_policy",
            VersionedExecutionComponent("ditto_strategy.rebalance_schedule", 2),
        ),
        ("rebalance_frequency", "weekly"),
        ("participation_rate_ppm", 100_000),
        ("fill_mode", ResearchFillMode.ALL_OR_NOTHING),
        ("benchmark", None),
    ],
)
def test_every_backtest_result_control_changes_fingerprint(
    field: str,
    value: object,
) -> None:
    original = _semantics()
    changed = replace(
        original,
        backtest=replace(original.backtest, **{field: value}),
    )

    assert changed.reproduction_fingerprint != original.reproduction_fingerprint


def test_slippage_control_and_policy_change_fingerprint_together() -> None:
    original = _semantics()
    policy = replace(
        original.policy,
        slippage=replace(original.policy.slippage, basis_points=2),
    )
    backtest = replace(
        original.backtest,
        slippage_basis_points=2,
        policy_hash=policy.canonical_hash,
    )

    changed = replace(original, policy=policy, backtest=backtest)

    assert changed.reproduction_fingerprint != original.reproduction_fingerprint


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("initial_cash_minor_units", 0, "invalid_initial_cash"),
        ("initial_cash_minor_units", 1.0, "invalid_initial_cash"),
        ("participation_rate_ppm", -1, "invalid_participation_rate"),
        ("participation_rate_ppm", 1_000_001, "invalid_participation_rate"),
        ("fill_mode", "provider_default", "invalid_fill_mode"),
        ("policy_hash", "latest", "invalid_content_hash"),
        ("data_feed_manifest_hash", "provider", "invalid_content_hash"),
    ],
)
def test_backtest_execution_binding_fails_closed(
    field: str,
    value: object,
    reason: str,
) -> None:
    with pytest.raises(AppProcessError) as captured:
        replace(_backtest_binding(), **{field: value})

    assert captured.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert captured.value.details["reason"] == reason


def test_semantics_rejects_policy_model_implementation_drift() -> None:
    original = _semantics()
    models = tuple(
        replace(
            item,
            implementation=VersionedExecutionComponent("provider.latest", 1),
        )
        if item.role == "fees"
        else item
        for item in original.backtest.policy_model_evidence
    )

    with pytest.raises(AppProcessError) as captured:
        replace(
            original,
            backtest=replace(original.backtest, policy_model_evidence=models),
        )

    assert captured.value.details["reason"] == "backtest_policy_model_drift"


def test_backtest_binding_rejects_duplicate_policy_model_role() -> None:
    original = _backtest_binding()

    with pytest.raises(AppProcessError) as captured:
        replace(
            original,
            policy_model_evidence=(
                *original.policy_model_evidence,
                original.policy_model_evidence[0],
            ),
        )

    assert captured.value.details["reason"] == "duplicate_policy_model_evidence"


def test_semantics_rejects_model_input_outside_frozen_snapshot() -> None:
    original = _semantics()
    inputs = tuple(
        item for item in original.snapshot.inputs if item.input_id != "fee_schedule"
    )

    with pytest.raises(AppProcessError) as captured:
        replace(original, snapshot=replace(original.snapshot, inputs=inputs))

    assert captured.value.details["reason"] == "backtest_input_evidence_drift"


def test_synthetic_baseline_binding_has_no_fake_strategy_or_registry_identity() -> None:
    binding = BaselineExecutorBinding(
        baseline_ref="equal_weight.v1",
        kind=BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
        descriptor_hash=_sha("a"),
        implementation_key="ditto_analysis.equal_weight_baseline",
        executor_contract_version=1,
        registry_manifest_hash=_sha("b"),
        factor_versions=(),
    )

    assert binding.as_payload() == {
        "baseline_ref": "equal_weight.v1",
        "kind": "stock_universe_equal_weight",
        "descriptor_hash": _sha("a"),
        "executor_contract_version": 1,
        "factor_versions": [],
        "implementation_key": "ditto_analysis.equal_weight_baseline",
        "registry_manifest_hash": _sha("b"),
    }
    assert "strategy_id" not in binding.as_payload()
    assert "node_registry_manifest_hash" not in binding.as_payload()


def test_stock_synthetic_baseline_rejects_factor_dependencies() -> None:
    with pytest.raises(AppProcessError) as captured:
        BaselineExecutorBinding(
            baseline_ref="stock_universe_equal_weight.v1",
            kind=BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
            descriptor_hash=_sha("a"),
            implementation_key="research.baseline.stock_universe_equal_weight.v1",
            executor_contract_version=1,
            registry_manifest_hash=_sha("b"),
            factor_versions=(("momentum_1m", 1),),
        )

    assert captured.value.details["reason"] == "unexpected_baseline_factor_binding"


def test_synthetic_baseline_semantics_payload_has_explicit_executor_kind() -> None:
    original = _semantics()
    registry = default_baseline_registry()
    ref = BaselineRef("stock_universe_equal_weight", 1)
    descriptor = registry.lookup(ref).descriptor
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=ref,
            snapshot=original.snapshot.exact_snapshot,
            universe=ExactUniverseIdentity("pit-stock", original.membership_hash),
            exact_strategy=None,
        )
    )
    binding = BaselineExecutorBinding(
        baseline_ref=ref.identity,
        kind=descriptor.kind,
        descriptor_hash=descriptor.canonical_hash,
        implementation_key=descriptor.implementation_key,
        executor_contract_version=descriptor.executor_contract_version,
        registry_manifest_hash=registry.manifest_hash,
        factor_versions=(),
    )

    semantics = replace(
        original,
        is_baseline=True,
        strategy=binding,
        snapshot=_snapshot_without_factors(original.snapshot),
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=plan,
    )
    payload = orjson.loads(semantics.canonical_payload)

    assert payload["strategy"]["kind"] == "baseline_executor"
    assert payload["strategy"]["binding"]["baseline_ref"] == ref.identity


def test_synthetic_baseline_consumes_zero_factors_from_shared_snapshot() -> None:
    original = _semantics()
    registry = default_baseline_registry()
    ref = BaselineRef("stock_universe_equal_weight", 1)
    descriptor = registry.lookup(ref).descriptor
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=ref,
            snapshot=original.snapshot.exact_snapshot,
            universe=ExactUniverseIdentity("pit-stock", original.membership_hash),
            exact_strategy=None,
        )
    )
    binding = BaselineExecutorBinding(
        baseline_ref=ref.identity,
        kind=descriptor.kind,
        descriptor_hash=descriptor.canonical_hash,
        implementation_key=descriptor.implementation_key,
        executor_contract_version=descriptor.executor_contract_version,
        registry_manifest_hash=registry.manifest_hash,
        factor_versions=(),
    )

    semantics = replace(
        original,
        is_baseline=True,
        strategy=binding,
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=plan,
    )

    assert binding.factor_versions == ()
    assert any(item.artifact_kind == "factor" for item in semantics.snapshot.inputs)


def test_stock_baseline_plan_rejects_catalog_strategy_binding() -> None:
    original = _semantics()
    registry = default_baseline_registry()
    ref = BaselineRef("stock_universe_equal_weight", 1)
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=ref,
            snapshot=original.snapshot.exact_snapshot,
            universe=ExactUniverseIdentity("pit-stock", original.membership_hash),
        )
    )

    with pytest.raises(AppProcessError) as captured:
        replace(
            original,
            is_baseline=True,
            baseline_registry_manifest_hash=registry.manifest_hash,
            baseline_plan=plan,
            policy=plan.execution_policy,
            backtest=replace(
                original.backtest,
                policy_hash=plan.execution_policy.canonical_hash,
            ),
        )

    assert captured.value.details["reason"] == "baseline_strategy_binding_kind_drift"


def test_etf_baseline_plan_rejects_wrong_exact_strategy() -> None:
    original = _semantics()
    registry = default_baseline_registry()
    ref = BaselineRef("etf_current_active", 1)
    expected = ExactStrategyIdentity("etf-current", 2, _sha("a"))
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=ref,
            snapshot=original.snapshot.exact_snapshot,
            universe=ExactUniverseIdentity("pit-etf", original.membership_hash),
            exact_strategy=expected,
        )
    )
    wrong = replace(
        original.strategy,
        exact_strategy=ExactStrategyIdentity("etf-current", 3, _sha("b")),
    )

    with pytest.raises(AppProcessError) as captured:
        replace(
            original,
            is_baseline=True,
            strategy=wrong,
            baseline_registry_manifest_hash=registry.manifest_hash,
            baseline_plan=plan,
            policy=plan.execution_policy,
            backtest=replace(
                original.backtest,
                policy_hash=plan.execution_policy.canonical_hash,
            ),
        )

    assert captured.value.details["reason"] == "baseline_exact_strategy_drift"


def test_synthetic_baseline_plan_rejects_wrong_executor_kind() -> None:
    original = _semantics()
    registry = default_baseline_registry()
    ref = BaselineRef("stock_universe_equal_weight", 1)
    descriptor = registry.lookup(ref).descriptor
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=ref,
            snapshot=original.snapshot.exact_snapshot,
            universe=ExactUniverseIdentity("pit-stock", original.membership_hash),
        )
    )
    wrong = BaselineExecutorBinding(
        baseline_ref=ref.identity,
        kind=BaselinePlanKind.CODE_REGISTERED_EXTENSION,
        descriptor_hash=descriptor.canonical_hash,
        implementation_key=descriptor.implementation_key,
        executor_contract_version=descriptor.executor_contract_version,
        registry_manifest_hash=registry.manifest_hash,
        factor_versions=(),
    )

    with pytest.raises(AppProcessError) as captured:
        replace(
            original,
            is_baseline=True,
            strategy=wrong,
            snapshot=_snapshot_without_factors(original.snapshot),
            baseline_registry_manifest_hash=registry.manifest_hash,
            baseline_plan=plan,
            policy=plan.execution_policy,
            backtest=replace(
                original.backtest,
                policy_hash=plan.execution_policy.canonical_hash,
            ),
        )

    assert captured.value.details["reason"] == "baseline_executor_identity_drift"


def test_attempt_audit_changes_bundle_hash_but_not_reproduction_fingerprint() -> None:
    semantics = _semantics()
    first = ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id="attempt-1",
        attempt_ordinal=1,
        backtest_run_id="run-1",
        parent_attempt_id=None,
        resume_from_run_id=None,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    retry = ResearchExecutionAudit.create(
        semantics=semantics,
        attempt_id="attempt-2",
        attempt_ordinal=2,
        backtest_run_id="run-2",
        parent_attempt_id="attempt-1",
        resume_from_run_id="run-1",
        created_at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert first.reproduction_fingerprint == retry.reproduction_fingerprint
    assert first.bundle_hash != retry.bundle_hash
    assert first.canonical_payload != retry.canonical_payload


def test_snapshot_inputs_and_source_ids_are_canonicalized() -> None:
    snapshot = ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot("snapshot-1", _sha("2")),
        dataset_id="research-stock-selection",
        source_snapshot_ids=("provider-b", "provider-a"),
        known_at_policy="sample_time",
        builder_version="builder-v1",
        inputs=(
            ContentAddressedResearchInput(
                input_id="z",
                artifact_kind="parquet",
                content_hash=_sha("3"),
                schema_hash=_sha("4"),
            ),
            ContentAddressedResearchInput(
                input_id="a",
                artifact_kind="json",
                content_hash=_sha("5"),
                schema_hash=_sha("6"),
            ),
        ),
    )

    assert snapshot.source_snapshot_ids == ("provider-a", "provider-b")
    assert tuple(item.input_id for item in snapshot.inputs) == ("a", "z")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_snapshot_ids", (), "missing_source_snapshot_identity"),
        ("inputs", (), "missing_research_input"),
        ("known_at_policy", "", "invalid_execution_identity"),
        (
            "known_at_policy",
            "explicit_cutoff",
            "unsupported_known_at_policy",
        ),
    ],
)
def test_snapshot_binding_fails_closed(
    field: str,
    value: object,
    reason: str,
) -> None:
    kwargs = {
        "exact_snapshot": ExactResearchSnapshot("snapshot-1", _sha("2")),
        "dataset_id": "research-stock-selection",
        "source_snapshot_ids": ("provider-snapshot-1",),
        "known_at_policy": "sample_time",
        "builder_version": "builder-v1",
        "inputs": (
            ContentAddressedResearchInput(
                input_id="bars",
                artifact_kind="parquet",
                content_hash=_sha("3"),
                schema_hash=_sha("4"),
            ),
        ),
    }
    kwargs[field] = value

    with pytest.raises(AppProcessError) as captured:
        ResearchSnapshotBinding(
            exact_snapshot=kwargs["exact_snapshot"],
            dataset_id=kwargs["dataset_id"],
            source_snapshot_ids=kwargs["source_snapshot_ids"],
            known_at_policy=kwargs["known_at_policy"],
            builder_version=kwargs["builder_version"],
            inputs=kwargs["inputs"],
        )

    assert captured.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert captured.value.details["reason"] == reason


def test_semantics_rejects_inverted_windows_and_unregistered_baseline() -> None:
    original = _semantics()

    with pytest.raises(AppProcessError) as inverted:
        replace(original, test_start=date(2025, 1, 1), test_end=date(2024, 1, 1))
    assert inverted.value.details["reason"] == "invalid_execution_window"

    with pytest.raises(AppProcessError) as baseline:
        replace(original, is_baseline=True)
    assert baseline.value.details["reason"] == "baseline_plan_required"
