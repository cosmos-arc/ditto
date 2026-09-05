"""Immutable, deterministic experiment launch specifications."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.promotion_models import PromotionObjective
from ditto_analysis.experiments.promotion_objective import (
    validate_promotion_objective_graph,
)
from ditto_analysis.experiments.trial_family import LogicalTrialIdentity, TrialKind

__all__ = [
    "CandidateExecutionBinding",
    "CandidateSpec",
    "ExperimentBudget",
    "ExperimentFailurePolicy",
    "ExperimentLaunchSpec",
    "FoldProtocolSpec",
    "candidate_parameter_hash",
]

type FrozenScalar = str | bool | int | float | None
type FrozenValue = FrozenScalar | tuple[FrozenValue, ...] | Mapping[str, FrozenValue]

_MAX_CANDIDATES = 128
_MIN_WORKERS = 2
_MAX_WORKERS = 4


def _spec_error(
    message: str, reason_code: str, **details: object
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise _spec_error(
            f"{field_name} must be a positive integer",
            "invalid_positive_integer",
            field=field_name,
            value=value,
        )
    return value


def _enter_container(
    value: object,
    path: str,
    active_container_ids: set[int],
) -> int:
    container_id = id(value)
    if container_id in active_container_ids:
        raise _spec_error(
            f"{path} contains a cyclic container reference",
            "cyclic_experiment_value",
            field=path,
        )
    active_container_ids.add(container_id)
    return container_id


def _freeze_mapping_value(
    value: Mapping[object, object],
    path: str,
    active_container_ids: set[int],
) -> Mapping[str, FrozenValue]:
    container_id = _enter_container(value, path, active_container_ids)
    try:
        frozen: dict[str, FrozenValue] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise _spec_error(
                    f"{path} mapping keys must be non-empty strings",
                    "invalid_parameter_key",
                    field=path,
                )
            frozen[key] = _freeze_value(
                item,
                f"{path}.{key}",
                active_container_ids,
            )
        return MappingProxyType(frozen)
    finally:
        active_container_ids.remove(container_id)


def _freeze_sequence_value(
    value: Sequence[object],
    path: str,
    active_container_ids: set[int],
) -> tuple[FrozenValue, ...]:
    container_id = _enter_container(value, path, active_container_ids)
    try:
        return tuple(
            _freeze_value(
                item,
                f"{path}[{index}]",
                active_container_ids,
            )
            for index, item in enumerate(value)
        )
    finally:
        active_container_ids.remove(container_id)


def _freeze_value(
    value: object,
    path: str,
    active_container_ids: set[int] | None = None,
) -> FrozenValue:
    active_ids: set[int] = (
        set() if active_container_ids is None else active_container_ids
    )
    if value is None or isinstance(value, str):
        return value
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise _spec_error(
                f"{path} must be finite",
                "non_finite_experiment_value",
                field=path,
            )
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return _freeze_mapping_value(mapping, path, active_ids)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return _freeze_sequence_value(sequence, path, active_ids)
    raise _spec_error(
        f"{path} contains an unsupported or unordered value",
        "invalid_experiment_value",
        field=path,
        value_type=type(value).__name__,
    )


def _freeze_mapping(value: object, field_name: str) -> Mapping[str, FrozenValue]:
    if not isinstance(value, Mapping):
        raise _spec_error(
            f"{field_name} must be a mapping",
            "invalid_parameter_mapping",
            field=field_name,
        )
    return cast(
        "Mapping[str, FrozenValue]",
        _freeze_value(cast("Mapping[object, object]", value), field_name),
    )


class ExperimentFailurePolicy(StrEnum):
    """Stable policy for child-attempt failures."""

    CONTINUE_CANDIDATE_FAILURES = "continue_candidate_failures"
    FAIL_FAST = "fail_fast"


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    """Frozen candidate parameters and stable ordinal."""

    candidate_id: CandidateId
    ordinal: int
    is_baseline: bool
    parameters: Mapping[str, FrozenValue]

    def __post_init__(self) -> None:
        """Validate identity/ordinal and deeply freeze parameters."""
        if not isinstance(cast("object", self.candidate_id), CandidateId):
            raise _spec_error(
                "candidate_id must be CandidateId",
                "invalid_candidate_identity",
            )
        _positive_int(self.ordinal, "candidate_ordinal")
        if type(self.is_baseline) is not bool:
            raise _spec_error(
                "is_baseline must be bool",
                "invalid_baseline_marker",
            )
        object.__setattr__(
            self,
            "parameters",
            _freeze_mapping(self.parameters, "parameters"),
        )

    @property
    def parameter_hash(self) -> ContentHash:
        """Return the canonical content identity of the frozen parameters."""
        return candidate_parameter_hash(self.parameters)


@dataclass(frozen=True, slots=True)
class CandidateExecutionBinding:
    """Preflight-frozen runtime identity for one exact launch candidate."""

    candidate_id: CandidateId
    ordinal: int
    parameter_hash: ContentHash
    resolved_spec_hash: ContentHash

    def __post_init__(self) -> None:
        """Reject nominal or partial runtime identities."""
        if type(self.candidate_id) is not CandidateId:
            raise _spec_error(
                "execution binding candidate_id must be CandidateId",
                "invalid_candidate_execution_binding",
            )
        _positive_int(self.ordinal, "candidate_execution_ordinal")
        if (
            type(self.parameter_hash) is not ContentHash
            or type(self.resolved_spec_hash) is not ContentHash
        ):
            raise _spec_error(
                "execution binding requires exact parameter and resolved spec hashes",
                "invalid_candidate_execution_binding",
            )


@dataclass(frozen=True, slots=True)
class FoldProtocolSpec:
    """Opaque, versioned fold protocol frozen before later matrix expansion."""

    protocol_id: str
    protocol_version: int
    protocol_hash: ContentHash

    def __post_init__(self) -> None:
        """Validate the opaque versioned protocol reference."""
        raw_protocol_id = cast("object", self.protocol_id)
        if not isinstance(raw_protocol_id, str) or not raw_protocol_id.strip():
            raise _spec_error(
                "protocol_id must be a non-empty string",
                "invalid_fold_protocol",
            )
        if self.protocol_id != self.protocol_id.strip():
            raise _spec_error(
                "protocol_id cannot have surrounding whitespace",
                "invalid_fold_protocol",
            )
        _positive_int(self.protocol_version, "protocol_version")
        if not isinstance(cast("object", self.protocol_hash), ContentHash):
            raise _spec_error(
                "protocol_hash must be ContentHash",
                "invalid_fold_protocol",
            )


@dataclass(frozen=True, slots=True)
class ExperimentBudget:
    """Pre-registered bounded work budget."""

    candidate_limit: int
    fold_run_limit: int

    def __post_init__(self) -> None:
        """Validate bounded, positive budget values."""
        _positive_int(self.candidate_limit, "candidate_limit")
        _positive_int(self.fold_run_limit, "fold_run_limit")
        if self.candidate_limit > _MAX_CANDIDATES:
            raise _spec_error(
                "candidate_limit cannot exceed 128",
                "candidate_limit_exceeded",
                candidate_limit=self.candidate_limit,
            )


def _freeze_candidates(value: object) -> tuple[CandidateSpec, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _spec_error(
            "candidates must be an ordered finite Sequence",
            "invalid_candidate_sequence",
        )
    candidates = tuple(cast("Sequence[object]", value))
    if not candidates or any(
        not isinstance(item, CandidateSpec) for item in candidates
    ):
        raise _spec_error(
            "candidates must contain CandidateSpec values",
            "invalid_candidate_sequence",
        )
    return cast("tuple[CandidateSpec, ...]", candidates)


def _freeze_execution_bindings(
    value: object,
) -> tuple[CandidateExecutionBinding, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _spec_error(
            "execution_bindings must be an ordered finite Sequence",
            "invalid_candidate_execution_bindings",
        )
    bindings = tuple(cast("Sequence[object]", value))
    if not bindings or any(
        type(item) is not CandidateExecutionBinding for item in bindings
    ):
        raise _spec_error(
            "execution_bindings must contain exact typed bindings",
            "invalid_candidate_execution_bindings",
        )
    return cast("tuple[CandidateExecutionBinding, ...]", bindings)


def _canonical_parameter_value(value: FrozenValue) -> object:
    if isinstance(value, Mapping):
        return {
            key: _canonical_parameter_value(item) for key, item in sorted(value.items())
        }
    if isinstance(value, tuple):
        return [_canonical_parameter_value(item) for item in value]
    return value


def candidate_parameter_hash(
    parameters: Mapping[str, FrozenValue],
) -> ContentHash:
    """Hash one frozen candidate parameter mapping canonically."""
    payload = json.dumps(
        _canonical_parameter_value(parameters),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ContentHash(hashlib.sha256(payload).hexdigest())


def _promotion_objective_for_family(
    value: object,
    *,
    experiment_id: ExperimentId,
    baseline_candidate_id: CandidateId,
    candidates: tuple[CandidateSpec, ...],
) -> PromotionObjective:
    objective = validate_promotion_objective_graph(value)
    if objective.baseline_candidate_id != baseline_candidate_id:
        raise _spec_error(
            "promotion objective must bind the explicit baseline candidate",
            "promotion_baseline_candidate_mismatch",
        )
    expected_current = tuple(
        LogicalTrialIdentity(
            origin_experiment_id=experiment_id,
            candidate_id=candidate.candidate_id,
            ordinal=candidate.ordinal,
            parameter_hash=candidate.parameter_hash,
            kind=TrialKind.CURRENT,
        )
        for candidate in candidates
    )
    if objective.trial_family.current_members != expected_current:
        raise _spec_error(
            "promotion objective current family must equal executable candidates",
            "promotion_current_trial_family_mismatch",
            declared_current_trial_count=len(objective.trial_family.current_members),
            candidate_count=len(candidates),
        )
    return objective


@dataclass(frozen=True, slots=True)
class ExperimentLaunchSpec:
    """Complete minimum deterministic semantics frozen at experiment launch."""

    experiment_id: ExperimentId
    strategy_version: StrategyVersion
    strategy_spec_hash: ContentHash
    snapshot_id: SnapshotId
    candidates: Sequence[CandidateSpec]
    execution_bindings: Sequence[CandidateExecutionBinding]
    promotion_objective: PromotionObjective
    fold_protocol: FoldProtocolSpec
    seed: int
    worker_count: int
    failure_policy: ExperimentFailurePolicy
    budget: ExperimentBudget
    desired_state: ExperimentDesiredState
    created_at: datetime

    def __post_init__(self) -> None:  # noqa: C901, PLR0912 - aggregate invariant gate
        """Validate and defensively freeze all deterministic launch semantics."""
        typed_fields = (
            (self.experiment_id, ExperimentId, "experiment_id"),
            (self.strategy_version, StrategyVersion, "strategy_version"),
            (self.strategy_spec_hash, ContentHash, "strategy_spec_hash"),
            (self.snapshot_id, SnapshotId, "snapshot_id"),
            (self.fold_protocol, FoldProtocolSpec, "fold_protocol"),
            (self.failure_policy, ExperimentFailurePolicy, "failure_policy"),
            (self.budget, ExperimentBudget, "budget"),
            (self.desired_state, ExperimentDesiredState, "desired_state"),
        )
        for value, expected, field_name in typed_fields:
            if not isinstance(cast("object", value), expected):
                raise _spec_error(
                    f"{field_name} must be {expected.__name__}",
                    "invalid_launch_spec_field",
                    field=field_name,
                )
        if self.desired_state is not ExperimentDesiredState.RUN:
            raise _spec_error(
                "experiment launch must begin with run intent",
                "initial_desired_state_must_be_run",
            )
        if type(self.seed) is not int or self.seed < 0:
            raise _spec_error(
                "seed must be a non-negative integer",
                "invalid_seed",
            )
        if (
            type(self.worker_count) is not int
            or not _MIN_WORKERS <= self.worker_count <= _MAX_WORKERS
        ):
            raise _spec_error(
                "worker_count must be between 2 and 4",
                "invalid_worker_count",
            )
        require_utc_datetime(self.created_at, "created_at")

        candidates = _freeze_candidates(self.candidates)
        object.__setattr__(self, "candidates", candidates)
        execution_bindings = _freeze_execution_bindings(self.execution_bindings)
        object.__setattr__(self, "execution_bindings", execution_bindings)
        ordinals = tuple(candidate.ordinal for candidate in candidates)
        if ordinals != tuple(range(1, len(candidates) + 1)):
            raise _spec_error(
                "candidate ordinals must be unique and contiguous from one",
                "candidate_ordinals_not_contiguous",
                ordinals=ordinals,
            )
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise _spec_error(
                "candidate identities must be unique within an experiment",
                "duplicate_candidate_identity",
            )
        expected_binding_keys = tuple(
            (candidate.candidate_id, candidate.ordinal) for candidate in candidates
        )
        observed_binding_keys = tuple(
            (binding.candidate_id, binding.ordinal) for binding in execution_bindings
        )
        if observed_binding_keys != expected_binding_keys:
            raise _spec_error(
                "execution bindings must exactly match launch candidate order",
                "candidate_execution_binding_mismatch",
            )
        if any(
            binding.parameter_hash != candidate.parameter_hash
            for candidate, binding in zip(candidates, execution_bindings, strict=True)
        ):
            raise _spec_error(
                "execution binding parameter hash must equal candidate parameters",
                "candidate_execution_parameter_hash_mismatch",
            )
        parameter_hashes = tuple(candidate.parameter_hash for candidate in candidates)
        if len(set(parameter_hashes)) != len(parameter_hashes):
            raise _spec_error(
                "candidate parameter sets must be semantically unique",
                "duplicate_candidate_parameters",
            )
        baselines = tuple(
            candidate for candidate in candidates if candidate.is_baseline
        )
        if not baselines:
            raise _spec_error(
                "one explicit baseline candidate is required",
                "baseline_candidate_missing",
            )
        if len(baselines) > 1:
            raise _spec_error(
                "only one baseline candidate is allowed",
                "multiple_baseline_candidates",
            )
        baseline = next(candidate for candidate in candidates if candidate.is_baseline)
        if (
            len(candidates) > _MAX_CANDIDATES
            or len(candidates) > self.budget.candidate_limit
        ):
            raise _spec_error(
                "candidate count exceeds the pre-registered budget",
                "candidate_limit_exceeded",
                candidate_count=len(candidates),
                candidate_limit=self.budget.candidate_limit,
            )
        object.__setattr__(
            self,
            "promotion_objective",
            _promotion_objective_for_family(
                self.promotion_objective,
                experiment_id=self.experiment_id,
                baseline_candidate_id=baseline.candidate_id,
                candidates=candidates,
            ),
        )

    @property
    def candidate_count(self) -> int:
        """Count every candidate, including the explicit baseline."""
        return len(self.candidates)

    @property
    def baseline_candidate(self) -> CandidateSpec:
        """Return the single baseline guaranteed by launch validation."""
        return next(candidate for candidate in self.candidates if candidate.is_baseline)
