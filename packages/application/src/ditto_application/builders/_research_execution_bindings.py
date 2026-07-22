"""Build exact strategy, benchmark, policy, and backtest bindings."""

from __future__ import annotations

from datetime import date
from typing import cast

from ditto_strategy.alpha.parameters import CandidateParameter
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_factor_registry import ResearchFactorBinding
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppBuilderError, AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    compiled_expressions_actual_max_lookback,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    DurableLaunchEvidence,
    ExactStrategyVersionReader,
    FrozenResearchExecutionInputs,
    canonical_execution_payload_hash,
    require_evidence_list,
    require_evidence_mapping,
    require_evidence_string,
    research_execution_error,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselinePlanKind,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchFactorExecutionBinding,
    ResearchFillMode,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
    VersionedExecutionComponent,
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ResearchAssetLane,
    ResearchExecutionPolicy,
    default_etf_execution_policy,
    default_stock_execution_policy,
)

_RUNTIME_LANES = {
    "stock_selection": ResearchAssetLane.STOCK,
    "etf_rotation": ResearchAssetLane.ETF,
}
_R3_ENGINE_VERSION = "0.1.0"
_R3_INITIAL_CASH_MINOR_UNITS = 100_000_000
_R3_PARTICIPATION_RATE_PPM = 50_000
_REBALANCE_FREQUENCIES = {
    "D": "daily",
    "W": "weekly",
    "M": "monthly",
}


def read_exact_strategy_record(
    reader: ExactStrategyVersionReader,
    identity: ExactStrategyIdentity,
) -> StrategySpecRecord:
    record = reader.get_spec(identity.strategy_id, identity.version)
    if (
        type(record) is not StrategySpecRecord
        or record.strategy_id != identity.strategy_id
        or record.version != identity.version
    ):
        raise research_execution_error(
            "exact_strategy_version_missing",
            strategy_id=identity.strategy_id,
            strategy_version=identity.version,
        )
    return record


def build_research_runtime(
    *,
    builder: ResearchRuntimeBuilder | PublishedBaselineRuntimeBuilder,
    record: StrategySpecRecord,
    parameters: tuple[CandidateParameter, ...],
    snapshot: ExactResearchSnapshot,
) -> ResearchStrategyRuntime:
    try:
        return builder.build(
            record=record,
            candidate_parameters=parameters,
            snapshot_identity=ResearchSnapshotIdentity(
                snapshot.snapshot_id,
                snapshot.manifest_hash,
            ),
        )
    except (AppBuilderError, AppProcessError) as exc:
        raise research_execution_error(
            "exact_strategy_runtime_unavailable",
            strategy_id=record.strategy_id,
            strategy_version=record.version,
            error_type=type(exc).__name__,
        ) from exc


def build_strategy_execution_binding(
    runtime: ResearchStrategyRuntime,
    *,
    exact: ExactStrategyIdentity,
    snapshot: ResearchSnapshotBinding,
    parameters: tuple[CandidateParameter, ...],
) -> StrategyExecutionBinding:
    if runtime.base_spec_hash != exact.spec_hash:
        raise research_execution_error("strategy_base_spec_hash_mismatch")
    raw_bindings: object = runtime.used_factor_bindings
    if type(raw_bindings) is not tuple or any(
        type(item) is not ResearchFactorBinding
        for item in cast("tuple[object, ...]", raw_bindings)
    ):
        raise research_execution_error("invalid_authoritative_factor_bindings")
    runtime_bindings = runtime.used_factor_bindings
    artifacts = {
        item.input_id: item
        for item in snapshot.inputs
        if item.artifact_kind == "factor"
    }
    expected_artifact_ids = {
        f"{item.factor_id}@{item.version}" for item in runtime_bindings
    }
    if not expected_artifact_ids.issubset(artifacts):
        raise research_execution_error("factor_input_version_binding_drift")
    factor_bindings: list[ResearchFactorExecutionBinding] = []
    for binding in runtime_bindings:
        artifact_id = f"{binding.factor_id}@{binding.version}"
        execution_binding = ResearchFactorExecutionBinding(
            factor_id=binding.factor_id,
            version=binding.version,
            spec_hash=binding.spec_hash,
            compile_identity=binding.compile_identity,
            compiled_expression_hash=binding.compiled_expression_hash,
            analysis_execution_hash=binding.analysis_execution_hash,
            artifact=artifacts[artifact_id],
        )
        if execution_binding.binding_hash != binding.binding_hash:
            raise research_execution_error(
                "authoritative_factor_binding_hash_mismatch",
                factor_id=binding.factor_id,
                factor_version=binding.version,
            )
        factor_bindings.append(execution_binding)
    return StrategyExecutionBinding(
        exact_strategy=exact,
        resolved_spec_hash=runtime.resolved_spec_hash,
        parameter_hash=runtime.parameter_hash,
        node_registry_manifest_hash=runtime.node_registry_manifest_hash,
        pipeline_execution_hash=runtime.pipeline_execution_hash,
        factor_registry_manifest_hash=runtime.factor_registry_manifest_hash,
        compiled_factor_set_hash=compiled_expressions_execution_hash(
            runtime.compiled_expressions
        ),
        factor_bindings=tuple(factor_bindings),
        candidate_parameters=parameters,
    )


def resolve_runtime_rebalance_frequency(runtime: ResearchStrategyRuntime) -> str:
    try:
        declared = runtime.legacy_spec.execution.frequency
    except AttributeError:
        raise research_execution_error(
            "rebuilt_runtime_execution_evidence_missing"
        ) from None
    frequency = _REBALANCE_FREQUENCIES.get(declared)
    if frequency is None:
        raise research_execution_error(
            "unsupported_research_rebalance_frequency",
            declared_frequency=declared,
        )
    return frequency


def _runtime_order_type(runtime: ResearchStrategyRuntime) -> str:
    try:
        order_type = runtime.legacy_spec.execution.default_order_type.value
    except AttributeError:
        raise research_execution_error(
            "rebuilt_runtime_execution_evidence_missing"
        ) from None
    return require_evidence_string(order_type, "runtime.execution.default_order_type")


def build_runtime_benchmark(
    runtime: ResearchStrategyRuntime,
    inputs: FrozenResearchExecutionInputs,
    *,
    knowledge_date: date,
) -> ExactBenchmarkBinding | None:
    try:
        benchmark_code = runtime.legacy_spec.benchmark
    except AttributeError:
        raise research_execution_error(
            "rebuilt_runtime_execution_evidence_missing"
        ) from None
    if benchmark_code is None:
        return None
    benchmark_code = require_evidence_string(benchmark_code, "runtime.benchmark")
    bars = tuple(
        item for item in inputs.snapshot_binding.inputs if item.artifact_kind == "bars"
    )
    if len(bars) != 1:
        raise research_execution_error("benchmark_bars_evidence_missing_or_ambiguous")
    instrument_id = inputs.instrument_rules.resolve_instrument_id_at(
        benchmark_code,
        knowledge_date=knowledge_date,
    )
    mapping_input = inputs.instrument_rules.input_evidence
    identity_hash = canonical_execution_payload_hash(
        {
            "instrument_code": benchmark_code,
            "instrument_id": int(instrument_id),
            "mapping_input": mapping_input.as_payload(),
        }
    )
    return ExactBenchmarkBinding(
        instrument_id=int(instrument_id),
        instrument_identity_hash=identity_hash,
        mapping_input=mapping_input,
        bars_input=bars[0],
    )


def _versioned(key: str, version: int = 1) -> VersionedExecutionComponent:
    return VersionedExecutionComponent(key, version)


def _policy_model_evidence(
    policy: ResearchExecutionPolicy,
    instrument_rules: ContentAddressedResearchInput,
) -> tuple[PolicyModelEvidenceBinding, ...]:
    frozen = ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT
    code = ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY
    return (
        PolicyModelEvidenceBinding(
            role="fees",
            implementation=_versioned(
                policy.fees.model_key,
                policy.fees.model_version,
            ),
            evidence_source=frozen,
            inputs=(instrument_rules,),
        ),
        PolicyModelEvidenceBinding(
            role="rules",
            implementation=_versioned(
                policy.rules.contract_key,
                policy.rules.contract_version,
            ),
            evidence_source=frozen,
            inputs=(instrument_rules,),
        ),
        PolicyModelEvidenceBinding(
            role="settlement",
            implementation=_versioned(
                policy.settlement.model_key,
                policy.settlement.model_version,
            ),
            evidence_source=frozen,
            inputs=(instrument_rules,),
        ),
        PolicyModelEvidenceBinding(
            role="slippage",
            implementation=_versioned(
                policy.slippage.model_key,
                policy.slippage.model_version,
            ),
            evidence_source=code,
            inputs=(),
        ),
    )


def build_backtest_execution_binding(
    *,
    runtime: ResearchStrategyRuntime,
    inputs: FrozenResearchExecutionInputs,
    policy: ResearchExecutionPolicy,
    knowledge_date: date,
) -> BacktestExecutionConfigBinding:
    frequency = resolve_runtime_rebalance_frequency(runtime)
    order_type = _runtime_order_type(runtime)
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=_R3_INITIAL_CASH_MINOR_UNITS,
        currency="CNY",
        engine=_versioned("ditto_backtest.engine_loop"),
        engine_version=_R3_ENGINE_VERSION,
        rebalance_policy=_versioned(
            f"ditto_backtest.rebalance.{frequency}",
        ),
        rebalance_frequency=frequency,
        participation_rate_ppm=_R3_PARTICIPATION_RATE_PPM,
        fill_mode=ResearchFillMode.PARTIAL,
        fill_model=_versioned("ditto_backtest.a_share_fill.partial"),
        brokerage_model=_versioned("ditto_backtest.backtest_brokerage"),
        execution_planner=_versioned(
            f"ditto_execution.simple_execution_planner.{order_type}",
        ),
        slippage_basis_points=policy.slippage.basis_points,
        benchmark=build_runtime_benchmark(
            runtime,
            inputs,
            knowledge_date=knowledge_date,
        ),
        policy_hash=policy.canonical_hash,
        policy_model_evidence=_policy_model_evidence(
            policy,
            inputs.instrument_rules.input_evidence,
        ),
        pre_trade_checks=(
            _versioned("ditto_risk.lot_size_check"),
            _versioned("ditto_risk.buying_power_check"),
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=research_data_feed_manifest_hash(
            inputs.snapshot_binding,
        ),
    )


def build_synthetic_baseline_backtest_binding(
    plan: BaselineExecutionPlan,
    inputs: FrozenResearchExecutionInputs,
) -> BacktestExecutionConfigBinding:
    """Build stock equal-weight controls from its plan, never a hidden strategy."""
    if (
        plan.kind is not BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT
        or plan.exact_strategy is not None
        or plan.semantics
        != (
            ("allocation", "equal_weight"),
            ("membership", "point_in_time"),
            ("rebalance", "fold_schedule"),
        )
    ):
        raise research_execution_error("unsupported_synthetic_baseline_plan")
    policy = plan.execution_policy
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=_R3_INITIAL_CASH_MINOR_UNITS,
        currency="CNY",
        engine=_versioned("ditto_backtest.engine_loop"),
        engine_version=_R3_ENGINE_VERSION,
        rebalance_policy=_versioned("research.baseline.fold_schedule"),
        rebalance_frequency="fold_schedule",
        participation_rate_ppm=_R3_PARTICIPATION_RATE_PPM,
        fill_mode=ResearchFillMode.PARTIAL,
        fill_model=_versioned("ditto_backtest.a_share_fill.partial"),
        brokerage_model=_versioned("ditto_backtest.backtest_brokerage"),
        execution_planner=_versioned(
            "ditto_execution.simple_execution_planner.market",
        ),
        slippage_basis_points=policy.slippage.basis_points,
        benchmark=None,
        policy_hash=policy.canonical_hash,
        policy_model_evidence=_policy_model_evidence(
            policy,
            inputs.instrument_rules.input_evidence,
        ),
        pre_trade_checks=(
            _versioned("ditto_risk.lot_size_check"),
            _versioned("ditto_risk.buying_power_check"),
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=research_data_feed_manifest_hash(
            inputs.snapshot_binding,
        ),
    )


def resolve_persisted_runtime_lane(launch: DurableLaunchEvidence) -> ResearchAssetLane:
    runtime = require_evidence_mapping(
        launch.executor.get("runtime_validation_evidence"),
        "executor.runtime_validation_evidence",
    )
    lane_name = require_evidence_string(runtime.get("lane"), "runtime_validation.lane")
    lane = _RUNTIME_LANES.get(lane_name)
    if lane is None:
        raise research_execution_error(
            "unsupported_persisted_research_asset_lane", lane=lane_name
        )
    return lane


def _rebuilt_runtime_lane(runtime: ResearchStrategyRuntime) -> ResearchAssetLane:
    try:
        lane_name = runtime.resolved_spec.strategy_kind.value
    except AttributeError:
        raise research_execution_error("rebuilt_runtime_lane_missing") from None
    lane = _RUNTIME_LANES.get(lane_name)
    if lane is None:
        raise research_execution_error(
            "unsupported_rebuilt_research_asset_lane", lane=lane_name
        )
    return lane


def _require_factor_runtime_parity(
    runtime: ResearchStrategyRuntime,
    launch: DurableLaunchEvidence,
) -> None:
    persisted_bindings = tuple(
        require_evidence_string(item, "executor.factor_binding_hash")
        for item in require_evidence_list(
            launch.executor.get("factor_binding_hashes"),
            "executor.factor_binding_hashes",
        )
    )
    try:
        actual_bindings = tuple(
            item.binding_hash for item in runtime.used_factor_bindings
        )
        actual_registry = runtime.factor_registry_manifest_hash
    except AttributeError:
        raise research_execution_error(
            "rebuilt_factor_runtime_evidence_missing"
        ) from None
    if (
        actual_registry != launch.executor.get("factor_registry_manifest_hash")
        or actual_bindings != persisted_bindings
    ):
        raise research_execution_error("factor_runtime_validation_evidence_drift")


def _persisted_runtime_max_lookback(launch: DurableLaunchEvidence) -> int:
    persisted = require_evidence_mapping(
        launch.executor.get("runtime_validation_evidence"),
        "executor.runtime_validation_evidence",
    )
    max_lookback = persisted.get("max_lookback_sessions")
    if type(max_lookback) is not int or max_lookback < 0:
        raise research_execution_error("invalid_runtime_max_lookback_evidence")
    return max_lookback


def require_candidate_runtime_parity(
    runtime: ResearchStrategyRuntime,
    launch: DurableLaunchEvidence,
) -> ResearchAssetLane:
    persisted = require_evidence_mapping(
        launch.executor.get("runtime_validation_evidence"),
        "executor.runtime_validation_evidence",
    )
    required_datasets = tuple(
        require_evidence_string(item, "runtime_validation.required_dataset")
        for item in require_evidence_list(
            persisted.get("required_datasets"),
            "runtime_validation.required_datasets",
        )
    )
    try:
        runtime_universe = runtime.legacy_spec.universe
        runtime_datasets = tuple(sorted(runtime.legacy_spec.required_datasets))
    except AttributeError:
        raise research_execution_error("rebuilt_runtime_evidence_missing") from None
    lane = _rebuilt_runtime_lane(runtime)
    if (
        lane is not resolve_persisted_runtime_lane(launch)
        or runtime_universe
        != require_evidence_string(
            persisted.get("universe_id"), "runtime_validation.universe_id"
        )
        or runtime_datasets != required_datasets
        or runtime.node_registry_manifest_hash
        != launch.executor.get("node_registry_manifest_hash")
    ):
        raise research_execution_error("candidate_runtime_validation_evidence_drift")
    actual_max_lookback = compiled_expressions_actual_max_lookback(
        runtime.compiled_expressions
    )
    if actual_max_lookback > _persisted_runtime_max_lookback(launch):
        raise research_execution_error(
            "candidate_runtime_lookback_exceeds_validation_envelope"
        )
    _require_factor_runtime_parity(runtime, launch)
    return lane


def require_baseline_runtime_parity(
    runtime: ResearchStrategyRuntime,
    launch: DurableLaunchEvidence,
    inputs: FrozenResearchExecutionInputs,
    *,
    exact: ExactStrategyIdentity,
    expected_lane: ResearchAssetLane,
) -> None:
    persisted = require_evidence_mapping(
        launch.executor.get("baseline_runtime"),
        "executor.baseline_runtime",
    )
    persisted_factor_bindings = tuple(
        require_evidence_string(item, "baseline_runtime.factor_binding_hash")
        for item in require_evidence_list(
            persisted.get("factor_binding_hashes"),
            "baseline_runtime.factor_binding_hashes",
        )
    )
    required_datasets = tuple(
        require_evidence_string(item, "runtime_validation.required_dataset")
        for item in require_evidence_list(
            require_evidence_mapping(
                launch.executor.get("runtime_validation_evidence"),
                "executor.runtime_validation_evidence",
            ).get("required_datasets"),
            "runtime_validation.required_datasets",
        )
    )
    try:
        runtime_universe = runtime.legacy_spec.universe
        runtime_datasets = tuple(sorted(runtime.legacy_spec.required_datasets))
        runtime_factor_bindings = tuple(
            item.binding_hash for item in runtime.used_factor_bindings
        )
    except AttributeError:
        raise research_execution_error(
            "rebuilt_baseline_runtime_evidence_missing"
        ) from None
    persisted_max_lookback = persisted.get("max_lookback_sessions")
    if type(persisted_max_lookback) is not int or persisted_max_lookback < 0:
        raise research_execution_error("invalid_baseline_runtime_lookback_evidence")
    actual_max_lookback = compiled_expressions_actual_max_lookback(
        runtime.compiled_expressions
    )
    if (
        actual_max_lookback != persisted_max_lookback
        or actual_max_lookback > _persisted_runtime_max_lookback(launch)
    ):
        raise research_execution_error("baseline_runtime_lookback_drift")
    if (
        resolve_persisted_runtime_lane(launch) is not expected_lane
        or _rebuilt_runtime_lane(runtime) is not expected_lane
        or runtime_universe != inputs.universe.universe_id
        or runtime_datasets != required_datasets
    ):
        raise research_execution_error("baseline_runtime_validation_evidence_drift")
    if (
        runtime.strategy_id != exact.strategy_id
        or runtime.strategy_version != exact.version
        or runtime.base_spec_hash
        != require_evidence_string(
            persisted.get("base_spec_hash"), "baseline_runtime.base_spec_hash"
        )
        or runtime.resolved_spec_hash
        != require_evidence_string(
            persisted.get("resolved_spec_hash"),
            "baseline_runtime.resolved_spec_hash",
        )
        or runtime.parameter_hash
        != require_evidence_string(
            persisted.get("parameter_hash"), "baseline_runtime.parameter_hash"
        )
        or runtime.pipeline_execution_hash
        != require_evidence_string(
            persisted.get("pipeline_execution_hash"),
            "baseline_runtime.pipeline_execution_hash",
        )
        or compiled_expressions_execution_hash(runtime.compiled_expressions)
        != require_evidence_string(
            persisted.get("compiled_factor_set_hash"),
            "baseline_runtime.compiled_factor_set_hash",
        )
        or runtime.node_registry_manifest_hash
        != require_evidence_string(
            persisted.get("node_registry_manifest_hash"),
            "baseline_runtime.node_registry_manifest_hash",
        )
        or runtime.factor_registry_manifest_hash
        != require_evidence_string(
            persisted.get("factor_registry_manifest_hash"),
            "baseline_runtime.factor_registry_manifest_hash",
        )
        or runtime_factor_bindings != persisted_factor_bindings
    ):
        raise research_execution_error("baseline_runtime_identity_drift")


def build_synthetic_baseline_binding(
    plan: BaselineExecutionPlan,
    *,
    registry_manifest_hash: str,
    factor_versions: tuple[tuple[str, int], ...] = (),
) -> BaselineExecutorBinding:
    return BaselineExecutorBinding(
        baseline_ref=plan.baseline_ref.identity,
        kind=plan.kind,
        descriptor_hash=plan.descriptor_hash,
        implementation_key=plan.implementation_key,
        executor_contract_version=plan.executor_contract_version,
        registry_manifest_hash=registry_manifest_hash,
        factor_versions=factor_versions,
    )


def execution_policy_for_lane(lane: ResearchAssetLane) -> ResearchExecutionPolicy:
    if lane is ResearchAssetLane.STOCK:
        return default_stock_execution_policy()
    return default_etf_execution_policy()
