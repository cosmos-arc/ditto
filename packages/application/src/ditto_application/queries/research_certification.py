"""Read-only adapter from R2 readiness evidence to R3 certification probes."""

from __future__ import annotations

from datetime import date

from ditto_analysis.research.catalog_service import ResearchCatalogService

from ditto_application.queries.data_readiness import (
    DataReadinessQueryFacade,
    DatasetReadinessRequirement,
)
from ditto_application.research_certification_contracts import (
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchSnapshotEvidence,
)

__all__ = ["DataReadinessCertificationProbe"]


class DataReadinessCertificationProbe:
    """Adapt the existing R2 readiness facade to the R3 fixed profile."""

    def __init__(
        self,
        facade: DataReadinessQueryFacade,
        research_catalog: ResearchCatalogService,
    ) -> None:
        self._facade = facade
        self._research_catalog = research_catalog

    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        """Assess exact certification evidence without mutating catalog state."""
        report = self._facade.assess(
            profile=request.profile,
            requirements=tuple(
                DatasetReadinessRequirement(
                    dataset_id=item.dataset_id,
                    required_from=request.required_from,
                    required_to=request.required_to,
                    expected_snapshot_ids=item.expected_snapshot_ids,
                    requires_pit_universe=item.requires_pit_universe,
                )
                for item in request.requirements
            ),
        )
        report_ids = tuple(
            item.certification_report_id
            for item in report.datasets
            if item.certification_report_id is not None
        )
        reasons = tuple(
            sorted({reason for item in report.datasets for reason in item.reason_codes})
        )
        snapshot_record = self._research_catalog.get_dataset_snapshot(
            request.snapshot_identity.snapshot_id
        )
        snapshot_evidence: ResearchSnapshotEvidence | None = None
        snapshot_reasons = list(reasons)
        if snapshot_record is None:
            snapshot_reasons.append("RESEARCH_SNAPSHOT_MISSING")
        else:
            try:
                snapshot_evidence = ResearchSnapshotEvidence(
                    snapshot_id=snapshot_record.snapshot_id,
                    dataset_id=snapshot_record.dataset_id,
                    manifest_hash=snapshot_record.manifest_hash,
                    source_snapshot_ids=snapshot_record.source_snapshot_ids,
                    snapshot_start=date.fromisoformat(snapshot_record.snapshot_start),
                    snapshot_end=date.fromisoformat(snapshot_record.snapshot_end),
                    known_at_policy=snapshot_record.known_at_policy,
                    builder_version=snapshot_record.builder_version,
                )
            except ValueError:
                snapshot_reasons.append("RESEARCH_SNAPSHOT_INVALID")
        return ResearchCertificationResult(
            ready=(
                report.status == "ready"
                and report.profile == request.profile
                and snapshot_evidence is not None
            ),
            profile=report.profile,
            dataset_ids=tuple(item.dataset_id for item in report.datasets),
            report_ids=report_ids,
            reason_codes=tuple(sorted(set(snapshot_reasons))),
            snapshot_evidence=snapshot_evidence,
        )
