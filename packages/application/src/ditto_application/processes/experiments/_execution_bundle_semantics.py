"""Validation and payload assembly for immutable research execution semantics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol, cast

from ditto_backtest.context_inputs import ReplayContextInputRef

from ditto_application.processes.experiments._execution_bundle_inputs import (
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchSnapshotBinding,
    VersionedExecutionComponent,
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    execution_bundle_error as _error,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    require_date as _date_value,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    require_nonnegative_integer as _nonnegative_integer,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
)
from ditto_application.processes.experiments.execution_contracts import (
    ResearchExecutionPolicy,
)

__all__: list[str] = []


class _PayloadBinding(Protocol):
    def as_payload(self) -> Mapping[str, object]:
        """Return the canonical binding payload."""
        ...


class _FactorBindingView(Protocol):
    artifact: ContentAddressedResearchInput


class _StrategyBindingView(_PayloadBinding, Protocol):
    exact_strategy: object
    factor_bindings: tuple[object, ...]


class _BenchmarkBindingView(Protocol):
    mapping_input: ContentAddressedResearchInput
    bars_input: ContentAddressedResearchInput


class _BacktestBindingView(_PayloadBinding, Protocol):
    policy_hash: str
    policy_model_evidence: tuple[PolicyModelEvidenceBinding, ...]
    slippage_basis_points: int
    benchmark: object | None
    data_feed_manifest_hash: str


class _SemanticsView(Protocol):
    experiment_id: str
    candidate_id: str
    fold_id: str
    fold_role: str
    is_baseline: bool
    plan_hash: str
    launch_spec_hash: str
    fold_spec_hash: str
    strategy: object
    backtest: object
    snapshot: ResearchSnapshotBinding
    membership_hash: str
    membership_projection_hash: str
    train_start: date | None
    train_end: date | None
    test_start: date
    test_end: date
    purge_sessions: int
    embargo_sessions: int
    seed: int
    knowledge_lag_days: int
    execution_delay_sessions: int
    baseline_registry_manifest_hash: str
    baseline_plan: BaselineExecutionPlan | None
    policy: ResearchExecutionPolicy
    environment: CodeEnvironmentLock
    context_input_refs: tuple[ReplayContextInputRef, ...]


def validate_research_execution_semantics(
    semantics: object,
    *,
    strategy_binding_type: type[object],
    backtest_binding_type: type[object],
) -> None:
    """Validate all cross-binding, window, control, and baseline invariants."""
    view = cast("_SemanticsView", semantics)
    _validate_bindings(
        view,
        strategy_binding_type=strategy_binding_type,
        backtest_binding_type=backtest_binding_type,
    )
    _validate_windows(view)
    _validate_controls(view)
    _validate_baseline(view, strategy_binding_type=strategy_binding_type)


def _validate_bindings(
    semantics: _SemanticsView,
    *,
    strategy_binding_type: type[object],
    backtest_binding_type: type[object],
) -> None:
    if type(semantics.strategy) not in {
        strategy_binding_type,
        BaselineExecutorBinding,
    }:
        raise _error("strategy binding is invalid", "invalid_strategy_binding")
    if (
        type(semantics.strategy) is BaselineExecutorBinding
        and not semantics.is_baseline
    ):
        raise _error(
            "synthetic baseline binding requires a baseline candidate",
            "unexpected_baseline_executor",
        )
    if type(semantics.backtest) is not backtest_binding_type:
        raise _error(
            "backtest execution binding is invalid",
            "invalid_backtest_execution_binding",
        )
    if type(semantics.snapshot) is not ResearchSnapshotBinding:
        raise _error("snapshot binding is invalid", "invalid_snapshot_binding")
    if type(semantics.policy) is not ResearchExecutionPolicy:
        raise _error(
            "execution policy binding is invalid",
            "invalid_policy_binding",
        )
    if type(semantics.environment) is not CodeEnvironmentLock:
        raise _error("environment lock is invalid", "invalid_environment_lock")
    backtest = cast("_BacktestBindingView", semantics.backtest)
    if backtest.policy_hash != semantics.policy.canonical_hash:
        raise _error(
            "backtest policy hash drifted from execution semantics",
            "backtest_policy_hash_drift",
        )
    _validate_policy_model_parity(semantics, backtest)
    _validate_backtest_inputs(semantics, backtest)
    _validate_factor_inputs(
        semantics,
        strategy_binding_type=strategy_binding_type,
    )
    _validate_data_feed_manifest(semantics, backtest)


def _validate_policy_model_parity(
    semantics: _SemanticsView,
    backtest: _BacktestBindingView,
) -> None:
    expected = {
        "fees": VersionedExecutionComponent(
            semantics.policy.fees.model_key,
            semantics.policy.fees.model_version,
        ),
        "rules": VersionedExecutionComponent(
            semantics.policy.rules.contract_key,
            semantics.policy.rules.contract_version,
        ),
        "settlement": VersionedExecutionComponent(
            semantics.policy.settlement.model_key,
            semantics.policy.settlement.model_version,
        ),
        "slippage": VersionedExecutionComponent(
            semantics.policy.slippage.model_key,
            semantics.policy.slippage.model_version,
        ),
    }
    actual = {
        item.role: (item.implementation, item.evidence_source)
        for item in backtest.policy_model_evidence
    }
    expected_sources = {
        "fees": ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
        "rules": ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
        "settlement": ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
        "slippage": ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY,
    }
    if (
        actual
        != {
            role: (component, expected_sources[role])
            for role, component in expected.items()
        }
        or backtest.slippage_basis_points != semantics.policy.slippage.basis_points
    ):
        raise _error(
            "backtest model implementations drifted from execution policy",
            "backtest_policy_model_drift",
        )


def _validate_backtest_inputs(
    semantics: _SemanticsView,
    backtest: _BacktestBindingView,
) -> None:
    snapshot_inputs = {
        (item.input_id, item.content_hash, item.schema_hash)
        for item in semantics.snapshot.inputs
    }
    required_inputs = {
        (item.input_id, item.content_hash, item.schema_hash)
        for model in backtest.policy_model_evidence
        for item in model.inputs
    }
    if backtest.benchmark is not None:
        benchmark = cast("_BenchmarkBindingView", backtest.benchmark)
        bars = benchmark.bars_input
        required_inputs.add((bars.input_id, bars.content_hash, bars.schema_hash))
        mapping = benchmark.mapping_input
        required_inputs.add(
            (mapping.input_id, mapping.content_hash, mapping.schema_hash)
        )
    if not required_inputs.issubset(snapshot_inputs):
        raise _error(
            "backtest model evidence is absent from the frozen snapshot",
            "backtest_input_evidence_drift",
        )


def _validate_factor_inputs(
    semantics: _SemanticsView,
    *,
    strategy_binding_type: type[object],
) -> None:
    snapshot_factors = {
        (item.input_id, item.content_hash, item.schema_hash)
        for item in semantics.snapshot.inputs
        if item.artifact_kind == "factor"
    }
    required_factors: set[tuple[str, str, str]]
    if type(semantics.strategy) is strategy_binding_type:
        strategy = cast("_StrategyBindingView", semantics.strategy)
        required_factors = {
            (
                factor.artifact.input_id,
                factor.artifact.content_hash,
                factor.artifact.schema_hash,
            )
            for item in strategy.factor_bindings
            for factor in (cast("_FactorBindingView", item),)
        }
    else:
        required_factors = set()
    if not required_factors.issubset(snapshot_factors):
        raise _error(
            "factor artifacts drifted from authoritative runtime bindings",
            "factor_input_binding_drift",
        )


def _validate_data_feed_manifest(
    semantics: _SemanticsView,
    backtest: _BacktestBindingView,
) -> None:
    expected = research_data_feed_manifest_hash(semantics.snapshot)
    if backtest.data_feed_manifest_hash != expected:
        raise _error(
            "declared data-feed manifest drifted from the frozen snapshot",
            "data_feed_manifest_hash_drift",
            expected_manifest_hash=expected,
            actual_manifest_hash=backtest.data_feed_manifest_hash,
        )


def _validate_controls(semantics: _SemanticsView) -> None:
    for field_name in (
        "purge_sessions",
        "embargo_sessions",
        "seed",
        "knowledge_lag_days",
        "execution_delay_sessions",
    ):
        _nonnegative_integer(getattr(semantics, field_name), field_name)


def _validate_baseline(
    semantics: _SemanticsView,
    *,
    strategy_binding_type: type[object],
) -> None:
    if semantics.is_baseline and semantics.baseline_plan is None:
        raise _error(
            "baseline candidates require a frozen execution plan",
            "baseline_plan_required",
        )
    if not semantics.is_baseline and semantics.baseline_plan is not None:
        raise _error(
            "non-baseline candidates cannot carry a baseline plan",
            "unexpected_baseline_plan",
        )
    if semantics.baseline_plan is None:
        return
    if type(semantics.baseline_plan) is not BaselineExecutionPlan:
        raise _error("baseline plan has the wrong type", "invalid_baseline_plan")
    _validate_baseline_plan_identity(semantics, semantics.baseline_plan)
    _validate_baseline_strategy(
        semantics,
        semantics.baseline_plan,
        strategy_binding_type=strategy_binding_type,
    )


def _validate_baseline_plan_identity(
    semantics: _SemanticsView,
    plan: BaselineExecutionPlan,
) -> None:
    if (
        plan.snapshot != semantics.snapshot.exact_snapshot
        or plan.universe.membership_hash != semantics.membership_hash
        or plan.execution_policy != semantics.policy
    ):
        raise _error(
            "baseline plan drifted from execution semantics",
            "baseline_plan_identity_drift",
        )


def _validate_baseline_strategy(
    semantics: _SemanticsView,
    plan: BaselineExecutionPlan,
    *,
    strategy_binding_type: type[object],
) -> None:
    if plan.exact_strategy is None:
        if type(semantics.strategy) is not BaselineExecutorBinding:
            raise _error(
                "synthetic baseline plan requires its registered executor",
                "baseline_strategy_binding_kind_drift",
            )
        strategy = semantics.strategy
        if (
            strategy.baseline_ref != plan.baseline_ref.identity
            or strategy.kind is not plan.kind
            or strategy.descriptor_hash != plan.descriptor_hash
            or strategy.implementation_key != plan.implementation_key
            or strategy.executor_contract_version != plan.executor_contract_version
            or strategy.registry_manifest_hash
            != semantics.baseline_registry_manifest_hash
        ):
            raise _error(
                "baseline executor binding drifted from the frozen plan",
                "baseline_executor_identity_drift",
            )
        return
    if type(semantics.strategy) is not strategy_binding_type:
        raise _error(
            "catalog baseline plan requires its exact strategy binding",
            "baseline_strategy_binding_kind_drift",
        )
    strategy = cast("_StrategyBindingView", semantics.strategy)
    if strategy.exact_strategy != plan.exact_strategy:
        raise _error(
            "baseline strategy binding drifted from the frozen plan",
            "baseline_exact_strategy_drift",
        )


def _validate_windows(semantics: _SemanticsView) -> None:
    if (semantics.train_start is None) is not (semantics.train_end is None):
        raise _error(
            "train window boundaries must be supplied together",
            "invalid_execution_window",
        )
    if semantics.train_start is not None and semantics.train_end is not None:
        train_start = _date_value(semantics.train_start, "train_start")
        train_end = _date_value(semantics.train_end, "train_end")
        if train_start > train_end:
            raise _error("train window is inverted", "invalid_execution_window")
    test_start = _date_value(semantics.test_start, "test_start")
    test_end = _date_value(semantics.test_end, "test_end")
    if test_start > test_end:
        raise _error("test window is inverted", "invalid_execution_window")


def build_research_execution_payload(
    semantics: object,
    *,
    strategy_binding_type: type[object],
) -> Mapping[str, object]:
    """Build the stable schema-v1 payload after semantic validation succeeds."""
    view = cast("_SemanticsView", semantics)
    strategy = cast("_PayloadBinding", view.strategy)
    backtest = cast("_PayloadBinding", view.backtest)
    strategy_kind = (
        "catalog_strategy"
        if type(view.strategy) is strategy_binding_type
        else "baseline_executor"
    )
    return {
        "schema_version": 1,
        "experiment_id": view.experiment_id,
        "candidate_id": view.candidate_id,
        "fold_id": view.fold_id,
        "fold_role": view.fold_role,
        "is_baseline": view.is_baseline,
        "plan_hash": view.plan_hash,
        "launch_spec_hash": view.launch_spec_hash,
        "fold_spec_hash": view.fold_spec_hash,
        "strategy": {
            "kind": strategy_kind,
            "binding": strategy.as_payload(),
        },
        "backtest": backtest.as_payload(),
        "snapshot": view.snapshot.as_payload(),
        "membership": {
            "content_hash": view.membership_hash,
            "projection_hash": view.membership_projection_hash,
        },
        "window": {
            "train": None
            if view.train_start is None
            else {
                "start": view.train_start.isoformat(),
                "end": cast("date", view.train_end).isoformat(),
            },
            "test": {
                "start": view.test_start.isoformat(),
                "end": view.test_end.isoformat(),
            },
            "purge_sessions": view.purge_sessions,
            "embargo_sessions": view.embargo_sessions,
        },
        "controls": {
            "seed": view.seed,
            "knowledge_lag_days": view.knowledge_lag_days,
            "execution_delay_sessions": view.execution_delay_sessions,
        },
        "baseline": {
            "registry_manifest_hash": view.baseline_registry_manifest_hash,
            "plan_hash": (
                None
                if view.baseline_plan is None
                else view.baseline_plan.canonical_hash
            ),
            "runner_key": (
                None
                if view.baseline_plan is None
                else view.baseline_plan.baseline_ref.identity
            ),
        },
        "policy": {
            "identity": view.policy.identity,
            "content_hash": view.policy.canonical_hash,
            "semantics": view.policy.canonical_payload(),
        },
        "environment": view.environment.as_payload(),
        "context_input_refs": [
            {
                "context_kind": item.context_kind.value,
                "context_id": item.context_id,
                "content_hash": item.content_hash,
                "as_of": item.as_of,
                "knowledge_cutoff": item.knowledge_cutoff,
                "publication_cutoff": item.publication_cutoff,
                "source_snapshot_ids": list(item.source_snapshot_ids),
            }
            for item in view.context_input_refs
        ],
    }
