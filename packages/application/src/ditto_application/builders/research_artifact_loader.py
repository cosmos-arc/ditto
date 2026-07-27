"""Indexed research artifact loader backed by ``ResearchArtifactService``."""

from __future__ import annotations

from io import BytesIO
from typing import NoReturn

import polars as pl
from ditto_analysis.errors import ExperimentIntegrityError, ResearchDatasetError
from ditto_analysis.experiments import (
    ArtifactRecord,
    LeaseFence,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactPublicationSpec,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments._report_artifact_validation import (
    BacktestReportArtifactValidationError,
    validate_backtest_report_artifact,
)
from ditto_application.processes.experiments._report_evidence import (
    BACKTEST_REPORT_ARTIFACT_KIND,
    BacktestReportArtifactIdentity,
    BacktestReportArtifactIndexReader,
    BacktestReportEvidence,
    LoadedBacktestReportArtifact,
    decode_backtest_report_evidence,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)

__all__ = [
    "IndexedBacktestReportArtifactAdapter",
    "IndexedResearchArtifactLoader",
]


class IndexedResearchArtifactLoader:
    """
    Production ``ExactResearchArtifactLoader`` backed by indexed artifacts.

    The loader reads raw verified bytes from the indexed artifact namespace
    and rebuilds the same trust boundaries used during planning. It never
    performs catalog lookup, provider fallback, or unverified path reads.
    """

    def __init__(self, *, artifact_service: ResearchArtifactService) -> None:
        self._artifacts = artifact_service

    def load_frame(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedResearchFrame:
        """Load and verify one Parquet frame addressed by ``evidence.input_id``."""
        artifact_bytes = self._artifacts.read_indexed_artifact_bytes(evidence.input_id)
        # VerifiedResearchFrame does not infer source_snapshot_ids from the
        # parsed frame; derive them here so the trust boundary stays caller-free.
        frame = pl.read_parquet(BytesIO(artifact_bytes))
        source_snapshot_ids = tuple(
            frame["source_snapshot_id"].unique().sort().to_list()
        )
        return VerifiedResearchFrame(
            input_evidence=evidence,
            source_snapshot_ids=source_snapshot_ids,
            artifact_bytes=artifact_bytes,
        )

    def load_instrument_rules(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedInstrumentRulesArtifact:
        """Load and verify one instrument-rules Parquet artifact."""
        artifact_bytes = self._artifacts.read_indexed_artifact_bytes(evidence.input_id)
        return VerifiedInstrumentRulesArtifact(
            input_evidence=evidence,
            artifact_bytes=artifact_bytes,
        )


def _integrity(
    identity: BacktestReportArtifactIdentity,
    reason: str,
) -> NoReturn:
    raise ExperimentIntegrityError(
        "indexed backtest report evidence is inconsistent",
        details={
            "reason_code": "backtest_report_artifact_integrity_mismatch",
            "reason": reason,
            "artifact_id": identity.artifact_id,
        },
    )


def _require_identity(
    identity: object,
) -> BacktestReportArtifactIdentity:
    if type(identity) is not BacktestReportArtifactIdentity:
        raise ExperimentIntegrityError(
            "backtest report artifact identity must be exact",
            details={
                "reason_code": "backtest_report_artifact_integrity_mismatch",
                "reason": "invalid_artifact_identity",
            },
        )
    return identity


def _require_evidence_binding(
    identity: BacktestReportArtifactIdentity,
    evidence: object,
) -> BacktestReportEvidence:
    if type(evidence) is not BacktestReportEvidence:
        _integrity(identity, "invalid_report_evidence")
    expected_period = (
        identity.test_window.start.isoformat(),
        identity.test_window.end.isoformat(),
    )
    if evidence.run_id != str(identity.run_id) or evidence.period != expected_period:
        _integrity(identity, "report_evidence_identity_drift")
    return evidence


def _require_complete_artifact(
    identity: BacktestReportArtifactIdentity,
    record: object,
    evidence: object,
) -> LoadedBacktestReportArtifact:
    try:
        return validate_backtest_report_artifact(identity, record, evidence)
    except BacktestReportArtifactValidationError as error:
        _integrity(identity, error.reason)


class IndexedBacktestReportArtifactAdapter:
    """Production builder adapter over indexed immutable research artifacts."""

    def __init__(
        self,
        *,
        artifact_service: ResearchArtifactService,
        artifact_index_reader: BacktestReportArtifactIndexReader,
    ) -> None:
        self._artifacts = artifact_service
        self._index = artifact_index_reader

    def publish(
        self,
        identity: BacktestReportArtifactIdentity,
        evidence: BacktestReportEvidence,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish an immutable attempt report with explicit run/time audit."""
        typed_identity = _require_identity(identity)
        typed_evidence = _require_evidence_binding(typed_identity, evidence)
        spec = ArtifactPublicationSpec(
            artifact_id=typed_identity.artifact_id,
            experiment_id=typed_identity.experiment_id,
            candidate_id=typed_identity.candidate_id,
            fold_id=typed_identity.fold_id,
            attempt_id=typed_identity.attempt_id,
            artifact_kind=BACKTEST_REPORT_ARTIFACT_KIND,
            relative_path=typed_identity.relative_path,
            reproduction_fingerprint=typed_identity.reproduction_fingerprint,
            audit={
                "attempt_id": str(typed_identity.attempt_id),
                "created_at": typed_identity.attempt_created_at.isoformat(),
                "run_id": str(typed_identity.run_id),
            },
            created_at=typed_identity.attempt_created_at,
        )
        record = self._artifacts.publish_indexed_json(
            spec,
            typed_evidence.canonical_payload(),
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )
        _require_complete_artifact(typed_identity, record, typed_evidence)
        return record

    def read(
        self,
        identity: BacktestReportArtifactIdentity,
    ) -> LoadedBacktestReportArtifact | None:
        """Read one existing report through full index/file/schema verification."""
        typed_identity = _require_identity(identity)
        record_by_id = self._index.get_artifact(typed_identity.artifact_id)
        record_by_path = self._index.get_artifact_by_relative_path(
            typed_identity.relative_path
        )
        if record_by_id is None and record_by_path is None:
            return None
        if (
            record_by_id is None
            or record_by_path is None
            or record_by_id != record_by_path
        ):
            _integrity(typed_identity, "artifact_identity_path_cross_conflict")
        record = record_by_id
        try:
            payload = self._artifacts.read_indexed_json(typed_identity.artifact_id)
            evidence = decode_backtest_report_evidence(payload)
        except (
            AppProcessError,
            ExperimentIntegrityError,
            ResearchDatasetError,
        ) as exc:
            raise ExperimentIntegrityError(
                "indexed backtest report payload violates Schema v1",
                details={
                    "reason_code": "backtest_report_artifact_integrity_mismatch",
                    "reason": "invalid_backtest_report_evidence",
                    "artifact_id": typed_identity.artifact_id,
                },
            ) from exc
        return _require_complete_artifact(typed_identity, record, evidence)
