"""Unit tests for dataset promotion review commands."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_application.commands.catalog import (
    DatasetMaturityPromotionRevokeCommand,
    DatasetPromotionReviewCommand,
    ReviewDatasetPromotionEvidenceHandler,
    RevokeDatasetMaturityPromotionHandler,
)
from ditto_application.exceptions import AppCommandError
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionEvent,
    DatasetPromotionEvidence,
)


class _PromotionEvidenceStore:
    def __init__(
        self,
        evidence_by_dataset: dict[str, tuple[DatasetPromotionEvidence, ...]]
        | None = None,
    ) -> None:
        self._evidence_by_dataset = evidence_by_dataset or {}
        self.writes: list[tuple[str, DatasetPromotionEvidence]] = []

    def upsert_dataset_evidence(
        self,
        dataset_id: str,
        evidence: DatasetPromotionEvidence,
    ) -> None:
        self.writes.append((dataset_id, evidence))
        existing = tuple(
            item
            for item in self._evidence_by_dataset.get(dataset_id, ())
            if item.criterion != evidence.criterion
        )
        self._evidence_by_dataset[dataset_id] = (*existing, evidence)

    def list_dataset_evidence(
        self,
        dataset_id: str,
    ) -> tuple[DatasetPromotionEvidence, ...]:
        return self._evidence_by_dataset.get(dataset_id, ())


class _MaturityPromotionStore:
    def __init__(
        self,
        promotions_by_dataset: dict[str, DatasetMaturityPromotion] | None = None,
    ) -> None:
        self._promotions_by_dataset = promotions_by_dataset or {}
        self.writes: list[DatasetMaturityPromotion] = []
        self.revokes: list[tuple[str, str, datetime, str, str | None]] = []

    def upsert_dataset_maturity_promotion(
        self,
        promotion: DatasetMaturityPromotion,
    ) -> None:
        self.writes.append(promotion)
        self._promotions_by_dataset[promotion.dataset_id] = promotion

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        return self._promotions_by_dataset.get(dataset_id)

    def revoke_dataset_maturity_promotion(
        self,
        dataset_id: str,
        *,
        revoked_by: str,
        revoked_at: datetime,
        revocation_reason: str,
        notes: str | None = None,
    ) -> DatasetMaturityPromotionEvent:
        current = self._promotions_by_dataset.pop(dataset_id)
        self.revokes.append(
            (dataset_id, revoked_by, revoked_at, revocation_reason, notes)
        )
        return DatasetMaturityPromotionEvent(
            dataset_id=dataset_id,
            action="revoked",
            previous_maturity=current.promoted_maturity,
            next_maturity=current.previous_maturity,
            actor=revoked_by,
            action_at=revoked_at,
            evidence_uri=current.evidence_uri,
            revocation_reason=revocation_reason,
            notes=notes,
        )


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 30, tzinfo=UTC)


class TestReviewDatasetPromotionEvidenceHandler:
    """Promotion review writes durable evidence and returns reassessment."""

    def test_review_writes_approved_evidence_and_returns_ready_assessment(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        existing = tuple(
            DatasetPromotionEvidence(
                criterion=criterion,
                evidence_uri=f"ditto://evidence/stock_daily/{index}",
                approved_by="architecture-review",
            )
            for index, criterion in enumerate(metadata.promotion_criteria[:-1], start=1)
        )
        store = _PromotionEvidenceStore({"stock_daily": existing})
        maturity_store = _MaturityPromotionStore()
        handler = ReviewDatasetPromotionEvidenceHandler(
            evidence_writer=store,
            evidence_reader=store,
            maturity_promotion_writer=maturity_store,
            maturity_promotion_reader=maturity_store,
            now=_now,
        )
        criterion = metadata.promotion_criteria[-1]

        result = handler.handle(
            DatasetPromotionReviewCommand(
                dataset_id="stock_daily",
                criterion=criterion,
                evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                reviewed_by="architecture-review",
                passed=True,
                notes="runtime tests passed",
            )
        )

        assert store.writes == [
            (
                "stock_daily",
                DatasetPromotionEvidence(
                    criterion=criterion,
                    evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                    approved_by="architecture-review",
                    passed=True,
                    notes="runtime tests passed",
                    reviewed_at=_now(),
                ),
            )
        ]
        assert result.dataset_id == "stock_daily"
        assert result.reviewed_criterion == criterion
        assert result.promotion_status == "ready"
        assert result.missing_criteria == ()
        assert result.rejected_criteria == ()
        assert result.metadata_promoted is True
        assert result.dataset_maturity_before == "experimental"
        assert result.dataset_maturity_after == "initial-focus"
        assert maturity_store.writes == [
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=_now(),
                evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                notes="runtime tests passed",
            )
        ]

    def test_review_rejects_unknown_dataset_before_writing(self) -> None:
        store = _PromotionEvidenceStore()
        maturity_store = _MaturityPromotionStore()
        handler = ReviewDatasetPromotionEvidenceHandler(
            evidence_writer=store,
            evidence_reader=store,
            maturity_promotion_writer=maturity_store,
            maturity_promotion_reader=maturity_store,
            now=_now,
        )

        with pytest.raises(AppCommandError, match="Unknown dataset"):
            handler.handle(
                DatasetPromotionReviewCommand(
                    dataset_id="unknown_dataset",
                    criterion="complete PIT/replay coverage for the dataset",
                    evidence_uri="ditto://evidence/unknown",
                    reviewed_by="architecture-review",
                )
            )

        assert store.writes == []
        assert maturity_store.writes == []


class TestRevokeDatasetMaturityPromotionHandler:
    """Promotion reversal removes the current maturity override."""

    def test_revoke_existing_promotion_returns_maturity_transition(self) -> None:
        store = _MaturityPromotionStore(
            {
                "stock_daily": DatasetMaturityPromotion(
                    dataset_id="stock_daily",
                    previous_maturity="experimental",
                    promoted_maturity="initial-focus",
                    promoted_by="architecture-review",
                    promoted_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
                    evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                    notes="runtime tests passed",
                )
            }
        )
        handler = RevokeDatasetMaturityPromotionHandler(
            maturity_promotion_reader=store,
            maturity_promotion_revoker=store,
            now=_now,
        )

        result = handler.handle(
            DatasetMaturityPromotionRevokeCommand(
                dataset_id="stock_daily",
                revoked_by="architecture-review",
                revocation_reason="failed_revalidation",
                notes="PIT regression reopened promotion",
            )
        )

        assert result.dataset_id == "stock_daily"
        assert result.revoked_by == "architecture-review"
        assert result.revoked_at == _now()
        assert result.dataset_maturity_before == "initial-focus"
        assert result.dataset_maturity_after == "experimental"
        assert result.evidence_uri == "ditto://evidence/stock_daily/runtime-tests"
        assert result.revocation_reason == "failed_revalidation"
        assert store.get_dataset_maturity_promotion("stock_daily") is None
        assert store.revokes == [
            (
                "stock_daily",
                "architecture-review",
                _now(),
                "failed_revalidation",
                "PIT regression reopened promotion",
            )
        ]

    def test_revoke_rejects_unknown_dataset_before_mutation(self) -> None:
        store = _MaturityPromotionStore()
        handler = RevokeDatasetMaturityPromotionHandler(
            maturity_promotion_reader=store,
            maturity_promotion_revoker=store,
            now=_now,
        )

        with pytest.raises(AppCommandError, match="Unknown dataset"):
            handler.handle(
                DatasetMaturityPromotionRevokeCommand(
                    dataset_id="unknown_dataset",
                    revoked_by="architecture-review",
                    revocation_reason="manual_override",
                )
            )

        assert store.revokes == []

    def test_revoke_rejects_dataset_without_current_promotion(self) -> None:
        store = _MaturityPromotionStore()
        handler = RevokeDatasetMaturityPromotionHandler(
            maturity_promotion_reader=store,
            maturity_promotion_revoker=store,
            now=_now,
        )

        with pytest.raises(AppCommandError, match="No active maturity promotion"):
            handler.handle(
                DatasetMaturityPromotionRevokeCommand(
                    dataset_id="stock_daily",
                    revoked_by="architecture-review",
                    revocation_reason="manual_override",
                )
            )

        assert store.revokes == []

    def test_review_rejects_criteria_not_declared_by_dataset_metadata(self) -> None:
        store = _PromotionEvidenceStore()
        maturity_store = _MaturityPromotionStore()
        handler = ReviewDatasetPromotionEvidenceHandler(
            evidence_writer=store,
            evidence_reader=store,
            maturity_promotion_writer=maturity_store,
            maturity_promotion_reader=maturity_store,
            now=_now,
        )

        with pytest.raises(AppCommandError, match="not declared"):
            handler.handle(
                DatasetPromotionReviewCommand(
                    dataset_id="stock_daily",
                    criterion="spreadsheet says ok",
                    evidence_uri="ditto://evidence/stock_daily/spreadsheet",
                    reviewed_by="architecture-review",
                )
            )

        assert store.writes == []
        assert maturity_store.writes == []

    def test_review_rejects_initial_focus_dataset_without_promotion_criteria(
        self,
    ) -> None:
        store = _PromotionEvidenceStore()
        maturity_store = _MaturityPromotionStore()
        handler = ReviewDatasetPromotionEvidenceHandler(
            evidence_writer=store,
            evidence_reader=store,
            maturity_promotion_writer=maturity_store,
            maturity_promotion_reader=maturity_store,
            now=_now,
        )

        with pytest.raises(
            AppCommandError,
            match="does not declare promotion criteria",
        ):
            handler.handle(
                DatasetPromotionReviewCommand(
                    dataset_id="etf_daily",
                    criterion="complete PIT/replay coverage for the dataset",
                    evidence_uri="ditto://evidence/etf_daily/not-needed",
                    reviewed_by="architecture-review",
                )
            )

        assert store.writes == []
        assert maturity_store.writes == []
