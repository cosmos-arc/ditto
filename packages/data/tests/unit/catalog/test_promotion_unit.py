"""Unit tests for dataset promotion assessment policy."""

from __future__ import annotations

import pytest
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionEvent,
    DatasetPromotionEvidence,
    apply_dataset_maturity_promotion,
    assess_dataset_promotion,
)


class TestAssessDatasetPromotion:
    """Promotion readiness must be data-owned and evidence-based."""

    def test_experimental_dataset_without_evidence_is_blocked(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]

        assessment = assess_dataset_promotion(metadata, ())

        assert assessment.dataset_id == "stock_daily"
        assert assessment.status == "blocked"
        assert assessment.is_promotable is False
        assert assessment.required_criteria == metadata.promotion_criteria
        assert assessment.satisfied_criteria == ()
        assert assessment.missing_criteria == metadata.promotion_criteria
        assert assessment.rejected_criteria == ()

    def test_complete_approved_evidence_marks_experimental_dataset_ready(
        self,
    ) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        evidence = tuple(
            DatasetPromotionEvidence(
                criterion=criterion,
                evidence_uri=f"ditto://evidence/stock_daily/{index}",
                approved_by="architecture-review",
            )
            for index, criterion in enumerate(metadata.promotion_criteria, start=1)
        )

        assessment = assess_dataset_promotion(metadata, evidence)

        assert assessment.status == "ready"
        assert assessment.is_promotable is True
        assert assessment.satisfied_criteria == metadata.promotion_criteria
        assert assessment.missing_criteria == ()
        assert assessment.rejected_criteria == ()

    def test_rejected_evidence_blocks_promotion(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        rejected = metadata.promotion_criteria[0]
        evidence = (
            DatasetPromotionEvidence(
                criterion=rejected,
                evidence_uri="ditto://evidence/stock_daily/rejected",
                approved_by="architecture-review",
                passed=False,
            ),
        )

        assessment = assess_dataset_promotion(metadata, evidence)

        assert assessment.status == "blocked"
        assert assessment.is_promotable is False
        assert assessment.rejected_criteria == (rejected,)
        assert rejected not in assessment.missing_criteria

    def test_unknown_evidence_criterion_is_rejected(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        evidence = (
            DatasetPromotionEvidence(
                criterion="untracked spreadsheet says ok",
                evidence_uri="ditto://evidence/stock_daily/unknown",
                approved_by="architecture-review",
            ),
        )

        with pytest.raises(ValueError, match="not declared"):
            assess_dataset_promotion(metadata, evidence)

    def test_duplicate_evidence_criterion_is_rejected(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        criterion = metadata.promotion_criteria[0]
        evidence = (
            DatasetPromotionEvidence(
                criterion=criterion,
                evidence_uri="ditto://evidence/stock_daily/one",
                approved_by="architecture-review",
            ),
            DatasetPromotionEvidence(
                criterion=criterion,
                evidence_uri="ditto://evidence/stock_daily/two",
                approved_by="architecture-review",
            ),
        )

        with pytest.raises(ValueError, match="duplicate"):
            assess_dataset_promotion(metadata, evidence)

    def test_initial_focus_dataset_is_not_applicable(self) -> None:
        metadata = default_dataset_metadata()["etf_daily"]

        assessment = assess_dataset_promotion(metadata, ())

        assert assessment.status == "not_applicable"
        assert assessment.is_promotable is False
        assert assessment.required_criteria == ()
        assert assessment.missing_criteria == ()


class TestApplyDatasetMaturityPromotion:
    """Approved promotion metadata must resolve through data-owned policy."""

    def test_promoted_metadata_becomes_initial_focus_without_criteria(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        promotion = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
        )

        promoted = apply_dataset_maturity_promotion(metadata, promotion)

        assert promoted.dataset_id == "stock_daily"
        assert promoted.maturity == "initial-focus"
        assert promoted.promotion_criteria == ()
        assert metadata.maturity == "experimental"
        assert metadata.promotion_criteria

    def test_rejects_mismatched_dataset_promotion(self) -> None:
        metadata = default_dataset_metadata()["stock_daily"]
        promotion = DatasetMaturityPromotion(
            dataset_id="stock_basic",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
        )

        with pytest.raises(ValueError, match="dataset_id"):
            apply_dataset_maturity_promotion(metadata, promotion)


class TestDatasetMaturityPromotionEvent:
    """Promotion governance events must carry structured audit semantics."""

    def test_revoked_event_requires_structured_revocation_reason(self) -> None:
        with pytest.raises(ValueError, match="revocation_reason"):
            DatasetMaturityPromotionEvent(
                dataset_id="stock_daily",
                action="revoked",
                previous_maturity="initial-focus",
                next_maturity="experimental",
                actor="architecture-review",
            )
