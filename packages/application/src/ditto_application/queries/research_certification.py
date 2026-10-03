"""Read-only adapter from snapshot readiness evidence to R3 certification probes."""

from __future__ import annotations

from datetime import date

from ditto_analysis.research.catalog_service import ResearchCatalogService

from ditto_application.queries.snapshot_readiness import (
    FieldRequirement,
    SnapshotReadinessQuery,
    SnapshotReadinessRequest,
)
from ditto_application.research_certification_contracts import (
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchSnapshotEvidence,
)

__all__ = ["DataReadinessCertificationProbe"]


class DataReadinessCertificationProbe:
    """Adapt completed observed snapshot evidence to the R3 fixed profile."""

    def __init__(
        self,
        readiness: SnapshotReadinessQuery,
        research_catalog: ResearchCatalogService,
    ) -> None:
        self._readiness = readiness
        self._research_catalog = research_catalog

    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        """Assess exact observed snapshots without mutating catalog state."""
        requirements = request.requirements
        fields = tuple(
            FieldRequirement(dataset_id=item.dataset_id, field="", snapshot_id=sid)
            for item in requirements
            for sid in item.expected_snapshot_ids
        )
        reasons: set[str] = set()
        report_ids: list[str] = []
        if fields:
            report = self._readiness.assess(
                SnapshotReadinessRequest(
                    fields=fields,
                    required_from=request.required_from,
                    required_to=request.required_to,
                )
            )
            dataset_reasons: dict[str, list[str]] = {}
            for item in report.fields:
                dataset_reasons.setdefault(item.dataset_id, []).extend(
                    item.reason_codes
                )
            for item in requirements:
                dataset_codes = tuple(
                    dict.fromkeys(dataset_reasons.get(item.dataset_id, ()))
                )
                if dataset_codes:
                    reasons.update(dataset_codes)
                elif not item.expected_snapshot_ids:
                    reasons.add("SNAPSHOT_REQUIREMENT_MISSING")
                else:
                    report_ids.append(item.expected_snapshot_ids[-1])
        else:
            reasons.add("SNAPSHOT_REQUIREMENT_MISSING")

        snapshot_record = self._research_catalog.get_dataset_snapshot(
            request.snapshot_identity.snapshot_id
        )
        snapshot_evidence: ResearchSnapshotEvidence | None = None
        if snapshot_record is None:
            reasons.add("RESEARCH_SNAPSHOT_MISSING")
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
                reasons.add("RESEARCH_SNAPSHOT_INVALID")

        return ResearchCertificationResult(
            ready=(not reasons and snapshot_evidence is not None),
            profile=request.profile,
            dataset_ids=tuple(item.dataset_id for item in requirements),
            report_ids=tuple(report_ids),
            reason_codes=tuple(sorted(reasons)),
            snapshot_evidence=snapshot_evidence,
        )
