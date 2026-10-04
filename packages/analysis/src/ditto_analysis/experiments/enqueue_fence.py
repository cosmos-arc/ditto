"""
Canonical payload identities bound by holdout preflight authority.

#448 起 ExperimentEnqueueFence（enqueue 时点集比对）已删除；两个值类
仍是 preflight 权威绑定的载荷身份类型。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    FoldKey,
)

__all__ = [
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


def _fold_fence_sort_key(value: FoldPersistenceFence) -> tuple[bytes, bytes, bytes]:
    return (
        _utf8(str(value.key.experiment_id)),
        _utf8(str(value.key.candidate_id)),
        _utf8(str(value.key.fold_id)),
    )
