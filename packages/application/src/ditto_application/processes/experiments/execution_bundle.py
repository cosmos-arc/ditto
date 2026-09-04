"""Canonical execution semantics and per-attempt audit bundles for R3 research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast

import orjson
from ditto_analysis.experiments import ContentHash, canonical_payload
from ditto_backtest.context_inputs import (
    ReplayContextInputRef,
    normalize_context_input_refs,
)
from ditto_features.expression.contracts import CompileIdentity
from ditto_strategy.alpha.parameters import CandidateParameter

from ditto_application.processes.experiments._execution_bundle_inputs import (
    EXECUTABLE_FOLD_ROLES as _FOLD_ROLES,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    PARTS_PER_MILLION as _PARTS_PER_MILLION,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    POLICY_MODEL_ROLES as _POLICY_MODEL_ROLES,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchFillMode,
    ResearchSnapshotBinding,
    VersionedExecutionComponent,
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    execution_bundle_error as _error,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    require_content_hash as _hash,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    require_execution_identity as _identity,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    require_positive_integer as _positive_integer,
)
from ditto_application.processes.experiments._execution_bundle_semantics import (
    build_research_execution_payload,
    validate_research_execution_semantics,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactStrategyIdentity,
    ResearchExecutionPolicy,
)

__all__ = [
    "BacktestExecutionConfigBinding",
    "BaselineExecutorBinding",
    "CodeEnvironmentLock",
    "ContentAddressedResearchInput",
    "ExactBenchmarkBinding",
    "ExecutionEvidenceSource",
    "PolicyModelEvidenceBinding",
    "ResearchExecutionAudit",
    "ResearchExecutionSemantics",
    "ResearchFactorExecutionBinding",
    "ResearchFillMode",
    "ResearchSnapshotBinding",
    "StrategyExecutionBinding",
    "VersionedExecutionComponent",
    "research_data_feed_manifest_hash",
]

_FACTOR_IDENTITY_PART_COUNT = 2
_COMPILE_HASH_FIELDS = (
    "compile_input_hash",
    "operator_fingerprint",
    "compiler_fingerprint",
    "cache_key",
)
_COMPILE_IDENTITY_FIELDS = (
    "engine_codegen_version",
    "analysis_version",
    "polars_version",
    "expr_serialization_format",
)


def _compile_operator_versions(raw_value: object) -> tuple[tuple[str, str], ...]:
    """Validate the exact ordered operator identities in one compile record."""
    if type(raw_value) is not tuple:
        raise _error(
            "factor operator versions must be an explicit tuple",
            "invalid_factor_compile_identity",
        )
    operators: list[tuple[str, str]] = []
    for raw_operator in cast("tuple[object, ...]", raw_value):
        if type(raw_operator) is not tuple:
            raise _error(
                "factor operator versions must be exact identity/version pairs",
                "invalid_factor_compile_identity",
            )
        operator_parts = cast("tuple[object, ...]", raw_operator)
        if len(operator_parts) != _FACTOR_IDENTITY_PART_COUNT:
            raise _error(
                "factor operator versions must be exact identity/version pairs",
                "invalid_factor_compile_identity",
            )
        name, version = operator_parts
        operators.append(
            (
                _identity(name, "factor.operator_name"),
                _identity(version, "factor.operator_version"),
            )
        )
    result = tuple(operators)
    if len({name for name, _ in result}) != len(result) or result != tuple(
        sorted(result, key=lambda item: item[0])
    ):
        raise _error(
            "factor operator versions must be unique and canonical",
            "invalid_factor_compile_identity",
        )
    return result


def _compile_identity_payload(identity: object) -> Mapping[str, object]:
    """Validate and expose every compiler/cache identity field."""
    if type(identity) is not CompileIdentity:
        raise _error(
            "factor binding requires an exact compile identity",
            "invalid_factor_compile_identity",
        )
    typed = identity
    for field_name in _COMPILE_HASH_FIELDS:
        _hash(getattr(typed, field_name), f"factor.{field_name}")
    for field_name in _COMPILE_IDENTITY_FIELDS:
        _identity(getattr(typed, field_name), f"factor.{field_name}")

    operators = _compile_operator_versions(typed.operator_versions)

    raw_flags: object = typed.global_compile_flags
    if type(raw_flags) is not tuple:
        raise _error(
            "factor compile flags must be an explicit tuple",
            "invalid_factor_compile_identity",
        )
    flags = tuple(
        _identity(flag, "factor.global_compile_flag")
        for flag in cast("tuple[object, ...]", raw_flags)
    )
    if len(set(flags)) != len(flags):
        raise _error(
            "factor compile flags must be unique",
            "invalid_factor_compile_identity",
        )
    return {
        "analysis_version": typed.analysis_version,
        "cache_key": typed.cache_key,
        "compile_input_hash": typed.compile_input_hash,
        "compiler_fingerprint": typed.compiler_fingerprint,
        "engine_codegen_version": typed.engine_codegen_version,
        "expr_serialization_format": typed.expr_serialization_format,
        "global_compile_flags": list(flags),
        "operator_fingerprint": typed.operator_fingerprint,
        "operator_versions": [list(item) for item in operators],
        "polars_version": typed.polars_version,
    }


@dataclass(frozen=True, slots=True)
class ExactBenchmarkBinding:
    """Exact internal benchmark identity and its frozen bar evidence."""

    instrument_id: int
    instrument_identity_hash: str
    mapping_input: ContentAddressedResearchInput
    bars_input: ContentAddressedResearchInput
    canonical_hash: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        """Reject ticker lookup and path-only benchmark evidence."""
        _positive_integer(self.instrument_id, "benchmark_instrument_id")
        _hash(self.instrument_identity_hash, "benchmark_instrument_identity_hash")
        if (
            type(self.mapping_input) is not ContentAddressedResearchInput
            or self.mapping_input.artifact_kind != "instrument_rules"
        ):
            raise _error(
                "benchmark mapping requires exact instrument-rules evidence",
                "invalid_benchmark_binding",
            )
        if type(self.bars_input) is not ContentAddressedResearchInput:
            raise _error(
                "benchmark bars require exact content-addressed evidence",
                "invalid_benchmark_binding",
            )
        if self.bars_input.artifact_kind != "bars":
            raise _error(
                "benchmark evidence must identify frozen bars",
                "invalid_benchmark_binding",
            )
        object.__setattr__(
            self,
            "canonical_hash",
            canonical_payload(self.as_payload()).content_hash,
        )

    def as_payload(self) -> Mapping[str, object]:
        """Return benchmark identity without any moving ticker lookup."""
        return {
            "instrument_id": self.instrument_id,
            "instrument_identity_hash": self.instrument_identity_hash,
            "mapping_input": self.mapping_input.as_payload(),
            "bars_input": self.bars_input.as_payload(),
        }

    @property
    def mapping_artifact_hash(self) -> str:
        """Expose the mapping content hash as a derived compatibility view."""
        return self.mapping_input.content_hash


@dataclass(frozen=True, slots=True)
class BacktestExecutionConfigBinding:
    """Every BacktestService control that can change research results."""

    initial_cash_minor_units: int
    currency: str
    engine: VersionedExecutionComponent
    engine_version: str
    rebalance_policy: VersionedExecutionComponent
    rebalance_frequency: str
    participation_rate_ppm: int
    fill_mode: ResearchFillMode
    fill_model: VersionedExecutionComponent
    brokerage_model: VersionedExecutionComponent
    execution_planner: VersionedExecutionComponent
    slippage_basis_points: int
    benchmark: ExactBenchmarkBinding | None
    policy_hash: str
    policy_model_evidence: tuple[PolicyModelEvidenceBinding, ...]
    pre_trade_checks: tuple[VersionedExecutionComponent, ...]
    post_trade_guard: VersionedExecutionComponent | None
    data_feed_manifest_hash: str
    policy_model_evidence_hash: ContentHash = field(init=False)
    canonical_hash: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        """Reject implicit models, floating controls, and moving evidence."""
        if (
            type(self.initial_cash_minor_units) is not int
            or self.initial_cash_minor_units <= 0
        ):
            raise _error(
                "initial cash must be positive integer minor units",
                "invalid_initial_cash",
            )
        currency = _identity(self.currency, "currency")
        if currency != currency.upper():
            raise _error("currency must be uppercase", "invalid_currency")
        for field_name in (
            "engine",
            "rebalance_policy",
            "fill_model",
            "brokerage_model",
            "execution_planner",
        ):
            if type(getattr(self, field_name)) is not VersionedExecutionComponent:
                raise _error(
                    f"{field_name} must bind a versioned implementation",
                    "invalid_backtest_component",
                    field=field_name,
                )
        _identity(self.engine_version, "engine_version")
        _identity(self.rebalance_frequency, "rebalance_frequency")
        if (
            type(self.participation_rate_ppm) is not int
            or not 0 <= self.participation_rate_ppm <= _PARTS_PER_MILLION
        ):
            raise _error(
                "participation rate must be integer parts per million",
                "invalid_participation_rate",
            )
        if type(self.fill_mode) is not ResearchFillMode:
            raise _error("fill mode must be typed", "invalid_fill_mode")
        if (
            type(self.slippage_basis_points) is not int
            or self.slippage_basis_points < 0
        ):
            raise _error(
                "slippage basis points must be a non-negative integer",
                "invalid_slippage_control",
            )
        if (
            self.benchmark is not None
            and type(self.benchmark) is not ExactBenchmarkBinding
        ):
            raise _error(
                "benchmark must use exact frozen identity",
                "invalid_benchmark_binding",
            )
        _hash(self.policy_hash, "policy_hash")
        _hash(self.data_feed_manifest_hash, "data_feed_manifest_hash")
        models = self._validate_models()
        checks = self._validate_checks()
        if (
            self.post_trade_guard is not None
            and type(self.post_trade_guard) is not VersionedExecutionComponent
        ):
            raise _error(
                "post-trade guard must bind a versioned implementation",
                "invalid_backtest_component",
                field="post_trade_guard",
            )
        object.__setattr__(self, "policy_model_evidence", models)
        object.__setattr__(self, "pre_trade_checks", checks)
        evidence = canonical_payload(
            {
                "policy_hash": self.policy_hash,
                "models": [item.as_payload() for item in models],
            }
        ).content_hash
        object.__setattr__(self, "policy_model_evidence_hash", evidence)
        object.__setattr__(
            self,
            "canonical_hash",
            canonical_payload(self.as_payload()).content_hash,
        )

    def _validate_models(self) -> tuple[PolicyModelEvidenceBinding, ...]:
        raw_models_value: object = self.policy_model_evidence
        if type(raw_models_value) is not tuple:
            raise _error(
                "policy model evidence must be an explicit tuple",
                "invalid_policy_model_binding",
            )
        raw_models = cast("tuple[object, ...]", raw_models_value)
        if any(type(item) is not PolicyModelEvidenceBinding for item in raw_models):
            raise _error(
                "policy model evidence has the wrong type",
                "invalid_policy_model_binding",
            )
        models = tuple(
            sorted(
                cast("tuple[PolicyModelEvidenceBinding, ...]", raw_models),
                key=lambda item: item.role.encode(),
            )
        )
        roles = tuple(item.role for item in models)
        if len(set(roles)) != len(roles):
            raise _error(
                "executable policy model roles must be unique",
                "duplicate_policy_model_evidence",
            )
        if len(models) != len(_POLICY_MODEL_ROLES) or frozenset(roles) != (
            _POLICY_MODEL_ROLES
        ):
            raise _error(
                "every executable policy model must be bound exactly once",
                "missing_policy_model_evidence",
            )
        return models

    def _validate_checks(self) -> tuple[VersionedExecutionComponent, ...]:
        raw_checks_value: object = self.pre_trade_checks
        if type(raw_checks_value) is not tuple or not raw_checks_value:
            raise _error(
                "pre-trade checks must be an ordered non-empty tuple",
                "invalid_pre_trade_checks",
            )
        raw_checks = cast("tuple[object, ...]", raw_checks_value)
        if any(type(item) is not VersionedExecutionComponent for item in raw_checks):
            raise _error(
                "pre-trade checks must bind versioned implementations",
                "invalid_pre_trade_checks",
            )
        checks = cast("tuple[VersionedExecutionComponent, ...]", raw_checks)
        identities = tuple(
            (item.implementation_key, item.contract_version) for item in checks
        )
        if len(set(identities)) != len(identities):
            raise _error(
                "pre-trade check identities must be unique",
                "invalid_pre_trade_checks",
            )
        return checks

    def as_payload(self) -> Mapping[str, object]:
        """Return the exact BacktestService construction evidence."""
        return {
            "initial_cash": {
                "minor_units": self.initial_cash_minor_units,
                "currency": self.currency,
            },
            "engine": self.engine.as_payload(),
            "engine_version": self.engine_version,
            "rebalance_policy": self.rebalance_policy.as_payload(),
            "rebalance_frequency": self.rebalance_frequency,
            "participation_rate_ppm": self.participation_rate_ppm,
            "fill_mode": self.fill_mode.value,
            "fill_model": self.fill_model.as_payload(),
            "brokerage_model": self.brokerage_model.as_payload(),
            "execution_planner": self.execution_planner.as_payload(),
            "slippage_basis_points": self.slippage_basis_points,
            "benchmark": (
                None if self.benchmark is None else self.benchmark.as_payload()
            ),
            "policy_hash": self.policy_hash,
            "policy_model_evidence": [
                item.as_payload() for item in self.policy_model_evidence
            ],
            "policy_model_evidence_hash": str(self.policy_model_evidence_hash),
            "pre_trade_checks": [item.as_payload() for item in self.pre_trade_checks],
            "post_trade_guard": (
                None
                if self.post_trade_guard is None
                else self.post_trade_guard.as_payload()
            ),
            "data_feed_manifest_hash": self.data_feed_manifest_hash,
        }


@dataclass(frozen=True, slots=True)
class ResearchFactorExecutionBinding:
    """One actually compiled factor joined to its frozen data artifact."""

    factor_id: str
    version: int
    spec_hash: str
    compile_identity: CompileIdentity
    compiled_expression_hash: str
    analysis_execution_hash: str
    artifact: ContentAddressedResearchInput
    binding_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Reject self-reported versions without compiler and artifact evidence."""
        factor_id = _identity(self.factor_id, "factor_id")
        version = _positive_integer(self.version, "factor_version")
        spec_hash = _hash(self.spec_hash, "factor_spec_hash")
        expression_hash = _hash(
            self.compiled_expression_hash,
            "factor_compiled_expression_hash",
        )
        analysis_hash = _hash(
            self.analysis_execution_hash,
            "factor_analysis_execution_hash",
        )
        compile_identity = _compile_identity_payload(self.compile_identity)
        if type(self.artifact) is not ContentAddressedResearchInput:
            raise _error(
                "factor execution requires an exact content-addressed artifact",
                "invalid_factor_artifact_binding",
                factor_id=factor_id,
            )
        if (
            self.artifact.artifact_kind != "factor"
            or self.artifact.input_id != f"{factor_id}@{version}"
        ):
            raise _error(
                "factor artifact identity drifted from its compiler binding",
                "invalid_factor_artifact_binding",
                factor_id=factor_id,
                factor_version=version,
            )
        object.__setattr__(
            self,
            "binding_hash",
            str(
                canonical_payload(
                    {
                        "analysis_execution_hash": analysis_hash,
                        "compile_identity": compile_identity,
                        "compiled_expression_hash": expression_hash,
                        "factor_id": factor_id,
                        "spec_hash": spec_hash,
                        "version": version,
                    }
                ).content_hash
            ),
        )

    def as_payload(self) -> Mapping[str, object]:
        """Return the exact registry, compiler/cache, and artifact binding."""
        return {
            "factor_id": self.factor_id,
            "version": self.version,
            "spec_hash": self.spec_hash,
            "compile_identity": _compile_identity_payload(self.compile_identity),
            "compiled_expression_hash": self.compiled_expression_hash,
            "analysis_execution_hash": self.analysis_execution_hash,
            "binding_hash": self.binding_hash,
            "artifact": self.artifact.as_payload(),
        }


@dataclass(frozen=True, slots=True)
class StrategyExecutionBinding:
    """Exact version, resolved candidate, registry, and factor identities."""

    exact_strategy: ExactStrategyIdentity
    resolved_spec_hash: str
    parameter_hash: str
    node_registry_manifest_hash: str
    pipeline_execution_hash: str
    factor_registry_manifest_hash: str
    compiled_factor_set_hash: str
    factor_bindings: tuple[ResearchFactorExecutionBinding, ...]
    candidate_parameters: tuple[CandidateParameter, ...] = ()

    def __post_init__(self) -> None:
        """Freeze factor versions and reject any moving version identity."""
        if type(self.exact_strategy) is not ExactStrategyIdentity:
            raise _error(
                "strategy binding requires an exact strategy identity",
                "invalid_strategy_binding",
            )
        for field_name in (
            "resolved_spec_hash",
            "parameter_hash",
            "node_registry_manifest_hash",
            "pipeline_execution_hash",
            "factor_registry_manifest_hash",
            "compiled_factor_set_hash",
        ):
            _hash(getattr(self, field_name), field_name)
        raw_bindings: object = self.factor_bindings
        if type(raw_bindings) is not tuple or any(
            type(item) is not ResearchFactorExecutionBinding
            for item in cast("tuple[object, ...]", raw_bindings)
        ):
            raise _error(
                "factor bindings must be an explicit tuple of exact bindings",
                "invalid_factor_identity",
            )
        bindings = self.factor_bindings
        if len({item.factor_id for item in bindings}) != len(bindings):
            raise _error(
                "factor identities must be unique",
                "duplicate_factor_identity",
            )
        raw_parameters: object = self.candidate_parameters
        if type(raw_parameters) is not tuple or any(
            type(item) is not CandidateParameter
            for item in cast("tuple[object, ...]", raw_parameters)
        ):
            raise _error(
                "candidate parameters must be exact typed bindings",
                "invalid_candidate_parameter_binding",
            )
        parameters = self.candidate_parameters
        if len({item.path for item in parameters}) != len(parameters) or tuple(
            item.path for item in parameters
        ) != tuple(sorted((item.path for item in parameters), key=str.encode)):
            raise _error(
                "candidate parameters must be unique and canonically ordered",
                "invalid_candidate_parameter_binding",
            )

    @property
    def factor_versions(self) -> tuple[tuple[str, int], ...]:
        """Expose versions only as a projection of authoritative bindings."""
        return tuple((item.factor_id, item.version) for item in self.factor_bindings)

    def as_payload(self) -> Mapping[str, object]:
        """Return exact strategy execution identity."""
        return {
            "strategy_id": self.exact_strategy.strategy_id,
            "strategy_version": self.exact_strategy.version,
            "base_spec_hash": self.exact_strategy.spec_hash,
            "resolved_spec_hash": self.resolved_spec_hash,
            "parameter_hash": self.parameter_hash,
            "node_registry_manifest_hash": self.node_registry_manifest_hash,
            "pipeline_execution_hash": self.pipeline_execution_hash,
            "factor_registry_manifest_hash": self.factor_registry_manifest_hash,
            "compiled_factor_set_hash": self.compiled_factor_set_hash,
            "factor_bindings": [item.as_payload() for item in self.factor_bindings],
            "candidate_parameters": [
                {
                    "path": item.path,
                    "type": (
                        "bool"
                        if type(item.value) is bool
                        else "int"
                        if type(item.value) is int
                        else "float"
                        if type(item.value) is float
                        else "string"
                    ),
                    "value": item.value,
                }
                for item in self.candidate_parameters
            ],
        }


@dataclass(frozen=True, slots=True)
class ResearchExecutionSemantics:
    """All result-determining values frozen before atomic fold claim."""

    experiment_id: str
    candidate_id: str
    fold_id: str
    fold_role: str
    is_baseline: bool
    plan_hash: str
    launch_spec_hash: str
    fold_spec_hash: str
    strategy: StrategyExecutionBinding | BaselineExecutorBinding
    backtest: BacktestExecutionConfigBinding
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
    context_input_refs: tuple[ReplayContextInputRef, ...] = ()
    canonical_payload: bytes = field(init=False, repr=False)
    reproduction_fingerprint: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        """Validate and content address the complete research run semantics."""
        for field_name in ("experiment_id", "candidate_id", "fold_id"):
            _identity(getattr(self, field_name), field_name)
        if self.fold_role not in _FOLD_ROLES:
            raise _error("fold role is not executable", "invalid_fold_role")
        if type(self.is_baseline) is not bool:
            raise _error("is_baseline must be bool", "invalid_baseline_marker")
        for field_name in (
            "plan_hash",
            "launch_spec_hash",
            "fold_spec_hash",
            "membership_hash",
            "membership_projection_hash",
            "baseline_registry_manifest_hash",
        ):
            _hash(getattr(self, field_name), field_name)
        validate_research_execution_semantics(
            self,
            strategy_binding_type=StrategyExecutionBinding,
            backtest_binding_type=BacktestExecutionConfigBinding,
        )
        try:
            normalized_context_inputs = normalize_context_input_refs(
                self.context_input_refs
            )
        except ValueError as exc:
            raise _error(
                "research context input lineage is invalid",
                "invalid_replay_context_inputs",
            ) from exc
        boundaries = {
            (item.as_of, item.knowledge_cutoff, item.publication_cutoff)
            for item in normalized_context_inputs
        }
        if len(boundaries) > 1:
            raise _error(
                "research context inputs have mixed temporal boundaries",
                "invalid_replay_context_inputs",
            )
        object.__setattr__(
            self,
            "context_input_refs",
            normalized_context_inputs,
        )
        payload = canonical_payload(self._payload())
        object.__setattr__(self, "canonical_payload", payload.json_bytes)
        object.__setattr__(self, "reproduction_fingerprint", payload.content_hash)

    def _payload(self) -> Mapping[str, object]:
        return build_research_execution_payload(
            self,
            strategy_binding_type=StrategyExecutionBinding,
        )


@dataclass(frozen=True, slots=True)
class ResearchExecutionAudit:
    """Attempt-specific execution bundle whose semantic fingerprint is reusable."""

    semantics: ResearchExecutionSemantics
    attempt_id: str
    attempt_ordinal: int
    backtest_run_id: str
    parent_attempt_id: str | None
    resume_from_run_id: str | None
    created_at: datetime
    canonical_payload: bytes
    bundle_hash: ContentHash

    @classmethod
    def create(
        cls,
        *,
        semantics: ResearchExecutionSemantics,
        attempt_id: str,
        attempt_ordinal: int,
        backtest_run_id: str,
        parent_attempt_id: str | None,
        resume_from_run_id: str | None,
        created_at: datetime,
    ) -> ResearchExecutionAudit:
        """Create one immutable audit bundle after the attempt is claimed."""
        if type(semantics) is not ResearchExecutionSemantics:
            raise _error(
                "execution semantics are invalid",
                "invalid_execution_semantics",
            )
        _identity(attempt_id, "attempt_id")
        _positive_integer(attempt_ordinal, "attempt_ordinal")
        _identity(backtest_run_id, "backtest_run_id")
        if parent_attempt_id is not None:
            _identity(parent_attempt_id, "parent_attempt_id")
        if resume_from_run_id is not None:
            _identity(resume_from_run_id, "resume_from_run_id")
        raw_created_at: object = created_at
        if (
            type(raw_created_at) is not datetime
            or created_at.tzinfo is None
            or created_at.utcoffset() != UTC.utcoffset(created_at)
        ):
            raise _error("created_at must be UTC", "invalid_audit_timestamp")
        decoded_semantics = cast(
            "dict[str, object]",
            cast("object", orjson.loads(semantics.canonical_payload)),
        )
        payload = canonical_payload(
            {
                "schema_version": 1,
                "reproduction_fingerprint": str(semantics.reproduction_fingerprint),
                "semantics": decoded_semantics,
                "attempt": {
                    "attempt_id": attempt_id,
                    "attempt_ordinal": attempt_ordinal,
                    "backtest_run_id": backtest_run_id,
                    "parent_attempt_id": parent_attempt_id,
                    "resume_from_run_id": resume_from_run_id,
                    "created_at_epoch_us": int(created_at.timestamp() * 1_000_000),
                },
            }
        )
        return cls(
            semantics=semantics,
            attempt_id=attempt_id,
            attempt_ordinal=attempt_ordinal,
            backtest_run_id=backtest_run_id,
            parent_attempt_id=parent_attempt_id,
            resume_from_run_id=resume_from_run_id,
            created_at=created_at,
            canonical_payload=payload.json_bytes,
            bundle_hash=payload.content_hash,
        )

    @property
    def reproduction_fingerprint(self) -> ContentHash:
        """Expose the attempt-independent deterministic execution identity."""
        return self.semantics.reproduction_fingerprint
