"""Diagnostic and stability value objects for R3 walk-forward evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn, cast

from ditto_analysis.experiments import ContentHash, FoldId

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_values import (
    canonical_text,
    canonical_value,
    comparison_error,
    deep_freeze,
)
from ditto_application.processes.experiments._evidence_values import (
    finite as maybe_finite,
)
from ditto_application.processes.experiments.comparison import (
    EvidenceStatus,
)

_FOLD_VALUE_SIZE = 2
_REQUIRED_FOLD_COUNT = 2


def _walk_forward_error(reason: str, **details: object) -> NoReturn:
    raise AppProcessError(
        "walk-forward comparison evidence is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


def _finite(value: object) -> float:
    converted = maybe_finite(value)
    if converted is None:
        _walk_forward_error("non_finite_walk_forward_value")
    return converted


def _lineage(
    refs_value: object,
    hashes_value: object,
) -> tuple[tuple[str, ...], tuple[ContentHash, ...]]:
    if not isinstance(refs_value, Sequence) or isinstance(
        refs_value,
        (str, bytes, bytearray),
    ):
        comparison_error("invalid_evidence_refs")
    if not isinstance(hashes_value, Sequence) or isinstance(
        hashes_value,
        (str, bytes, bytearray),
    ):
        comparison_error("invalid_evidence_hashes")
    refs = tuple(
        canonical_text(item, "evidence_ref")
        for item in cast("Sequence[object]", refs_value)
    )
    raw_hashes = tuple(cast("Sequence[object]", hashes_value))
    if any(type(item) is not ContentHash for item in raw_hashes):
        comparison_error("invalid_evidence_hashes")
    hashes = cast("tuple[ContentHash, ...]", raw_hashes)
    if len(set(refs)) != len(refs):
        comparison_error("duplicate_evidence_ref")
    if len(refs) != len(hashes):
        comparison_error("evidence_lineage_length_mismatch")
    if len(set(zip(refs, hashes, strict=True))) != len(refs):
        comparison_error("duplicate_evidence_lineage_pair")
    return refs, hashes


@dataclass(frozen=True, slots=True)
class WalkForwardDiagnosticEvidence:
    """Per-fold values and exact artifact lineage for one diagnostic."""

    status: EvidenceStatus
    fold_values: tuple[tuple[FoldId, object], ...]
    reason: str | None
    evidence_refs: tuple[str, ...] = ()
    evidence_hashes: tuple[ContentHash, ...] = ()

    def __post_init__(self) -> None:
        """Freeze values and enforce complete evidence for evaluated results."""
        if type(self.status) is not EvidenceStatus:
            _walk_forward_error("invalid_diagnostic_status")
        normalized: list[tuple[FoldId, object]] = []
        for raw in tuple(self.fold_values):
            if (
                type(raw) is not tuple
                or len(raw) != _FOLD_VALUE_SIZE
                or type(raw[0]) is not FoldId
            ):
                _walk_forward_error("invalid_fold_diagnostic_values")
            normalized.append((raw[0], deep_freeze(raw[1])))
        if len({fold_id for fold_id, _ in normalized}) != len(normalized):
            _walk_forward_error("duplicate_fold_diagnostic_values")
        if self.status is EvidenceStatus.EVALUATED:
            if len(normalized) != _REQUIRED_FOLD_COUNT or self.reason is not None:
                _walk_forward_error("invalid_evaluated_walk_forward_diagnostic")
        elif self.reason is None:
            _walk_forward_error("not_evaluated_diagnostic_reason_required")
        try:
            refs, hashes = _lineage(self.evidence_refs, self.evidence_hashes)
        except AppProcessError:
            _walk_forward_error("invalid_diagnostic_evidence_identity")
        if self.status is EvidenceStatus.EVALUATED and (not refs or not hashes):
            _walk_forward_error("evaluated_evidence_source_required")
        object.__setattr__(self, "fold_values", tuple(normalized))
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)

    def canonical_payload(self) -> dict[str, object]:
        """Return a deterministic diagnostic evidence payload."""
        return {
            "evidence_hashes": [str(item) for item in self.evidence_hashes],
            "evidence_refs": list(self.evidence_refs),
            "fold_values": [
                {"fold_id": str(fold_id), "value": canonical_value(value)}
                for fold_id, value in self.fold_values
            ],
            "reason": self.reason,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class FoldStabilityEvidence:
    """Direction and range evidence retained across exact OOS folds."""

    status: EvidenceStatus
    fold_returns: tuple[tuple[FoldId, float], ...]
    direction_consistent: bool | None
    positive_fold_count: int
    negative_fold_count: int
    zero_fold_count: int
    return_range: float | None
    reason: str | None

    def __post_init__(self) -> None:
        """Validate fold values, sign counts, and evaluated-state completeness."""
        values = tuple(
            (fold_id, _finite(value)) for fold_id, value in self.fold_returns
        )
        if any(type(fold_id) is not FoldId for fold_id, _ in values):
            _walk_forward_error("invalid_fold_stability_identity")
        counts = (
            self.positive_fold_count,
            self.negative_fold_count,
            self.zero_fold_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            _walk_forward_error("invalid_fold_direction_counts")
        if self.status is EvidenceStatus.EVALUATED:
            if (
                len(values) != _REQUIRED_FOLD_COUNT
                or self.direction_consistent is None
                or self.return_range is None
                or self.reason is not None
                or sum(counts) != _REQUIRED_FOLD_COUNT
            ):
                _walk_forward_error("invalid_evaluated_fold_stability")
            object.__setattr__(self, "return_range", _finite(self.return_range))
        elif (
            self.direction_consistent is not None
            or self.return_range is not None
            or self.reason is None
            or any(counts)
        ):
            _walk_forward_error("invalid_not_evaluated_fold_stability")
        object.__setattr__(self, "fold_returns", values)

    def canonical_payload(self) -> dict[str, object]:
        """Return a deterministic stability evidence payload."""
        return {
            "direction_consistent": self.direction_consistent,
            "fold_returns": [
                {"fold_id": str(fold_id), "value": value}
                for fold_id, value in self.fold_returns
            ],
            "negative_fold_count": self.negative_fold_count,
            "positive_fold_count": self.positive_fold_count,
            "reason": self.reason,
            "return_range": self.return_range,
            "status": self.status.value,
            "zero_fold_count": self.zero_fold_count,
        }
