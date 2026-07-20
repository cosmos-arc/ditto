"""
Pure deterministic planning for bounded research experiments.

This module owns candidate-matrix and resource-budget semantics only.  It performs no
I/O and deliberately keeps the application-owned baseline envelope separate from
typed parameters that may be sent to ``ParameterBinder``.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import cast

import orjson
from ditto_analysis.experiments.specs import ExperimentFailurePolicy
from ditto_strategy.alpha.parameters import CandidateParameter, ParameterValue
from ditto_strategy.errors import StrategySpecError

from ditto_application.processes.experiments._planning_budget import (
    ExperimentBudgetSpec,
    ExperimentTrack,
    ResourceCostModel,
    ResourceEstimate,
    ValidationWorkload,
    estimate_resource_budget,
)
from ditto_application.processes.experiments._planning_budget import (
    nonnegative_int as _nonnegative_int,
)
from ditto_application.processes.experiments._planning_values import (
    BaselineInputValue,
    BaselineValue,
    ExperimentPlanningError,
)
from ditto_application.processes.experiments._planning_values import (
    freeze_baseline_mapping as _freeze_baseline_mapping,
)
from ditto_application.processes.experiments._planning_values import (
    planning_error as _planning_error,
)

__all__ = [
    "BASELINE_PARAMETER_KEY",
    "BaselineCandidatePlan",
    "BaselineDescriptor",
    "BinderCandidatePlan",
    "CandidateMatrixPlan",
    "CandidateMatrixSize",
    "CandidateMatrixSpec",
    "CandidateRole",
    "ExperimentBudgetSpec",
    "ExperimentPlanningError",
    "ExperimentPlanningSpec",
    "ExperimentTrack",
    "ExperimentWorkPlan",
    "ParameterAxis",
    "ResourceCostModel",
    "ResourceEstimate",
    "ValidationWorkload",
    "estimate_resource_budget",
    "expand_candidate_matrix",
    "inspect_candidate_matrix_size",
    "plan_experiment_work",
]

BASELINE_PARAMETER_KEY = "__ditto_baseline__"
_BASELINE_SCHEMA_VERSION = 1
_CANDIDATE_SCHEMA_VERSION = 1
_MAX_CANDIDATES = 128
_ALLOWED_WORKER_COUNTS = (2, 4)
_FIRST_BINDER_ORDINAL = 2

type PlannedCandidate = BaselineCandidatePlan | BinderCandidatePlan


def _plain_json_value(value: BaselineValue) -> object:
    if isinstance(value, Mapping):
        return {
            key: _plain_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: pair[0])
        }
    if isinstance(value, tuple):
        return [_plain_json_value(item) for item in value]
    return value


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    except (TypeError, ValueError, OverflowError) as exc:
        _planning_error(
            "planning value has no canonical JSON identity",
            reason="invalid_canonical_planning_value",
            codec_error=type(exc).__name__,
        )


@dataclass(frozen=True, slots=True)
class BaselineDescriptor:
    """Lossless application-owned description of the explicit baseline."""

    descriptor_type: str
    payload: Mapping[str, BaselineInputValue]
    schema_version: int = _BASELINE_SCHEMA_VERSION
    canonical_json: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate, deeply freeze, and canonically encode the descriptor."""
        raw_type = cast("object", self.descriptor_type)
        if (
            type(self) is not BaselineDescriptor
            or type(raw_type) is not str
            or not raw_type.strip()
            or raw_type != raw_type.strip()
        ):
            _planning_error(
                "baseline descriptor_type must be a canonical non-empty string",
                reason="invalid_baseline_descriptor_type",
            )
        if type(self.schema_version) is not int or self.schema_version <= 0:
            _planning_error(
                "baseline schema_version must be a positive integer",
                reason="invalid_baseline_schema_version",
            )
        frozen = _freeze_baseline_mapping(cast("object", self.payload))
        object.__setattr__(self, "payload", frozen)
        encoded = _canonical_json_bytes(
            {
                "schema_version": self.schema_version,
                "descriptor_type": self.descriptor_type,
                "payload": _plain_json_value(frozen),
            },
        )
        object.__setattr__(self, "canonical_json", encoded.decode("utf-8"))


def _parameter_type(value: ParameterValue) -> str:
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "int"
    if type(value) is float:
        return "float"
    return "string"


def _canonical_parameter_identity(value: ParameterValue) -> bytes:
    return _canonical_json_bytes(
        {"type": _parameter_type(value), "value": value},
    )


def _validated_parameter_value(name: str, value: object) -> ParameterValue:
    try:
        return CandidateParameter(path=name, value=cast("ParameterValue", value)).value
    except StrategySpecError as exc:
        _planning_error(
            "matrix value is not a canonical typed parameter",
            reason="invalid_matrix_parameter_value",
            parameter_name=name,
            strategy_reason=exc.details.get("reason"),
        )


@dataclass(frozen=True, slots=True)
class ParameterAxis:
    """One explicit, finite candidate parameter value list."""

    name: str
    values: Sequence[ParameterValue]

    def __post_init__(self) -> None:
        """Validate and sort canonical values independently of request order."""
        raw_name = cast("object", self.name)
        if (
            type(self) is not ParameterAxis
            or type(raw_name) is not str
            or not raw_name.strip()
            or raw_name != raw_name.strip()
        ):
            _planning_error(
                "matrix parameter name must be a canonical non-empty string",
                reason="invalid_matrix_parameter_name",
            )
        if self.name == BASELINE_PARAMETER_KEY:
            _planning_error(
                "matrix parameter name collides with the baseline envelope",
                reason="reserved_matrix_parameter_name",
                parameter_name=self.name,
            )
        raw_values = cast("object", self.values)
        if type(raw_values) not in (tuple, list) or not raw_values:
            _planning_error(
                "matrix axis values must be an explicit non-empty list",
                reason="invalid_matrix_axis_values",
                parameter_name=self.name,
            )
        identified: list[tuple[bytes, ParameterValue]] = []
        for value in cast("tuple[object, ...] | list[object]", raw_values):
            normalized = _validated_parameter_value(self.name, value)
            identified.append((_canonical_parameter_identity(normalized), normalized))
        identities = [identity for identity, _ in identified]
        if len(set(identities)) != len(identities):
            _planning_error(
                "matrix axis values must be canonically unique",
                reason="duplicate_matrix_axis_value",
                parameter_name=self.name,
            )
        identified.sort(key=lambda item: item[0])
        object.__setattr__(self, "values", tuple(value for _, value in identified))


@dataclass(frozen=True, slots=True)
class CandidateMatrixSpec:
    """Pre-registered finite Cartesian matrix including its hard candidate limit."""

    baseline: BaselineDescriptor
    axes: Sequence[ParameterAxis] = ()
    candidate_limit: int = _MAX_CANDIDATES

    def __post_init__(self) -> None:
        """Freeze axes in canonical parameter-name order."""
        if type(self) is not CandidateMatrixSpec:
            _planning_error(
                "matrix spec must be an exact CandidateMatrixSpec",
                reason="invalid_matrix_spec",
            )
        if type(cast("object", self.baseline)) is not BaselineDescriptor:
            _planning_error(
                "matrix baseline must be BaselineDescriptor",
                reason="invalid_matrix_baseline",
            )
        raw_axes: object = self.axes
        if type(raw_axes) not in (tuple, list):
            _planning_error(
                "matrix axes must be an explicit list of ParameterAxis",
                reason="invalid_matrix_axes",
            )
        axis_items = tuple(cast("Sequence[object]", raw_axes))
        if any(type(axis) is not ParameterAxis for axis in axis_items):
            _planning_error(
                "matrix axes must be an explicit list of ParameterAxis",
                reason="invalid_matrix_axes",
            )
        axes = cast("tuple[ParameterAxis, ...]", axis_items)
        names = tuple(axis.name for axis in axes)
        if len(set(names)) != len(names):
            _planning_error(
                "matrix parameter names must be unique",
                reason="duplicate_matrix_parameter_name",
            )
        if (
            type(self.candidate_limit) is not int
            or self.candidate_limit <= 0
            or self.candidate_limit > _MAX_CANDIDATES
        ):
            _planning_error(
                "candidate_limit must be between 1 and 128",
                reason="invalid_candidate_limit",
                candidate_limit=self.candidate_limit,
            )
        object.__setattr__(
            self,
            "axes",
            tuple(sorted(axes, key=lambda axis: axis.name.encode("utf-8"))),
        )


class CandidateRole(StrEnum):
    """Stable identity role included in every candidate hash."""

    BASELINE = "baseline"
    DEFAULT = "default"
    MATRIX = "matrix"


def _parameter_hash(
    *,
    ordinal: int,
    role: CandidateRole,
    parameters: Sequence[CandidateParameter],
) -> str:
    payload = {
        "schema_version": _CANDIDATE_SCHEMA_VERSION,
        "ordinal": ordinal,
        "role": role.value,
        "parameters": [
            {
                "name": parameter.path,
                "type": _parameter_type(parameter.value),
                "value": parameter.value,
            }
            for parameter in parameters
        ],
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _require_binder_parameters(value: object) -> tuple[CandidateParameter, ...]:
    if type(value) is not tuple:
        _planning_error(
            "binder_parameters must be tuple[CandidateParameter, ...]",
            reason="invalid_binder_parameters",
        )
    items = cast("tuple[object, ...]", value)
    if any(type(parameter) is not CandidateParameter for parameter in items):
        _planning_error(
            "binder_parameters must be tuple[CandidateParameter, ...]",
            reason="invalid_binder_parameters",
        )
    return cast("tuple[CandidateParameter, ...]", items)


@dataclass(frozen=True, slots=True)
class BaselineCandidatePlan:
    """Baseline candidate with persistence-only parameters and no binder payload."""

    descriptor: BaselineDescriptor
    ordinal: int = field(init=False, default=1)
    role: CandidateRole = field(init=False, default=CandidateRole.BASELINE)
    persistence_parameters: Mapping[str, str] = field(init=False)
    candidate_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Create the reserved persistence envelope and role-aware identity."""
        if (
            type(self) is not BaselineCandidatePlan
            or type(self.descriptor) is not BaselineDescriptor
        ):
            _planning_error(
                "baseline candidate must use exact planning graph nodes",
                reason="invalid_baseline_candidate",
            )
        envelope = MappingProxyType(
            {BASELINE_PARAMETER_KEY: self.descriptor.canonical_json},
        )
        object.__setattr__(self, "persistence_parameters", envelope)
        parameter = CandidateParameter(
            path=BASELINE_PARAMETER_KEY,
            value=self.descriptor.canonical_json,
        )
        object.__setattr__(
            self,
            "candidate_hash",
            _parameter_hash(
                ordinal=self.ordinal,
                role=self.role,
                parameters=(parameter,),
            ),
        )


@dataclass(frozen=True, slots=True)
class BinderCandidatePlan:
    """Default or matrix candidate safe to pass to ``ParameterBinder``."""

    ordinal: int
    binder_parameters: tuple[CandidateParameter, ...]
    role: CandidateRole = field(init=False)
    persistence_parameters: Mapping[str, ParameterValue] = field(init=False)
    candidate_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate canonical ordering and derive persistence/hash projections."""
        if type(self) is not BinderCandidatePlan:
            _planning_error(
                "binder candidate must be an exact BinderCandidatePlan",
                reason="invalid_binder_candidate",
            )
        if type(self.ordinal) is not int or self.ordinal < _FIRST_BINDER_ORDINAL:
            _planning_error(
                "binder candidate ordinal must be at least two",
                reason="invalid_candidate_ordinal",
                ordinal=self.ordinal,
            )
        parameters = _require_binder_parameters(
            cast("object", self.binder_parameters),
        )
        names = tuple(parameter.path for parameter in parameters)
        if names != tuple(sorted(names, key=lambda name: name.encode("utf-8"))):
            _planning_error(
                "binder parameters must use canonical name order",
                reason="non_canonical_binder_parameter_order",
            )
        if len(set(names)) != len(names):
            _planning_error(
                "binder parameter names must be unique",
                reason="duplicate_binder_parameter_name",
            )
        role = (
            CandidateRole.DEFAULT
            if not self.binder_parameters
            else CandidateRole.MATRIX
        )
        object.__setattr__(self, "role", role)
        object.__setattr__(
            self,
            "persistence_parameters",
            MappingProxyType(
                {parameter.path: parameter.value for parameter in parameters},
            ),
        )
        object.__setattr__(
            self,
            "candidate_hash",
            _parameter_hash(
                ordinal=self.ordinal,
                role=role,
                parameters=parameters,
            ),
        )


@dataclass(frozen=True, slots=True)
class CandidateMatrixPlan:
    """Deterministic baseline-first expansion of one finite matrix."""

    candidate_limit: int
    baseline_candidate: BaselineCandidatePlan
    binder_candidates: tuple[BinderCandidatePlan, ...]
    matrix_hash: str

    @property
    def candidates(self) -> tuple[PlannedCandidate, ...]:
        """Return baseline plus executable candidates in stable ordinal order."""
        return (self.baseline_candidate, *self.binder_candidates)

    @property
    def candidate_count(self) -> int:
        """Count every executable configuration, including the baseline."""
        return 1 + len(self.binder_candidates)


@dataclass(frozen=True, slots=True)
class CandidateMatrixSize:
    """Independent canonical matrix cardinality used by success and error paths."""

    candidate_count: int
    candidate_limit: int

    @property
    def exceeds_limit(self) -> bool:
        """Return whether the exact Cartesian size exceeds the registered ceiling."""
        return self.candidate_count > self.candidate_limit


def inspect_candidate_matrix_size(spec: CandidateMatrixSpec) -> CandidateMatrixSize:
    """Measure one validated canonical matrix without expanding its candidates."""
    if type(spec) is not CandidateMatrixSpec:
        _planning_error(
            "matrix spec must be CandidateMatrixSpec",
            reason="invalid_matrix_spec",
        )
    combination_count = math.prod(len(axis.values) for axis in spec.axes)
    return CandidateMatrixSize(
        candidate_count=1 + combination_count,
        candidate_limit=spec.candidate_limit,
    )


def expand_candidate_matrix(spec: CandidateMatrixSpec) -> CandidateMatrixPlan:
    """Expand a canonical finite Cartesian matrix without sampling or truncation."""
    if type(cast("object", spec)) is not CandidateMatrixSpec:
        _planning_error(
            "matrix spec must be CandidateMatrixSpec",
            reason="invalid_matrix_spec",
        )
    matrix_size = inspect_candidate_matrix_size(spec)
    candidate_count = matrix_size.candidate_count
    if matrix_size.exceeds_limit:
        _planning_error(
            "candidate matrix exceeds its pre-registered hard limit",
            code="MATRIX_TOO_LARGE",
            candidate_count=candidate_count,
            candidate_limit=spec.candidate_limit,
        )
    value_axes = tuple(axis.values for axis in spec.axes)
    combinations: Sequence[tuple[ParameterValue, ...]] = (
        tuple(itertools.product(*value_axes)) if value_axes else ((),)
    )
    candidates = tuple(
        BinderCandidatePlan(
            ordinal=ordinal,
            binder_parameters=tuple(
                CandidateParameter(path=axis.name, value=value)
                for axis, value in zip(spec.axes, values, strict=True)
            ),
        )
        for ordinal, values in enumerate(combinations, start=2)
    )
    baseline = BaselineCandidatePlan(descriptor=spec.baseline)
    candidate_hashes = (
        baseline.candidate_hash,
        *(candidate.candidate_hash for candidate in candidates),
    )
    matrix_hash = hashlib.sha256(
        _canonical_json_bytes(
            {
                "schema_version": _CANDIDATE_SCHEMA_VERSION,
                "candidate_limit": spec.candidate_limit,
                "candidate_hashes": candidate_hashes,
            },
        ),
    ).hexdigest()
    return CandidateMatrixPlan(
        candidate_limit=spec.candidate_limit,
        baseline_candidate=baseline,
        binder_candidates=candidates,
        matrix_hash=matrix_hash,
    )


@dataclass(frozen=True, slots=True)
class ExperimentPlanningSpec:
    """Complete pure-planning request whose controls are frozen into the plan."""

    matrix: CandidateMatrixSpec
    track: ExperimentTrack
    workload: ValidationWorkload
    cost_model: ResourceCostModel
    budget: ExperimentBudgetSpec
    seed: int = 0
    worker_count: int = 2
    failure_policy: ExperimentFailurePolicy = (
        ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES
    )

    def __post_init__(self) -> None:
        """Validate typed controls and one authoritative candidate ceiling."""
        if type(self) is not ExperimentPlanningSpec:
            _planning_error(
                "planning spec must be an exact ExperimentPlanningSpec",
                reason="invalid_planning_spec",
            )
        typed_fields = (
            (self.matrix, CandidateMatrixSpec, "matrix"),
            (self.track, ExperimentTrack, "track"),
            (self.workload, ValidationWorkload, "workload"),
            (self.cost_model, ResourceCostModel, "cost_model"),
            (self.budget, ExperimentBudgetSpec, "budget"),
            (self.failure_policy, ExperimentFailurePolicy, "failure_policy"),
        )
        for value, expected_type, field_name in typed_fields:
            if type(cast("object", value)) is not expected_type:
                _planning_error(
                    f"{field_name} must be {expected_type.__name__}",
                    reason="invalid_planning_field",
                    field=field_name,
                )
        if self.matrix.candidate_limit != self.budget.candidate_limit:
            _planning_error(
                "matrix and budget candidate limits must be identical",
                reason="candidate_limit_mismatch",
                matrix_candidate_limit=self.matrix.candidate_limit,
                budget_candidate_limit=self.budget.candidate_limit,
            )
        _nonnegative_int(self.seed, field_name="seed")
        if type(self.worker_count) is not int or self.worker_count not in (
            _ALLOWED_WORKER_COUNTS
        ):
            _planning_error(
                "worker_count must be exactly 2 or 4",
                reason="invalid_worker_count",
                worker_count=self.worker_count,
                allowed_worker_counts=_ALLOWED_WORKER_COUNTS,
            )


@dataclass(frozen=True, slots=True)
class ExperimentWorkPlan:
    """Frozen deterministic candidate and work plan ready for launch conversion."""

    candidate_matrix: CandidateMatrixPlan
    track: ExperimentTrack
    workload: ValidationWorkload
    cost_model: ResourceCostModel
    budget: ExperimentBudgetSpec
    seed: int
    worker_count: int
    failure_policy: ExperimentFailurePolicy
    estimate: ResourceEstimate
    plan_hash: str


def _budget_excesses(
    estimate: ResourceEstimate,
    budget: ExperimentBudgetSpec,
) -> tuple[str, ...]:
    excesses: list[str] = []
    if estimate.total_run_count > budget.fold_run_limit:
        excesses.append("fold_run_limit")
    if estimate.estimated_trading_sessions > budget.trading_session_limit:
        excesses.append("trading_session_limit")
    if estimate.estimated_disk_bytes > budget.disk_byte_limit:
        excesses.append("disk_byte_limit")
    return tuple(excesses)


def _work_plan_hash(
    spec: ExperimentPlanningSpec,
    matrix: CandidateMatrixPlan,
    estimate: ResourceEstimate,
) -> str:
    payload = {
        "schema_version": 1,
        "matrix_hash": matrix.matrix_hash,
        "track": spec.track.value,
        "fold_session_counts": spec.workload.fold_session_counts,
        "holdout_session_count": spec.workload.holdout_session_count,
        "cost_model": {
            "bytes_per_run": spec.cost_model.bytes_per_run,
            "bytes_per_trading_session": (spec.cost_model.bytes_per_trading_session),
        },
        "budget": {
            "candidate_limit": spec.budget.candidate_limit,
            "fold_run_limit": spec.budget.fold_run_limit,
            "trading_session_limit": spec.budget.trading_session_limit,
            "disk_byte_limit": spec.budget.disk_byte_limit,
        },
        "seed": spec.seed,
        "worker_count": spec.worker_count,
        "failure_policy": spec.failure_policy.value,
        "estimate": {
            "candidate_count": estimate.candidate_count,
            "validation_run_count": estimate.validation_run_count,
            "holdout_run_count": estimate.holdout_run_count,
            "total_run_count": estimate.total_run_count,
            "estimated_trading_sessions": estimate.estimated_trading_sessions,
            "estimated_disk_bytes": estimate.estimated_disk_bytes,
        },
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def plan_experiment_work(spec: ExperimentPlanningSpec) -> ExperimentWorkPlan:
    """Expand and budget one immutable experiment plan, failing closed on limits."""
    if type(cast("object", spec)) is not ExperimentPlanningSpec:
        _planning_error(
            "planning spec must be ExperimentPlanningSpec",
            reason="invalid_planning_spec",
        )
    matrix = expand_candidate_matrix(spec.matrix)
    estimate = estimate_resource_budget(
        candidate_count=matrix.candidate_count,
        track=spec.track,
        workload=spec.workload,
        cost_model=spec.cost_model,
    )
    excesses = _budget_excesses(estimate, spec.budget)
    if excesses:
        _planning_error(
            "experiment resource estimate exceeds the pre-registered budget",
            code="BUDGET_EXCEEDED",
            exceeded=excesses,
            total_run_count=estimate.total_run_count,
            estimated_trading_sessions=estimate.estimated_trading_sessions,
            estimated_disk_bytes=estimate.estimated_disk_bytes,
        )
    return ExperimentWorkPlan(
        candidate_matrix=matrix,
        track=spec.track,
        workload=spec.workload,
        cost_model=spec.cost_model,
        budget=spec.budget,
        seed=spec.seed,
        worker_count=spec.worker_count,
        failure_policy=spec.failure_policy,
        estimate=estimate,
        plan_hash=_work_plan_hash(spec, matrix, estimate),
    )
