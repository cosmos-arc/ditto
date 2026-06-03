"""Catalog governance command handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionReader,
    DatasetMaturityPromotionRevocationReason,
    DatasetMaturityPromotionRevoker,
    DatasetMaturityPromotionWriter,
    DatasetPromotionEvidence,
    DatasetPromotionEvidenceReader,
    DatasetPromotionEvidenceWriter,
    DatasetPromotionStatus,
    apply_dataset_maturity_promotion,
    assess_dataset_promotion,
)

from ditto_application.exceptions import AppCommandError

__all__ = [
    "DatasetMaturityPromotionRevokeCommand",
    "DatasetMaturityPromotionRevokeResult",
    "DatasetPromotionReviewCommand",
    "DatasetPromotionReviewResult",
    "ReviewDatasetPromotionEvidenceHandler",
    "RevokeDatasetMaturityPromotionHandler",
]


@dataclass(frozen=True, slots=True)
class DatasetPromotionReviewCommand:
    """Reviewer decision for one dataset promotion criterion."""

    dataset_id: str
    criterion: str
    evidence_uri: str
    reviewed_by: str
    passed: bool = True
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetPromotionReviewResult:
    """Result returned after writing reviewer evidence and reassessing."""

    dataset_id: str
    reviewed_criterion: str
    evidence_uri: str
    reviewed_by: str
    passed: bool
    reviewed_at: datetime
    promotion_status: DatasetPromotionStatus
    missing_criteria: tuple[str, ...]
    satisfied_criteria: tuple[str, ...]
    rejected_criteria: tuple[str, ...]
    metadata_promoted: bool
    dataset_maturity_before: str
    dataset_maturity_after: str


@dataclass(frozen=True, slots=True)
class DatasetMaturityPromotionRevokeCommand:
    """Operator request to revoke the current dataset maturity promotion."""

    dataset_id: str
    revoked_by: str
    revocation_reason: DatasetMaturityPromotionRevocationReason
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetMaturityPromotionRevokeResult:
    """Result returned after revoking a maturity promotion override."""

    dataset_id: str
    revoked_by: str
    revoked_at: datetime
    dataset_maturity_before: str
    dataset_maturity_after: str
    evidence_uri: str | None = None
    revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    notes: str | None = None


class ReviewDatasetPromotionEvidenceHandler:
    """Persist reviewer evidence and return the resulting promotion assessment."""

    def __init__(
        self,
        evidence_writer: DatasetPromotionEvidenceWriter,
        evidence_reader: DatasetPromotionEvidenceReader,
        maturity_promotion_writer: DatasetMaturityPromotionWriter,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._evidence_writer = evidence_writer
        self._evidence_reader = evidence_reader
        self._maturity_promotion_writer = maturity_promotion_writer
        self._maturity_promotion_reader = maturity_promotion_reader
        self._now = now or _utcnow

    def handle(
        self,
        command: DatasetPromotionReviewCommand,
    ) -> DatasetPromotionReviewResult:
        """Write one reviewer decision and return a fresh assessment."""
        metadata = default_dataset_metadata().get(command.dataset_id)
        if metadata is None:
            raise AppCommandError(
                f"Unknown dataset: {command.dataset_id}",
                command="review_dataset_promotion",
                dataset_id=command.dataset_id,
            )
        if not metadata.promotion_criteria:
            raise AppCommandError(
                f"Dataset does not declare promotion criteria: {command.dataset_id}",
                command="review_dataset_promotion",
                dataset_id=command.dataset_id,
            )
        if command.criterion not in metadata.promotion_criteria:
            raise AppCommandError(
                f"Promotion criterion is not declared for dataset: {command.criterion}",
                command="review_dataset_promotion",
                dataset_id=command.dataset_id,
                criterion=command.criterion,
            )

        reviewed_at = self._now()
        evidence = DatasetPromotionEvidence(
            criterion=command.criterion,
            evidence_uri=command.evidence_uri,
            approved_by=command.reviewed_by,
            passed=command.passed,
            notes=command.notes,
            reviewed_at=reviewed_at,
        )
        self._evidence_writer.upsert_dataset_evidence(command.dataset_id, evidence)
        assessment = assess_dataset_promotion(
            metadata,
            self._evidence_reader.list_dataset_evidence(command.dataset_id),
        )
        metadata_promoted = False
        dataset_maturity_after = metadata.maturity
        if assessment.is_promotable:
            promotion = DatasetMaturityPromotion(
                dataset_id=command.dataset_id,
                previous_maturity=metadata.maturity,
                promoted_maturity="initial-focus",
                promoted_by=command.reviewed_by,
                promoted_at=reviewed_at,
                evidence_uri=command.evidence_uri,
                notes=command.notes,
            )
            self._maturity_promotion_writer.upsert_dataset_maturity_promotion(promotion)
            promoted_metadata = apply_dataset_maturity_promotion(metadata, promotion)
            dataset_maturity_after = promoted_metadata.maturity
            metadata_promoted = True
        else:
            existing_promotion = (
                self._maturity_promotion_reader.get_dataset_maturity_promotion(
                    command.dataset_id
                )
            )
            if existing_promotion is not None:
                promoted_metadata = apply_dataset_maturity_promotion(
                    metadata,
                    existing_promotion,
                )
                dataset_maturity_after = promoted_metadata.maturity
        return DatasetPromotionReviewResult(
            dataset_id=command.dataset_id,
            reviewed_criterion=command.criterion,
            evidence_uri=command.evidence_uri,
            reviewed_by=command.reviewed_by,
            passed=command.passed,
            reviewed_at=reviewed_at,
            promotion_status=assessment.status,
            missing_criteria=assessment.missing_criteria,
            satisfied_criteria=assessment.satisfied_criteria,
            rejected_criteria=assessment.rejected_criteria,
            metadata_promoted=metadata_promoted,
            dataset_maturity_before=metadata.maturity,
            dataset_maturity_after=dataset_maturity_after,
        )


class RevokeDatasetMaturityPromotionHandler:
    """Remove the current metadata maturity promotion override for one dataset."""

    def __init__(
        self,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
        maturity_promotion_revoker: DatasetMaturityPromotionRevoker,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._maturity_promotion_reader = maturity_promotion_reader
        self._maturity_promotion_revoker = maturity_promotion_revoker
        self._now = now or _utcnow

    def handle(
        self,
        command: DatasetMaturityPromotionRevokeCommand,
    ) -> DatasetMaturityPromotionRevokeResult:
        """Revoke a current maturity promotion override."""
        if command.dataset_id not in default_dataset_metadata():
            raise AppCommandError(
                f"Unknown dataset: {command.dataset_id}",
                command="revoke_dataset_maturity_promotion",
                dataset_id=command.dataset_id,
            )

        current_promotion = (
            self._maturity_promotion_reader.get_dataset_maturity_promotion(
                command.dataset_id
            )
        )
        if current_promotion is None:
            raise AppCommandError(
                f"No active maturity promotion: {command.dataset_id}",
                command="revoke_dataset_maturity_promotion",
                dataset_id=command.dataset_id,
            )

        revoked_at = self._now()
        event = self._maturity_promotion_revoker.revoke_dataset_maturity_promotion(
            command.dataset_id,
            revoked_by=command.revoked_by,
            revoked_at=revoked_at,
            revocation_reason=command.revocation_reason,
            notes=command.notes,
        )
        return DatasetMaturityPromotionRevokeResult(
            dataset_id=event.dataset_id,
            revoked_by=event.actor,
            revoked_at=revoked_at,
            dataset_maturity_before=event.previous_maturity,
            dataset_maturity_after=event.next_maturity,
            evidence_uri=event.evidence_uri,
            revocation_reason=event.revocation_reason,
            notes=event.notes,
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)
