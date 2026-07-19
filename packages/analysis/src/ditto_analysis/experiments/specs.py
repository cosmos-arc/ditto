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

__all__ = [
    "CandidateSpec",
    "ExperimentBudget",
    "ExperimentFailurePolicy",
    "ExperimentLaunchSpec",
    "FoldProtocolSpec",
]

type FrozenScalar = str | int | float | None
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
    if type(value) is bool:
        raise _spec_error(
            f"{path} must not use bool as a numeric value",
            "bool_is_not_numeric",
            field=path,
        )
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
    frozen = _freeze_value(cast("Mapping[object, object]", value), field_name)
    if not isinstance(frozen, Mapping):
        raise _spec_error(
            f"{field_name} must be a mapping",
            "invalid_parameter_mapping",
            field=field_name,
        )
    return frozen


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


def _canonical_parameter_value(value: FrozenValue) -> object:
    if isinstance(value, Mapping):
        return {
            key: _canonical_parameter_value(item) for key, item in sorted(value.items())
        }
    if isinstance(value, tuple):
        return [_canonical_parameter_value(item) for item in value]
    return value


def _parameter_hash(parameters: Mapping[str, FrozenValue]) -> str:
    payload = json.dumps(
        _canonical_parameter_value(parameters),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentLaunchSpec:
    """Complete minimum deterministic semantics frozen at experiment launch."""

    experiment_id: ExperimentId
    strategy_version: StrategyVersion
    strategy_spec_hash: ContentHash
    snapshot_id: SnapshotId
    candidates: Sequence[CandidateSpec]
    fold_protocol: FoldProtocolSpec
    seed: int
    worker_count: int
    failure_policy: ExperimentFailurePolicy
    budget: ExperimentBudget
    desired_state: ExperimentDesiredState
    created_at: datetime

    def __post_init__(self) -> None:  # noqa: C901 - complete aggregate invariant gate
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
        parameter_hashes = tuple(
            _parameter_hash(candidate.parameters) for candidate in candidates
        )
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

    @property
    def candidate_count(self) -> int:
        """Count every candidate, including the explicit baseline."""
        return len(self.candidates)

    @property
    def baseline_candidate(self) -> CandidateSpec:
        """Return the single baseline guaranteed by launch validation."""
        return next(candidate for candidate in self.candidates if candidate.is_baseline)
