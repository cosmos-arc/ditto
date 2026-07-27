"""Shared no-I/O validation for immutable backtest-report artifacts."""

from __future__ import annotations

from typing import NoReturn

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
)
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.research.artifact_measurement import measure_json_bytes

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._report_evidence import (
    BACKTEST_REPORT_ARTIFACT_KIND,
    BacktestReportArtifactIdentity,
    BacktestReportArtifactPublisher,
    BacktestReportEvidence,
    LoadedBacktestReportArtifact,
)


class BacktestReportArtifactValidationError(ValueError):
    """One stable local reason before boundary-specific error normalization."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _invalid(reason: str) -> NoReturn:
    raise BacktestReportArtifactValidationError(reason)


def _require_evidence(
    value: object,
    identity: BacktestReportArtifactIdentity,
) -> BacktestReportEvidence:
    if type(value) is not BacktestReportEvidence:
        _invalid("invalid_backtest_report_artifact")
    evidence = value
    try:
        evidence.__post_init__()
    except AppProcessError as error:
        raise BacktestReportArtifactValidationError(
            "invalid_backtest_report_artifact"
        ) from error
    if evidence.run_id != str(identity.run_id):
        _invalid("report_run_identity_drift")
    expected_period = (
        identity.test_window.start.isoformat(),
        identity.test_window.end.isoformat(),
    )
    if evidence.period != expected_period:
        _invalid("report_period_drift")
    return evidence


def _require_record(
    value: object,
    identity: BacktestReportArtifactIdentity,
) -> ArtifactRecord:
    if type(value) is not ArtifactRecord:
        _invalid("invalid_backtest_report_artifact")
    record = value
    typed = (
        (record.artifact_id, str),
        (record.experiment_id, type(identity.experiment_id)),
        (record.candidate_id, type(identity.candidate_id)),
        (record.fold_id, type(identity.fold_id)),
        (record.attempt_id, type(identity.attempt_id)),
        (record.artifact_kind, str),
        (record.relative_path, str),
        (record.content_hash, ContentHash),
        (record.schema_hash, ContentHash),
        (record.row_count, int),
        (record.byte_size, int),
        (
            record.reproduction_fingerprint,
            type(identity.reproduction_fingerprint),
        ),
        (record.created_at, type(identity.attempt_created_at)),
    )
    if any(type(item) is not expected for item, expected in typed):
        _invalid("report_artifact_identity_drift")
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
        _invalid("report_artifact_identity_drift")
    return record


def _validate_measurements(
    record: ArtifactRecord,
    evidence: BacktestReportEvidence,
) -> None:
    canonical = canonical_payload(evidence.canonical_payload())
    measurement = measure_json_bytes(canonical.json_bytes)
    expected = (
        measurement.content_hash,
        measurement.schema_hash,
        measurement.row_count,
        measurement.byte_size,
    )
    actual = (
        record.content_hash,
        record.schema_hash,
        record.row_count,
        record.byte_size,
    )
    if (
        evidence.content_hash != measurement.content_hash
        or record.content_hash != measurement.content_hash
    ):
        _invalid("report_content_hash_drift")
    if actual != expected:
        _invalid("report_artifact_measurement_drift")


def _validate_manifest(
    record: ArtifactRecord,
    identity: BacktestReportArtifactIdentity,
) -> None:
    try:
        manifest = ArtifactManifest.from_record(record)
    except ExperimentIntegrityError as error:
        raise BacktestReportArtifactValidationError(
            "report_artifact_manifest_drift"
        ) from error
    if manifest.artifact_format is not ArtifactFormat.JSON:
        _invalid("report_artifact_format_drift")
    audit = manifest.audit
    if (
        audit.get("created_at") != identity.attempt_created_at.isoformat()
        or audit.get("run_id") != str(identity.run_id)
        or audit.get("attempt_id") != str(identity.attempt_id)
    ):
        _invalid("report_artifact_audit_drift")


def validate_backtest_report_artifact(
    identity: object,
    record: object,
    evidence: object,
) -> LoadedBacktestReportArtifact:
    """Validate one complete index/evidence binding from canonical bytes."""
    if type(identity) is not BacktestReportArtifactIdentity:
        _invalid("invalid_artifact_identity")
    try:
        identity.__post_init__()
    except AppProcessError as error:
        raise BacktestReportArtifactValidationError(
            "invalid_artifact_identity"
        ) from error
    typed_evidence = _require_evidence(evidence, identity)
    typed_record = _require_record(record, identity)
    _validate_measurements(typed_record, typed_evidence)
    _validate_manifest(typed_record, identity)
    return LoadedBacktestReportArtifact(typed_record, typed_evidence)


def validate_loaded_backtest_report_artifact(
    value: object,
    identity: object,
) -> LoadedBacktestReportArtifact:
    """Revalidate a caller-assembled loaded artifact without file I/O."""
    if type(value) is not LoadedBacktestReportArtifact:
        _invalid("invalid_backtest_report_artifact")
    return validate_backtest_report_artifact(
        identity,
        value.record,
        value.evidence,
    )


def _artifact_receipt_integrity(
    identity: BacktestReportArtifactIdentity,
    reason: str,
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        "backtest report artifact publication receipt is inconsistent",
        details={
            "reason_code": "backtest_report_artifact_receipt_drift",
            "reason": reason,
            "artifact_id": identity.artifact_id,
        },
    )


def require_backtest_report_artifact_receipt(
    identity: BacktestReportArtifactIdentity,
    evidence: BacktestReportEvidence,
    receipt: object,
) -> ArtifactRecord:
    """Require a complete immutable-index receipt before attempt completion."""
    try:
        return validate_backtest_report_artifact(
            identity,
            receipt,
            evidence,
        ).record
    except BacktestReportArtifactValidationError as error:
        raise _artifact_receipt_integrity(identity, error.reason) from error


def publish_verified_backtest_report_artifact(
    publisher: BacktestReportArtifactPublisher,
    identity: BacktestReportArtifactIdentity,
    evidence: BacktestReportEvidence,
    *,
    lease_fence: LeaseFence,
    now_epoch_us: int,
) -> ArtifactRecord:
    """Publish and validate the durable receipt inside one lease callback."""
    receipt = publisher.publish(
        identity,
        evidence,
        lease_fence=lease_fence,
        now_epoch_us=now_epoch_us,
    )
    return require_backtest_report_artifact_receipt(identity, evidence, receipt)
