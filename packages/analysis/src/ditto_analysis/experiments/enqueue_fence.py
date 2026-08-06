"""Typed exact-set identities for atomic experiment enqueue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    FoldKey,
    FoldPersistenceSpec,
    GateEvaluationRecord,
)

__all__ = [
    "ExperimentEnqueueFence",
    "FoldPersistenceFence",
    "GateEvaluationFence",
]


def _invalid(message: str, **details: object) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": "invalid_enqueue_fence", **details},
    )


def _utf8(value: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _invalid("enqueue fence identity must be UTF-8 encodable") from exc


@dataclass(frozen=True, slots=True)
class GateEvaluationFence:
    """Expected immutable identity of one gate at the enqueue boundary."""

    evaluation_id: str
    payload_hash: ContentHash

    def __post_init__(self) -> None:
        """Reject loose identities and hash subclasses at the persistence fence."""
        if (
            type(self) is not GateEvaluationFence
            or type(self.evaluation_id) is not str
            or not self.evaluation_id.strip()
            or self.evaluation_id != self.evaluation_id.strip()
            or type(self.payload_hash) is not ContentHash
        ):
            raise _invalid(
                "gate enqueue fence identity is invalid",
                fence_component="gate",
            )
        _utf8(self.evaluation_id)


@dataclass(frozen=True, slots=True)
class FoldPersistenceFence:
    """Expected immutable identity of one fold at the enqueue boundary."""

    key: FoldKey
    payload_hash: ContentHash

    def __post_init__(self) -> None:
        """Require the exact nominal fold key and canonical content hash types."""
        if (
            type(self) is not FoldPersistenceFence
            or type(self.key) is not FoldKey
            or type(self.key.experiment_id) is not ExperimentId
            or type(self.key.candidate_id) is not CandidateId
            or type(self.key.fold_id) is not FoldId
            or type(self.payload_hash) is not ContentHash
        ):
            raise _invalid(
                "fold enqueue fence identity is invalid",
                fence_component="fold",
            )
        _fold_fence_sort_key(self)


def _gate_fence_sort_key(value: GateEvaluationFence) -> bytes:
    return _utf8(value.evaluation_id)


def _fold_fence_sort_key(value: FoldPersistenceFence) -> tuple[bytes, bytes, bytes]:
    return (
        _utf8(str(value.key.experiment_id)),
        _utf8(str(value.key.candidate_id)),
        _utf8(str(value.key.fold_id)),
    )


@dataclass(frozen=True, slots=True)
class ExperimentEnqueueFence:
    """Exact gate and fold sets that must exist in one enqueue transaction."""

    gates: tuple[GateEvaluationFence, ...]
    folds: tuple[FoldPersistenceFence, ...]

    def __post_init__(self) -> None:
        """Require exact, unique, canonically ordered fence components."""
        raw_gates = cast("object", self.gates)
        raw_folds = cast("object", self.folds)
        if (
            type(self) is not ExperimentEnqueueFence
            or type(raw_gates) is not tuple
            or type(raw_folds) is not tuple
            or any(type(item) is not GateEvaluationFence for item in self.gates)
            or any(type(item) is not FoldPersistenceFence for item in self.folds)
            or self.gates != tuple(sorted(self.gates, key=_gate_fence_sort_key))
            or self.folds != tuple(sorted(self.folds, key=_fold_fence_sort_key))
            or len({item.evaluation_id for item in self.gates}) != len(self.gates)
            or len({item.key for item in self.folds}) != len(self.folds)
        ):
            raise _invalid(
                "experiment enqueue fence must be exact, unique, and canonical"
            )

    @classmethod
    def create(
        cls,
        *,
        gates: tuple[GateEvaluationRecord, ...],
        folds: tuple[FoldPersistenceSpec, ...],
    ) -> ExperimentEnqueueFence:
        """Seal complete gate and fold rows into their minimal enqueue identities."""
        if (
            cls is not ExperimentEnqueueFence
            or type(gates) is not tuple
            or type(folds) is not tuple
            or any(type(item) is not GateEvaluationRecord for item in gates)
            or any(type(item) is not FoldPersistenceSpec for item in folds)
        ):
            raise _invalid("enqueue fence sources must be exact gate and fold tuples")
        gate_fences = tuple(
            sorted(
                (
                    GateEvaluationFence(item.evaluation_id, item.payload_hash)
                    for item in gates
                ),
                key=_gate_fence_sort_key,
            )
        )
        fold_fences = tuple(
            sorted(
                (FoldPersistenceFence(item.key, item.payload_hash) for item in folds),
                key=_fold_fence_sort_key,
            )
        )
        return cls(gates=gate_fences, folds=fold_fences)
