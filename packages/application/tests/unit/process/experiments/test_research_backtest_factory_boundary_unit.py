"""Fail-closed public-boundary tests for the frozen research factory."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import polars as pl
import pytest
from ditto_application.builders.research_backtest_factory import (
    FrozenAuditResearchBacktestFactory,
)
from ditto_application.builders.research_factor_registry import (
    ResearchFactorBinding,
    ResearchFactorRegistry,
    analysis_execution_hash,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselinePlanKind,
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ResearchExecutionAudit,
    ResearchFactorExecutionBinding,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.research_data_feed import (
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_features.expression.contracts import (
    Analysis,
    CompiledDerivedExpression,
)
from ditto_kernel.order import OrderType
from ditto_strategy.alpha.parameters import CandidateParameter, legacy_parameter_path
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.alpha.specs import StrategyKind
from ditto_strategy.models import StrategySpecRecord
from packages.application.tests.unit.process.experiments import (
    test_research_backtest_factory_unit as fixtures,
)


def _assert_rejected(
    factory: FrozenAuditResearchBacktestFactory,
    audit: ResearchExecutionAudit,
    reason: str,
    *,
    external_should_stop: Callable[[], bool] = fixtures._never_stop,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory.build(audit, external_should_stop=external_should_stop)
    assert exc_info.value.details["reason"] == reason


def _new_factory(
    *,
    reader: object,
    builder: object,
    loader: object,
    environment: CodeEnvironmentLock,
    published_builder: object | None = None,
) -> FrozenAuditResearchBacktestFactory:
    checkpoints = fixtures._CheckpointStore()
    return FrozenAuditResearchBacktestFactory(
        strategy_reader=cast("fixtures._Reader", reader),
        runtime_builder=cast("fixtures._Builder", builder),
        published_baseline_builder=cast("fixtures._Builder | None", published_builder),
        artifact_loader=cast("fixtures._Loader", loader),
        environment=environment,
        checkpoint_reader=checkpoints,
        checkpoint_writer=checkpoints,
    )


def _audit_from(
    original: ResearchExecutionAudit, semantics: object
) -> ResearchExecutionAudit:
    return ResearchExecutionAudit.create(
        semantics=cast(type(original.semantics), semantics),
        attempt_id=original.attempt_id,
        attempt_ordinal=original.attempt_ordinal,
        backtest_run_id=original.backtest_run_id,
        parent_attempt_id=original.parent_attempt_id,
        resume_from_run_id=original.resume_from_run_id,
        created_at=original.created_at,
    )


def test_factory_rejects_invalid_environment_before_storing_ports() -> None:
    _factory, _audit, reader, builder, loader = fixtures._fixture()
    checkpoints = fixtures._CheckpointStore()

    with pytest.raises(AppProcessError) as exc_info:
        FrozenAuditResearchBacktestFactory(
            strategy_reader=reader,
            runtime_builder=builder,
            artifact_loader=loader,
            environment=cast(CodeEnvironmentLock, object()),
            checkpoint_reader=checkpoints,
            checkpoint_writer=checkpoints,
        )

    assert exc_info.value.details["reason"] == "invalid_actual_code_environment_lock"


def test_factory_rejects_non_callable_stop_before_reading_audit() -> None:
    factory, audit, reader, builder, loader = fixtures._fixture()

    _assert_rejected(
        factory,
        audit,
        "invalid_external_stop_callback",
        external_should_stop=cast("Callable[[], bool]", object()),
    )

    assert reader.calls == []
    assert builder.calls == 0
    assert loader.frame_calls == []


def test_factory_rejects_non_audit_value() -> None:
    factory, _audit, *_ = fixtures._fixture()

    with pytest.raises(AppProcessError) as exc_info:
        factory.build(
            cast(ResearchExecutionAudit, object()),
            external_should_stop=fixtures._never_stop,
        )

    assert exc_info.value.details["reason"] == "invalid_research_execution_audit"


def test_factory_rejects_resume_identity_without_parent_attempt() -> None:
    factory, audit, *_ = fixtures._fixture()
    object.__setattr__(audit, "resume_from_run_id", "orphan-run")

    _assert_rejected(factory, audit, "research_resume_lineage_incomplete")


def test_factory_recomputes_and_rejects_tampered_audit_hash() -> None:
    factory, audit, *_ = fixtures._fixture()
    object.__setattr__(audit, "bundle_hash", type(audit.bundle_hash)("f" * 64))

    _assert_rejected(factory, audit, "audit_bundle_integrity_drift")


def test_factory_rejects_duplicate_executable_artifact_kind() -> None:
    factory, audit, *_ = fixtures._fixture()
    bars = next(
        item for item in audit.semantics.snapshot.inputs if item.artifact_kind == "bars"
    )
    duplicate = replace(bars, input_id="duplicate-bars.parquet")
    object.__setattr__(
        audit.semantics.snapshot,
        "inputs",
        (*audit.semantics.snapshot.inputs, duplicate),
    )

    _assert_rejected(factory, audit, "duplicate_executable_artifact_kind")


def test_factory_rejects_missing_required_executable_artifact() -> None:
    factory, audit, *_ = fixtures._fixture()
    object.__setattr__(
        audit.semantics.snapshot,
        "inputs",
        tuple(
            item
            for item in audit.semantics.snapshot.inputs
            if item.artifact_kind != "membership"
        ),
    )

    _assert_rejected(factory, audit, "required_executable_artifact_missing")


def test_factory_accepts_snapshot_without_optional_frames() -> None:
    factory, audit, _reader, _builder, _loader = fixtures._fixture()
    snapshot = replace(
        audit.semantics.snapshot,
        inputs=tuple(
            item
            for item in audit.semantics.snapshot.inputs
            if item.artifact_kind not in {"fundamental", "classification"}
        ),
    )
    backtest = replace(
        audit.semantics.backtest,
        data_feed_manifest_hash=fixtures.research_data_feed_manifest_hash(snapshot),
    )
    exact_audit = _audit_from(
        audit,
        replace(audit.semantics, snapshot=snapshot, backtest=backtest),
    )

    built = factory.build(exact_audit, external_should_stop=fixtures._never_stop)

    assert built.attestation.snapshot == snapshot


@pytest.mark.parametrize("drift", ["type", "identity"])
def test_factory_rejects_frame_loader_drift(drift: str) -> None:
    factory, audit, _reader, _builder, loader = fixtures._fixture()
    bars = next(
        item for item in audit.semantics.snapshot.inputs if item.artifact_kind == "bars"
    )
    if drift == "type":
        loader.frames[bars] = cast(VerifiedResearchFrame, object())
    else:
        loaded = loader.frames[bars]
        object.__setattr__(loaded, "input_evidence", replace(bars, input_id="other"))

    _assert_rejected(factory, audit, "artifact_loader_identity_drift")


@pytest.mark.parametrize("drift", ["type", "identity"])
def test_factory_rejects_rules_loader_drift(drift: str) -> None:
    factory, audit, _reader, _builder, loader = fixtures._fixture()
    if drift == "type":
        loader.rules = cast(VerifiedInstrumentRulesArtifact, object())
    else:
        object.__setattr__(
            loader.rules,
            "input_evidence",
            replace(loader.rules.input_evidence, input_id="other-rules"),
        )

    _assert_rejected(factory, audit, "artifact_loader_identity_drift")


def test_factory_rejects_rules_from_an_undeclared_source_snapshot() -> None:
    original = fixtures._rules()
    frame = original.frame.with_columns(
        pl.lit("future-source").alias("source_snapshot_id")
    )
    artifact_bytes = fixtures._parquet_bytes(frame)
    rules = VerifiedInstrumentRulesArtifact(
        input_evidence=ContentAddressedResearchInput(
            input_id="instrument_rules.parquet",
            artifact_kind="instrument_rules",
            content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
            schema_hash=fixtures._schema_hash(frame),
        ),
        artifact_bytes=artifact_bytes,
    )
    factory, audit, *_ = fixtures._fixture(rules=rules)

    _assert_rejected(factory, audit, "artifact_loader_identity_drift")


def test_factory_rejects_benchmark_bars_drift_at_materialization() -> None:
    factory, audit, *_ = fixtures._fixture()
    benchmark = audit.semantics.backtest.benchmark
    assert benchmark is not None
    object.__setattr__(
        benchmark,
        "bars_input",
        replace(benchmark.bars_input, input_id="other-bars.parquet"),
    )

    _assert_rejected(factory, audit, "benchmark_binding_drift")


def _synthetic_baseline_fixture() -> tuple[
    FrozenAuditResearchBacktestFactory,
    ResearchExecutionAudit,
]:
    factory, candidate_audit, *_ = fixtures._fixture()
    snapshot = candidate_audit.semantics.snapshot
    registry = default_baseline_registry()
    universe = ExactUniverseIdentity("stock-pit-universe", fixtures._sha("4"))
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=BaselineRef("stock_universe_equal_weight", 1),
            snapshot=snapshot.exact_snapshot,
            universe=universe,
            exact_strategy=None,
        )
    )
    binding = BaselineExecutorBinding(
        baseline_ref=plan.baseline_ref.identity,
        kind=plan.kind,
        descriptor_hash=plan.descriptor_hash,
        implementation_key=plan.implementation_key,
        executor_contract_version=plan.executor_contract_version,
        registry_manifest_hash=registry.manifest_hash,
        factor_versions=(),
    )
    backtest = replace(
        candidate_audit.semantics.backtest,
        rebalance_policy=fixtures.VersionedExecutionComponent(
            "research.baseline.fold_schedule",
            1,
        ),
        rebalance_frequency="fold_schedule",
        benchmark=None,
    )
    semantics = replace(
        candidate_audit.semantics,
        candidate_id="baseline-boundary",
        is_baseline=True,
        strategy=binding,
        backtest=backtest,
        membership_hash=universe.membership_hash,
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=plan,
    )
    return factory, _audit_from(candidate_audit, semantics)


def test_factory_rejects_synthetic_baseline_without_its_plan() -> None:
    factory, audit = _synthetic_baseline_fixture()
    object.__setattr__(audit.semantics, "baseline_plan", None)

    _assert_rejected(factory, audit, "synthetic_baseline_plan_missing")


def test_factory_rejects_synthetic_baseline_with_benchmark_binding() -> None:
    factory, audit = _synthetic_baseline_fixture()
    _, candidate_audit, *_ = fixtures._fixture()
    object.__setattr__(
        audit.semantics.backtest,
        "benchmark",
        candidate_audit.semantics.backtest.benchmark,
    )

    _assert_rejected(factory, audit, "synthetic_baseline_execution_drift")


def test_factory_rejects_unknown_strategy_binding_at_execution() -> None:
    factory, audit, *_ = fixtures._fixture()
    object.__setattr__(audit.semantics, "strategy", object())

    _assert_rejected(factory, audit, "invalid_strategy_execution_binding")


@pytest.mark.parametrize("drift", ["type", "identity"])
def test_factory_rejects_missing_or_wrong_strategy_record(drift: str) -> None:
    factory, audit, reader, *_ = fixtures._fixture()
    if drift == "type":
        reader.record = cast(StrategySpecRecord, object())
    else:
        reader.record = replace(reader.record, strategy_id="other-strategy")

    _assert_rejected(factory, audit, "exact_strategy_version_missing")


def test_factory_rejects_missing_strategy_version_state() -> None:
    factory, audit, reader, *_ = fixtures._fixture()
    reader.version_state = cast(str, None)

    _assert_rejected(factory, audit, "exact_strategy_version_state_missing")


def test_factory_rejects_non_researchable_candidate_version_state() -> None:
    factory, audit, reader, *_ = fixtures._fixture()
    reader.version_state = "published"

    _assert_rejected(factory, audit, "candidate_strategy_version_not_researchable")


@pytest.mark.parametrize(
    ("poison", "reason"),
    [
        pytest.param("runtime_type", "exact_strategy_runtime_unavailable"),
        pytest.param("status", "rebuilt_strategy_runtime_type_drift"),
        pytest.param("lane_missing", "rebuilt_strategy_lane_unavailable"),
        pytest.param("lane_unknown", "rebuilt_strategy_lane_unavailable"),
        pytest.param("lane_mismatch", "rebuilt_strategy_lane_drift"),
        pytest.param("identity", "rebuilt_strategy_identity_drift"),
        pytest.param("bindings", "invalid_authoritative_factor_bindings"),
        pytest.param("legacy", "rebuilt_factor_runtime_evidence_missing"),
        pytest.param("empty_factor_evidence", "compiled_factor_runtime_drift"),
        pytest.param("order_type", "rebuilt_runtime_order_type_unavailable"),
        pytest.param("frequency_missing", "rebuilt_runtime_frequency_unavailable"),
        pytest.param("frequency_unknown", "rebuilt_runtime_frequency_unavailable"),
        pytest.param("benchmark_missing", "rebuilt_runtime_benchmark_unavailable"),
        pytest.param("benchmark_none", "benchmark_binding_drift"),
        pytest.param("benchmark_type", "benchmark_binding_drift"),
    ],
)
def test_factory_rejects_runtime_port_drift(poison: str, reason: str) -> None:
    factory, audit, _reader, builder, _loader = fixtures._fixture()

    class _UnknownLane:
        value = "commodity"

    class _ExecutionWithoutFrequency:
        def __init__(self, default_order_type: OrderType) -> None:
            self.default_order_type = default_order_type

    class _LegacyWithoutBenchmark:
        def __init__(self, runtime: ResearchStrategyRuntime) -> None:
            self.execution = runtime.legacy_spec.execution
            self.signal_expressions = runtime.legacy_spec.signal_expressions
            self.signal_weights = runtime.legacy_spec.signal_weights

    def _poison_shape(runtime: ResearchStrategyRuntime) -> ResearchStrategyRuntime:
        if poison == "runtime_type":
            return cast(ResearchStrategyRuntime, object())
        if poison == "status":
            return replace(runtime, version_status="published")
        if poison == "lane_missing":
            object.__setattr__(runtime, "resolved_spec", object())
        elif poison == "lane_unknown":
            object.__setattr__(runtime.resolved_spec, "strategy_kind", _UnknownLane())
        elif poison == "lane_mismatch":
            object.__setattr__(
                runtime.resolved_spec,
                "strategy_kind",
                StrategyKind.ETF_ROTATION,
            )
        elif poison == "identity":
            object.__setattr__(runtime, "strategy_id", "other-strategy")
        elif poison == "bindings":
            object.__setattr__(runtime, "used_factor_bindings", [])
        elif poison == "legacy":
            object.__setattr__(runtime, "legacy_spec", object())
        elif poison == "empty_factor_evidence":
            object.__setattr__(
                runtime,
                "legacy_spec",
                replace(runtime.legacy_spec, signal_expressions=("ghost-factor",)),
            )
        return runtime

    def _poison_execution(runtime: ResearchStrategyRuntime) -> ResearchStrategyRuntime:
        if poison == "order_type":
            object.__setattr__(
                runtime.legacy_spec.execution,
                "default_order_type",
                object(),
            )
        elif poison == "frequency_missing":
            execution = _ExecutionWithoutFrequency(
                runtime.legacy_spec.execution.default_order_type
            )
            object.__setattr__(runtime.legacy_spec, "execution", execution)
        elif poison == "frequency_unknown":
            object.__setattr__(runtime.legacy_spec.execution, "frequency", "Q")
        elif poison == "benchmark_missing":
            object.__setattr__(runtime, "legacy_spec", _LegacyWithoutBenchmark(runtime))
        elif poison == "benchmark_none":
            object.__setattr__(runtime.legacy_spec, "benchmark", None)
        elif poison == "benchmark_type":
            object.__setattr__(runtime.legacy_spec, "benchmark", 7)
        return runtime

    def _poison(runtime: ResearchStrategyRuntime) -> ResearchStrategyRuntime:
        if poison in {
            "runtime_type",
            "status",
            "lane_missing",
            "lane_unknown",
            "lane_mismatch",
            "identity",
            "bindings",
            "legacy",
            "empty_factor_evidence",
        }:
            return _poison_shape(runtime)
        return _poison_execution(runtime)

    builder.result_transform = _poison

    _assert_rejected(factory, audit, reason)


def test_factory_rejects_runtime_pipeline_with_wrong_concrete_type() -> None:
    factory, audit, _reader, builder, _loader = fixtures._fixture()

    def _poison(runtime: ResearchStrategyRuntime) -> ResearchStrategyRuntime:
        def _return_wrong_pipeline(*, expected_execution_hash: str) -> object:
            del expected_execution_hash
            return object()

        object.__setattr__(
            runtime,
            "require_verified_pipeline",
            _return_wrong_pipeline,
        )
        return runtime

    builder.result_transform = _poison

    _assert_rejected(factory, audit, "rebuilt_strategy_runtime_type_drift")


class _StaticRuntimeBuilder:
    def __init__(self, runtime: ResearchStrategyRuntime) -> None:
        self.runtime = runtime
        self.calls = 0

    def build(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
        version_status: str,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> ResearchStrategyRuntime:
        del (
            record,
            candidate_parameters,
            snapshot_identity,
            version_status,
            evidence_sink,
        )
        self.calls += 1
        return self.runtime


def _published_stock_baseline_fixture(
    *,
    with_parameters: bool = False,
    with_published_builder: bool = True,
) -> tuple[FrozenAuditResearchBacktestFactory, ResearchExecutionAudit]:
    _factory, candidate_audit, reader, candidate_builder, loader = fixtures._fixture()
    declared = candidate_audit.semantics.strategy
    assert type(declared) is StrategyExecutionBinding
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
        exact_strategy=declared.exact_strategy,
        semantics=(("source", "published_strategy"),),
    )
    if with_parameters:
        declared = replace(
            declared,
            candidate_parameters=(
                CandidateParameter(legacy_parameter_path("top_k"), 20),
            ),
        )
    semantics = replace(
        candidate_audit.semantics,
        is_baseline=True,
        strategy=declared,
        baseline_plan=plan,
    )
    audit = _audit_from(candidate_audit, semantics)
    reader.version_state = "published"
    runtime = ResearchRuntimeBuilder(factor_registry=ResearchFactorRegistry()).build(
        record=reader.record,
        candidate_parameters=(),
        snapshot_identity=ResearchSnapshotIdentity(
            semantics.snapshot.exact_snapshot.snapshot_id,
            semantics.snapshot.exact_snapshot.manifest_hash,
        ),
        version_status="draft",
    )
    published = _StaticRuntimeBuilder(replace(runtime, version_status="published"))
    return (
        _new_factory(
            reader=reader,
            builder=candidate_builder,
            loader=loader,
            environment=semantics.environment,
            published_builder=published if with_published_builder else None,
        ),
        audit,
    )


def test_factory_rejects_candidate_parameters_on_published_baseline() -> None:
    factory, audit = _published_stock_baseline_fixture(with_parameters=True)

    _assert_rejected(factory, audit, "published_baseline_parameters_forbidden")


def test_factory_requires_a_published_baseline_runtime_builder() -> None:
    factory, audit = _published_stock_baseline_fixture(with_published_builder=False)

    _assert_rejected(factory, audit, "published_baseline_runtime_builder_unavailable")


def test_factory_rejects_non_etf_runtime_from_published_builder_port() -> None:
    factory, audit = _published_stock_baseline_fixture()

    _assert_rejected(factory, audit, "published_baseline_lane_not_supported")


def _factor_fixture() -> tuple[
    FrozenAuditResearchBacktestFactory,
    ResearchExecutionAudit,
    fixtures._Builder,
    Callable[[ResearchStrategyRuntime], ResearchStrategyRuntime],
    ResearchFactorBinding,
    CompiledDerivedExpression,
    ContentAddressedResearchInput,
]:
    factory, audit, _reader, builder, _loader = fixtures._fixture()
    declared = audit.semantics.strategy
    assert type(declared) is StrategyExecutionBinding
    artifact = ContentAddressedResearchInput(
        input_id="momentum_1m@1",
        artifact_kind="factor",
        content_hash=fixtures._sha("8"),
        schema_hash=fixtures._sha("9"),
    )
    expression = CompiledDerivedExpression(
        derived_id="momentum_1m",
        version=1,
        expr=pl.col("close"),
        analysis=Analysis(
            dependencies=("close",),
            operator_names=(),
            lookback=0,
            requires_full_day=False,
            scope="instrument",
        ),
        compile_identity=fixtures._compile_identity(),
    )
    serialized = expression.expr.meta.serialize()
    assert type(serialized) is bytes
    runtime_factor = ResearchFactorBinding(
        factor_id="momentum_1m",
        version=1,
        spec_hash=fixtures._sha("a"),
        compiled_expression_hash=hashlib.sha256(serialized).hexdigest(),
        analysis_execution_hash=analysis_execution_hash(expression.analysis),
        compile_identity=fixtures._compile_identity(),
    )
    execution_factor = ResearchFactorExecutionBinding(
        factor_id=runtime_factor.factor_id,
        version=runtime_factor.version,
        spec_hash=runtime_factor.spec_hash,
        compiled_expression_hash=runtime_factor.compiled_expression_hash,
        analysis_execution_hash=runtime_factor.analysis_execution_hash,
        compile_identity=runtime_factor.compile_identity,
        artifact=artifact,
    )
    snapshot = replace(
        audit.semantics.snapshot,
        inputs=(*audit.semantics.snapshot.inputs, artifact),
    )
    compiled = CompiledExpressions(expressions=(expression,), weights=(1.0,))
    binding = replace(
        declared,
        compiled_factor_set_hash=compiled_expressions_execution_hash(compiled),
        factor_bindings=(execution_factor,),
    )

    def _with_factor(runtime: ResearchStrategyRuntime) -> ResearchStrategyRuntime:
        return replace(
            runtime,
            legacy_spec=replace(
                runtime.legacy_spec,
                signal_expressions=("momentum_1m",),
                signal_weights=(1.0,),
            ),
            used_factor_bindings=(runtime_factor,),
            compiled_expressions=CompiledExpressions(
                expressions=(expression,),
                weights=(1.0,),
            ),
        )

    builder.result_transform = _with_factor
    exact_audit = _audit_from(
        audit,
        replace(audit.semantics, strategy=binding, snapshot=snapshot),
    )
    return (
        factory,
        exact_audit,
        builder,
        _with_factor,
        runtime_factor,
        expression,
        artifact,
    )


@pytest.mark.parametrize(
    ("poison", "reason"),
    [
        pytest.param("compiled_type", "compiled_factor_runtime_drift"),
        pytest.param("declared_ids", "compiled_factor_runtime_drift"),
        pytest.param("expressions_type", "compiled_factor_runtime_drift"),
        pytest.param("weights", "compiled_factor_weight_drift"),
        pytest.param("expression_type", "compiled_factor_runtime_drift"),
        pytest.param(
            "serialization_missing",
            "compiled_factor_serialization_unavailable",
        ),
        pytest.param("serialization_type", "compiled_factor_serialization_unavailable"),
        pytest.param("analysis", "compiled_factor_analysis_unavailable"),
        pytest.param("binding_hash", "factor_compiler_binding_drift"),
    ],
)
def test_factory_rejects_factor_runtime_port_drift(poison: str, reason: str) -> None:
    factory, audit, builder, with_factor, runtime_factor, _expression, _artifact = (
        _factor_fixture()
    )

    class _MetaReturningText:
        @staticmethod
        def serialize() -> str:
            return "not-bytes"

    class _ExpressionReturningText:
        meta = _MetaReturningText()

    def _poison(runtime: ResearchStrategyRuntime) -> ResearchStrategyRuntime:
        runtime = with_factor(runtime)
        if poison == "compiled_type":
            object.__setattr__(runtime, "compiled_expressions", object())
        elif poison == "declared_ids":
            object.__setattr__(
                runtime.legacy_spec, "signal_expressions", ["momentum_1m"]
            )
        elif poison == "expressions_type":
            assert runtime.compiled_expressions is not None
            object.__setattr__(runtime.compiled_expressions, "expressions", [])
        elif poison == "weights":
            assert runtime.compiled_expressions is not None
            object.__setattr__(runtime.compiled_expressions, "weights", (0.5,))
        elif poison == "expression_type":
            object.__setattr__(
                runtime,
                "compiled_expressions",
                CompiledExpressions(
                    expressions=(cast(CompiledDerivedExpression, object()),),
                    weights=(1.0,),
                ),
            )
        elif poison == "serialization_missing":
            assert runtime.compiled_expressions is not None
            object.__setattr__(
                runtime.compiled_expressions.expressions[0], "expr", object()
            )
        elif poison == "serialization_type":
            assert runtime.compiled_expressions is not None
            object.__setattr__(
                runtime.compiled_expressions.expressions[0],
                "expr",
                _ExpressionReturningText(),
            )
        elif poison == "analysis":
            assert runtime.compiled_expressions is not None
            object.__setattr__(
                runtime.compiled_expressions.expressions[0],
                "analysis",
                object(),
            )
        elif poison == "binding_hash":
            object.__setattr__(runtime_factor, "binding_hash", fixtures._sha("f"))
        return runtime

    builder.result_transform = _poison

    _assert_rejected(factory, audit, reason)


def test_factory_rejects_missing_frozen_artifact_for_runtime_factor() -> None:
    factory, audit, _builder, _with_factor, _factor, _expression, artifact = (
        _factor_fixture()
    )
    object.__setattr__(
        audit.semantics.snapshot,
        "inputs",
        tuple(item for item in audit.semantics.snapshot.inputs if item != artifact),
    )

    _assert_rejected(factory, audit, "factor_artifact_identity_missing")
