"""Certified exact-snapshot adapter for Agent technical evidence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from ditto_data.catalog.certification import (
    CertificationReader,
    DatasetCertificationReport,
)

from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppConfigurationError, AppQueryError
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    InstrumentTechnicalEvidenceQuery,
    InstrumentTechnicalEvidenceReadModel,
)
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisRequest,
    TechnicalAnalysisSpecDraft,
)

__all__ = [
    "InstrumentTechnicalEvidenceQuery",
    "InstrumentTechnicalEvidenceQueryFacade",
]

_SHA256_HEX_LENGTH = 64


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"technical analysis evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _approved_report_at(
    reader: CertificationReader,
    *,
    dataset_id: str,
    profile: str,
    knowledge_cutoff: datetime,
    source_snapshot_id: str,
) -> DatasetCertificationReport | None:
    """Select the latest visible approval for the host's exact snapshot set."""
    selected: DatasetCertificationReport | None = None
    for report in reader.list_reports(dataset_id, profile):
        if report.generated_at > knowledge_cutoff:
            continue
        visible_events = tuple(
            event
            for event in reader.list_events(report.report_id)
            if event.occurred_at <= knowledge_cutoff
        )
        if not visible_events or visible_events[-1].action != "approved":
            continue
        report_snapshot_set_id = aggregate_source_snapshot_ids(
            tuple(sorted(report.evidence.snapshot_ids))
        )
        if report_snapshot_set_id == source_snapshot_id:
            selected = report
    return selected


def _snapshot_hash(snapshot_id: str) -> str:
    digest = snapshot_id.removeprefix("technical-analysis:sha256:")
    if len(digest) != _SHA256_HEX_LENGTH or any(
        item not in "0123456789abcdef" for item in digest
    ):
        raise _error(
            "TECHNICAL_EVIDENCE_IDENTITY_INVALID",
            "technical_snapshot_identity_has_no_sha256",
            snapshot_id=snapshot_id,
        )
    return digest


class InstrumentTechnicalEvidenceQueryFacade:
    """Resolve certified stock history before computing Agent-visible evidence."""

    def __init__(
        self,
        *,
        certification_reader: CertificationReader,
        technical_analysis: TechnicalAnalysisFacade,
        certification_profile: str,
    ) -> None:
        if (
            not certification_profile
            or certification_profile.strip() != certification_profile
        ):
            raise AppConfigurationError(
                "technical analysis certification_profile must be canonical"
            )
        self._certification_reader = certification_reader
        self._technical_analysis = technical_analysis
        self._profile = certification_profile

    def get_evidence(
        self,
        *,
        query: InstrumentTechnicalEvidenceQuery,
        context: EvidenceTemporalContext,
    ) -> InstrumentTechnicalEvidenceReadModel:
        """Compute a fixed-v1 analysis only under the exact certified host set."""
        report = _approved_report_at(
            self._certification_reader,
            dataset_id="stock_daily",
            profile=self._profile,
            knowledge_cutoff=context.knowledge_cutoff,
            source_snapshot_id=context.source_snapshot_id,
        )
        if report is None:
            raise _error(
                "TECHNICAL_EVIDENCE_CERTIFICATION_REQUIRED",
                "certified_stock_daily_snapshot_set_missing",
                profile=self._profile,
                source_snapshot_id=context.source_snapshot_id,
            )
        source_snapshot_ids = tuple(sorted(report.evidence.snapshot_ids))
        snapshot_set_id = aggregate_source_snapshot_ids(source_snapshot_ids)
        if snapshot_set_id is None:
            raise _error(
                "TECHNICAL_EVIDENCE_SNAPSHOT_REQUIRED",
                "certified_snapshot_set_empty",
            )
        if snapshot_set_id != context.source_snapshot_id:
            raise _error(
                "TECHNICAL_EVIDENCE_SNAPSHOT_MISMATCH",
                "host_snapshot_set_does_not_match_certified_history",
                expected_snapshot_set_id=snapshot_set_id,
                actual_snapshot_set_id=context.source_snapshot_id,
            )
        snapshot = self._technical_analysis.get_snapshot(
            TechnicalAnalysisRequest(
                instrument_id=query.instrument_id,
                instrument_name=query.instrument_name,
                instrument_code=query.instrument_code,
                as_of=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_ids=source_snapshot_ids,
                spec=TechnicalAnalysisSpecDraft(
                    spec_id="technical-core",
                    spec_version="1",
                    timeframes=("daily", "weekly"),
                ),
                selection_run_id=query.selection_run_id,
                research_case_id=query.research_case_id,
                portfolio_snapshot_id=query.portfolio_snapshot_id,
            )
        )
        if snapshot.source_snapshot_ids != source_snapshot_ids:
            raise _error(
                "TECHNICAL_EVIDENCE_PROVENANCE_MISMATCH",
                "technical_analysis_changed_source_snapshot_set",
            )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value=asdict(snapshot),
        )
        return InstrumentTechnicalEvidenceReadModel(
            snapshot_id=snapshot.snapshot_id,
            instrument_id=snapshot.instrument_id,
            instrument_name=snapshot.instrument_name,
            status=snapshot.status,
            source_snapshot_ids=snapshot.source_snapshot_ids,
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=snapshot.snapshot_id,
                    artifact_kind="technical_analysis_snapshot",
                    content_hash=_snapshot_hash(snapshot.snapshot_id),
                ),
                EvidenceArtifactReference(
                    artifact_id=report.report_id,
                    artifact_kind="dataset_certification",
                    content_hash=report.content_hash,
                ),
            ),
            lineage=tuple(
                dict.fromkeys(
                    (
                        snapshot.snapshot_id,
                        f"certification:{report.report_id}",
                        *(f"snapshot:{item}" for item in source_snapshot_ids),
                        *(
                            (snapshot.selection_run_id,)
                            if snapshot.selection_run_id is not None
                            else ()
                        ),
                        *(
                            (snapshot.research_case_id,)
                            if snapshot.research_case_id is not None
                            else ()
                        ),
                        *(
                            (snapshot.portfolio_snapshot_id,)
                            if snapshot.portfolio_snapshot_id is not None
                            else ()
                        ),
                    )
                )
            ),
        )
