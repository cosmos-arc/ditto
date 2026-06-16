"""
Dataset promotion evidence collection (read-only).

Gathers objective evidence for a dataset's ``DatasetMetadata.promotion_criteria``
so a reviewer can submit it through ``ReviewDatasetPromotionEvidenceHandler``.

Hard boundary (per data/CLAUDE.md + application/CLAUDE.md): this module never
decides promotion readiness and never writes promotion state. It measures what
can be measured (catalog coverage, metadata declarations) and flags
human-owned criteria (catalog-backed test pass) for reviewer review. Final
pass/fail is always a reviewer decision recorded through the application
command handler.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ditto_data.catalog.contracts import DataCatalogEntry, DataCatalogReader
from ditto_data.catalog.metadata import DatasetMetadata, default_dataset_metadata

from ditto_application.exceptions import AppQueryError

__all__ = [
    "CriterionEvidence",
    "CriterionStatus",
    "PromotionEvidenceCollector",
    "PromotionEvidenceReport",
]

type CriterionStatus = Literal["measured", "needs_review"]

_COVERAGE_KEYWORD = "coverage"
_DOCUMENTATION_KEYWORD = "runtime owner"
_TEST_KEYWORD = "catalog-backed"


@dataclass(frozen=True, slots=True)
class CriterionEvidence:
    """
    Objective evidence gathered for one promotion criterion.

    ``status`` reports whether the tool could *measure* the criterion, not a
    promotion decision. ``measured`` means objective material was collected;
    ``needs_review`` means a human reviewer must supply the evidence. The
    final pass/fail is always a reviewer decision recorded via
    ``ReviewDatasetPromotionEvidenceHandler``.
    """

    criterion: str
    status: CriterionStatus
    materials: tuple[str, ...]
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionEvidenceReport:
    """Structured evidence report for one dataset's promotion criteria."""

    dataset_id: str
    generated_at: datetime
    maturity: str
    criteria: tuple[CriterionEvidence, ...]

    @property
    def all_measured(self) -> bool:
        """Return True when every criterion was measurable (not a pass decision)."""
        return all(item.status == "measured" for item in self.criteria)


class PromotionEvidenceCollector:
    """
    Gather objective evidence for a dataset's promotion criteria.

    Read-only and never decides promotion readiness: measures what can be
    measured (catalog coverage, metadata declarations) and flags human-owned
    criteria (test pass) for reviewer review.
    """

    def __init__(
        self,
        catalog_reader: DataCatalogReader | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._now = now or _utcnow

    def collect(
        self,
        dataset_id: str,
        *,
        metadata: DatasetMetadata | None = None,
    ) -> PromotionEvidenceReport:
        """Collect evidence for ``dataset_id`` against its promotion criteria."""
        resolved = (
            metadata
            if metadata is not None
            else default_dataset_metadata().get(dataset_id)
        )
        if resolved is None:
            msg = f"Unknown dataset: {dataset_id}"
            raise AppQueryError(msg)
        criteria = tuple(
            self._collect_criterion(dataset_id, resolved, criterion)
            for criterion in resolved.promotion_criteria
        )
        return PromotionEvidenceReport(
            dataset_id=dataset_id,
            generated_at=self._now(),
            maturity=resolved.maturity,
            criteria=criteria,
        )

    def _collect_criterion(
        self,
        dataset_id: str,
        metadata: DatasetMetadata,
        criterion: str,
    ) -> CriterionEvidence:
        if _DOCUMENTATION_KEYWORD in criterion:
            return _collect_documentation(metadata, criterion)
        if _COVERAGE_KEYWORD in criterion:
            return self._collect_coverage(dataset_id, criterion)
        if _TEST_KEYWORD in criterion:
            return _collect_test_pass(criterion)
        return CriterionEvidence(
            criterion=criterion,
            status="needs_review",
            materials=("criterion not auto-measurable",),
            suggestion="Reviewer must supply evidence for this criterion.",
        )

    def _collect_coverage(
        self,
        dataset_id: str,
        criterion: str,
    ) -> CriterionEvidence:
        if self._catalog_reader is None:
            return CriterionEvidence(
                criterion=criterion,
                status="needs_review",
                materials=("catalog reader not available",),
                suggestion="Provide a DataCatalogReader to measure dataset coverage.",
            )
        assets = tuple(
            entry
            for entry in self._catalog_reader.list_assets()
            if entry.asset.dataset_id == dataset_id
        )
        if not assets:
            return CriterionEvidence(
                criterion=criterion,
                status="needs_review",
                materials=("no catalog assets registered for dataset",),
                suggestion="Ingest data so catalog assets are registered.",
            )
        materials = (
            f"{len(assets)} catalog asset(s)",
            *(_describe_asset(entry) for entry in assets),
        )
        return CriterionEvidence(
            criterion=criterion,
            status="measured",
            materials=materials,
        )


def _collect_documentation(
    metadata: DatasetMetadata,
    criterion: str,
) -> CriterionEvidence:
    """Measure whether runtime owner / freshness SLA / failover are declared."""
    sla_status = "declared" if metadata.freshness_sla_hours else "missing"
    declared = (
        f"default_source={'declared' if metadata.default_source else 'missing'}",
        f"freshness_sla_hours={sla_status}",
        f"supported_sources={len(metadata.supported_sources)} source(s)",
    )
    complete = (
        bool(metadata.default_source)
        and metadata.freshness_sla_hours is not None
        and len(metadata.supported_sources) >= 1
    )
    return CriterionEvidence(
        criterion=criterion,
        status="measured" if complete else "needs_review",
        materials=declared,
        suggestion=None if complete else "Declare missing runtime metadata fields.",
    )


def _collect_test_pass(criterion: str) -> CriterionEvidence:
    """The tool must not auto-decide test pass; reviewer owns this criterion."""
    return CriterionEvidence(
        criterion=criterion,
        status="needs_review",
        materials=("test pass cannot be auto-decided by the tool",),
        suggestion=(
            "Reviewer must supply catalog-backed runtime/read-model test pass "
            "evidence (e.g. CI golden-e2e run)."
        ),
    )


def _describe_asset(entry: DataCatalogEntry) -> str:
    freshness = (
        entry.freshness_at.date().isoformat() if entry.freshness_at else "unknown"
    )
    rows = entry.schema.row_count
    return (
        f"namespace={entry.asset.namespace} source={entry.source} "
        f"freshness={freshness} rows={rows}"
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)
