"""Dataset promotion assessment policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from ditto_data.catalog.metadata import DatasetMaturity, DatasetMetadata

__all__ = [
    "DatasetMaturityPromotion",
    "DatasetMaturityPromotionEvent",
    "DatasetMaturityPromotionHistoryReader",
    "DatasetMaturityPromotionReader",
    "DatasetMaturityPromotionRevocationReason",
    "DatasetMaturityPromotionRevoker",
    "DatasetMaturityPromotionWriter",
    "DatasetPromotionAssessment",
    "DatasetPromotionEvidence",
    "DatasetPromotionEvidenceReader",
    "DatasetPromotionEvidenceWriter",
    "DatasetPromotionStatus",
    "apply_dataset_maturity_promotion",
    "assess_dataset_promotion",
]

type DatasetPromotionStatus = Literal["not_applicable", "blocked", "ready"]
type DatasetMaturityPromotionEventAction = Literal["promoted", "revoked"]
type DatasetMaturityPromotionRevocationReason = Literal[
    "policy_regression",
    "failed_revalidation",
    "manual_override",
    "evidence_invalidated",
]

_PROMOTED_MATURITY: DatasetMaturity = "initial-focus"
_REVOCATION_REASONS: tuple[DatasetMaturityPromotionRevocationReason, ...] = (
    "policy_regression",
    "failed_revalidation",
    "manual_override",
    "evidence_invalidated",
)


@dataclass(frozen=True, slots=True)
class DatasetPromotionEvidence:
    """Evidence that one catalog-owned promotion criterion was reviewed."""

    criterion: str
    evidence_uri: str
    approved_by: str
    passed: bool = True
    notes: str | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate required evidence identity fields."""
        _validate_text("criterion", self.criterion)
        _validate_text("evidence_uri", self.evidence_uri)
        _validate_text("approved_by", self.approved_by)


@dataclass(frozen=True, slots=True)
class DatasetPromotionAssessment:
    """Read-only assessment of whether a dataset can be promoted."""

    dataset_id: str
    status: DatasetPromotionStatus
    required_criteria: tuple[str, ...]
    satisfied_criteria: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    rejected_criteria: tuple[str, ...]

    @property
    def is_promotable(self) -> bool:
        """Return whether all catalog-owned promotion criteria passed."""
        return self.status == "ready"


@dataclass(frozen=True, slots=True)
class DatasetMaturityPromotion:
    """Current metadata maturity promotion override for one dataset."""

    dataset_id: str
    previous_maturity: DatasetMaturity
    promoted_maturity: DatasetMaturity
    promoted_by: str
    promoted_at: datetime | None = None
    evidence_uri: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate promotion identity and the only supported transition."""
        _validate_text("dataset_id", self.dataset_id)
        _validate_text("promoted_by", self.promoted_by)
        if self.previous_maturity == self.promoted_maturity:
            msg = "maturity promotion must change maturity"
            raise ValueError(msg)
        if self.previous_maturity != "experimental":
            msg = "maturity promotion currently requires experimental source maturity"
            raise ValueError(msg)
        if self.promoted_maturity != _PROMOTED_MATURITY:
            msg = "maturity promotion currently targets initial-focus"
            raise ValueError(msg)
        if self.evidence_uri is not None:
            _validate_text("evidence_uri", self.evidence_uri)


@dataclass(frozen=True, slots=True)
class DatasetMaturityPromotionEvent:
    """Append-only audit event for dataset maturity promotion governance."""

    dataset_id: str
    action: DatasetMaturityPromotionEventAction
    previous_maturity: DatasetMaturity
    next_maturity: DatasetMaturity
    actor: str
    action_at: datetime | None = None
    evidence_uri: str | None = None
    revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate event identity and supported maturity transitions."""
        _validate_text("dataset_id", self.dataset_id)
        _validate_text("actor", self.actor)
        if self.action == "promoted":
            _validate_transition(
                previous_maturity=self.previous_maturity,
                next_maturity=self.next_maturity,
                expected_previous="experimental",
                expected_next=_PROMOTED_MATURITY,
            )
            if self.revocation_reason is not None:
                msg = "revocation_reason is only valid for revoked events"
                raise ValueError(msg)
        elif self.action == "revoked":
            _validate_transition(
                previous_maturity=self.previous_maturity,
                next_maturity=self.next_maturity,
                expected_previous=_PROMOTED_MATURITY,
                expected_next="experimental",
            )
            _validate_revocation_reason(self.revocation_reason)
        else:
            msg = f"Invalid maturity promotion action: {self.action!r}"
            raise ValueError(msg)
        if self.evidence_uri is not None:
            _validate_text("evidence_uri", self.evidence_uri)


@runtime_checkable
class DatasetPromotionEvidenceReader(Protocol):
    """Read-only access to dataset promotion evidence."""

    def list_dataset_evidence(
        self,
        dataset_id: str,
    ) -> tuple[DatasetPromotionEvidence, ...]:
        """Return persisted promotion evidence for one dataset."""
        ...


@runtime_checkable
class DatasetPromotionEvidenceWriter(Protocol):
    """Write access to dataset promotion evidence."""

    def upsert_dataset_evidence(
        self,
        dataset_id: str,
        evidence: DatasetPromotionEvidence,
    ) -> None:
        """Insert or replace evidence for a dataset criterion."""
        ...


@runtime_checkable
class DatasetMaturityPromotionReader(Protocol):
    """Read access to current dataset maturity promotion overrides."""

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        """Return the current promotion override for one dataset, if any."""
        ...


@runtime_checkable
class DatasetMaturityPromotionWriter(Protocol):
    """Write access to dataset maturity promotion overrides."""

    def upsert_dataset_maturity_promotion(
        self,
        promotion: DatasetMaturityPromotion,
    ) -> None:
        """Insert or replace a dataset maturity promotion override."""
        ...


@runtime_checkable
class DatasetMaturityPromotionHistoryReader(Protocol):
    """Read access to append-only maturity promotion audit events."""

    def list_dataset_maturity_promotion_events(
        self,
        dataset_id: str,
    ) -> tuple[DatasetMaturityPromotionEvent, ...]:
        """Return promotion governance events for one dataset."""
        ...


@runtime_checkable
class DatasetMaturityPromotionRevoker(Protocol):
    """Revoke access for current dataset maturity promotion overrides."""

    def revoke_dataset_maturity_promotion(
        self,
        dataset_id: str,
        *,
        revoked_by: str,
        revoked_at: datetime,
        revocation_reason: DatasetMaturityPromotionRevocationReason,
        notes: str | None = None,
    ) -> DatasetMaturityPromotionEvent:
        """Remove a current promotion override and append a revoke event."""
        ...


def apply_dataset_maturity_promotion(
    metadata: DatasetMetadata,
    promotion: DatasetMaturityPromotion,
) -> DatasetMetadata:
    """Return metadata with an approved maturity promotion override applied."""
    if metadata.dataset_id != promotion.dataset_id:
        msg = (
            "maturity promotion dataset_id does not match metadata: "
            f"{promotion.dataset_id!r} != {metadata.dataset_id!r}"
        )
        raise ValueError(msg)
    return replace(
        metadata,
        maturity=promotion.promoted_maturity,
        promotion_criteria=(),
    )


def assess_dataset_promotion(
    metadata: DatasetMetadata,
    evidence: tuple[DatasetPromotionEvidence, ...],
) -> DatasetPromotionAssessment:
    """Assess promotion readiness against data-owned dataset metadata."""
    required = metadata.promotion_criteria
    if not required:
        return DatasetPromotionAssessment(
            dataset_id=metadata.dataset_id,
            status="not_applicable",
            required_criteria=(),
            satisfied_criteria=(),
            missing_criteria=(),
            rejected_criteria=(),
        )

    evidence_by_criterion = _validate_evidence(required, evidence)
    satisfied = tuple(
        criterion
        for criterion in required
        if (item := evidence_by_criterion.get(criterion)) is not None and item.passed
    )
    rejected = tuple(
        criterion
        for criterion in required
        if (item := evidence_by_criterion.get(criterion)) is not None
        and not item.passed
    )
    missing = tuple(
        criterion for criterion in required if criterion not in evidence_by_criterion
    )
    status: DatasetPromotionStatus = (
        "ready" if len(satisfied) == len(required) and not rejected else "blocked"
    )
    return DatasetPromotionAssessment(
        dataset_id=metadata.dataset_id,
        status=status,
        required_criteria=required,
        satisfied_criteria=satisfied,
        missing_criteria=missing,
        rejected_criteria=rejected,
    )


def _validate_evidence(
    required: tuple[str, ...],
    evidence: tuple[DatasetPromotionEvidence, ...],
) -> dict[str, DatasetPromotionEvidence]:
    required_set = set(required)
    evidence_by_criterion: dict[str, DatasetPromotionEvidence] = {}
    for item in evidence:
        if item.criterion not in required_set:
            msg = f"promotion evidence criterion is not declared: {item.criterion!r}"
            raise ValueError(msg)
        if item.criterion in evidence_by_criterion:
            msg = f"duplicate promotion evidence criterion: {item.criterion!r}"
            raise ValueError(msg)
        evidence_by_criterion[item.criterion] = item
    return evidence_by_criterion


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        msg = f"Invalid {field}: {value!r}"
        raise ValueError(msg)


def _validate_revocation_reason(
    reason: DatasetMaturityPromotionRevocationReason | None,
) -> None:
    if reason is None:
        msg = "revocation_reason is required for revoked events"
        raise ValueError(msg)
    if reason not in _REVOCATION_REASONS:
        msg = f"Invalid revocation_reason: {reason!r}"
        raise ValueError(msg)


def _validate_transition(
    *,
    previous_maturity: DatasetMaturity,
    next_maturity: DatasetMaturity,
    expected_previous: DatasetMaturity,
    expected_next: DatasetMaturity,
) -> None:
    if previous_maturity != expected_previous or next_maturity != expected_next:
        msg = (
            "invalid maturity promotion transition: "
            f"{previous_maturity!r} -> {next_maturity!r}"
        )
        raise ValueError(msg)
