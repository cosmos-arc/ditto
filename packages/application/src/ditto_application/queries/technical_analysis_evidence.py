"""Completed exact-snapshot adapter for Agent technical evidence."""

from __future__ import annotations

from dataclasses import asdict

from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

from ditto_application.catalog_freshness import (
    aggregate_source_snapshot_ids,
    observed_snapshot_ids,
)
from ditto_application.exceptions import AppQueryError
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
    """Resolve completed stock history before computing Agent-visible evidence."""

    def __init__(
        self,
        *,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
        technical_analysis: TechnicalAnalysisFacade,
    ) -> None:
        self._snapshots = snapshots
        self._lifecycle = lifecycle
        self._technical_analysis = technical_analysis

    def get_evidence(
        self,
        *,
        query: InstrumentTechnicalEvidenceQuery,
        context: EvidenceTemporalContext,
    ) -> InstrumentTechnicalEvidenceReadModel:
        """Compute a fixed-v1 analysis only under the exact observed host set."""
        source_snapshot_ids = observed_snapshot_ids(
            self._snapshots,
            self._lifecycle,
            dataset_ids=("stock_daily",),
            knowledge_cutoff=context.knowledge_cutoff,
        )
        snapshot_set_id = aggregate_source_snapshot_ids(source_snapshot_ids)
        if snapshot_set_id is None:
            raise _error(
                "TECHNICAL_EVIDENCE_SNAPSHOT_REQUIRED",
                "completed_stock_daily_snapshot_set_missing",
            )
        if snapshot_set_id != context.source_snapshot_id:
            raise _error(
                "TECHNICAL_EVIDENCE_SNAPSHOT_MISMATCH",
                "host_snapshot_set_does_not_match_observed_history",
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
            ),
            lineage=tuple(
                dict.fromkeys(
                    (
                        snapshot.snapshot_id,
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
