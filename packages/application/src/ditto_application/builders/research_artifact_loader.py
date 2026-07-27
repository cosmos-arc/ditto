"""Indexed research artifact loader backed by ``ResearchArtifactService``."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import NoReturn

import polars as pl
from ditto_analysis.errors import ExperimentIntegrityError, ResearchDatasetError
from ditto_analysis.experiments import (
    ArtifactRecord,
    ContentHash,
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    ContentAddressedResearchInput,
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


def _require_record_identity(
    identity: BacktestReportArtifactIdentity,
    record: object,
) -> ArtifactManifest:
    if type(record) is not ArtifactRecord:
        _integrity(identity, "invalid_artifact_record")
    if type(record.created_at) is not datetime:
        _integrity(identity, "artifact_record_identity_drift")
    expected = (
        identity.artifact_id,
        identity.experiment_id,
        identity.candidate_id,
        identity.fold_id,
        identity.attempt_id,
        identity.attempt_created_at,
        BACKTEST_REPORT_ARTIFACT_KIND,
        identity.relative_path,
        identity.reproduction_fingerprint,
    )
    actual = (
        record.artifact_id,
        record.experiment_id,
        record.candidate_id,
        record.fold_id,
        record.attempt_id,
        record.created_at,
        record.artifact_kind,
        record.relative_path,
        record.reproduction_fingerprint,
    )
    if actual != expected:
        _integrity(identity, "artifact_record_identity_drift")
    if (
        type(record.content_hash) is not ContentHash
        or type(record.schema_hash) is not ContentHash
        or type(record.row_count) is not int
        or record.row_count != 1
        or type(record.byte_size) is not int
        or record.byte_size <= 0
    ):
        _integrity(identity, "artifact_record_measurement_drift")
    manifest = ArtifactManifest.from_record(record)
    if manifest.artifact_format is not ArtifactFormat.JSON:
        _integrity(identity, "artifact_format_drift")
    audit = manifest.audit
    if (
        audit.get("created_at") != identity.attempt_created_at.isoformat()
        or audit.get("run_id") != str(identity.run_id)
        or audit.get("attempt_id") != str(identity.attempt_id)
    ):
        _integrity(identity, "artifact_audit_drift")
    return manifest


def _require_measurement_binding(
    identity: BacktestReportArtifactIdentity,
    record: ArtifactRecord,
    evidence: BacktestReportEvidence,
) -> None:
    canonical = canonical_payload(evidence.canonical_payload())
    if (
        record.content_hash != evidence.content_hash
        or canonical.content_hash != evidence.content_hash
        or record.byte_size != len(canonical.json_bytes)
    ):
        _integrity(identity, "artifact_content_measurement_drift")


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
        _require_record_identity(typed_identity, record)
        _require_measurement_binding(typed_identity, record, typed_evidence)
        return record

    def read(
        self,
        identity: BacktestReportArtifactIdentity,
    ) -> LoadedBacktestReportArtifact | None:
        """Read one existing report through full index/file/schema verification."""
        typed_identity = _require_identity(identity)
        record = self._index.get_artifact(typed_identity.artifact_id)
        if record is None:
            return None
        _require_record_identity(typed_identity, record)
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
        _require_evidence_binding(typed_identity, evidence)
        _require_measurement_binding(typed_identity, record, evidence)
        return LoadedBacktestReportArtifact(record=record, evidence=evidence)
