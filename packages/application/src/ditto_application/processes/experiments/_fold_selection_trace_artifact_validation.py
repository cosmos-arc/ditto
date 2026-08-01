"""No-I/O validation for the five durable fold selection-trace artifacts."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import NoReturn

import polars as pl
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import ArtifactRecord, ContentHash, LeaseFence
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
)
from ditto_analysis.research.artifact_measurement import measure_parquet_bytes
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceLog

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_serialization import (
    serialize_selection_evidence,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactKind,
    FoldSelectionTraceArtifactPublisher,
    FoldSelectionTraceArtifactReceipt,
    fold_selection_trace_table_name,
)

__all__ = [
    "FoldSelectionTraceArtifactValidationError",
    "publish_verified_fold_selection_trace_artifacts",
    "require_fold_selection_trace_artifact_receipt",
    "validate_fold_selection_trace_artifacts",
]


class FoldSelectionTraceArtifactValidationError(ValueError):
    """One stable local reason before boundary error normalization."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _invalid(reason: str) -> NoReturn:
    raise FoldSelectionTraceArtifactValidationError(reason)


def _require_identity(
    value: object,
) -> FoldSelectionTraceArtifactIdentity:
    if type(value) is not FoldSelectionTraceArtifactIdentity:
        _invalid("invalid_fold_selection_trace_artifact_identity")
    try:
        value.__post_init__()
    except AppProcessError as error:
        raise FoldSelectionTraceArtifactValidationError(
            "invalid_fold_selection_trace_artifact_identity"
        ) from error
    return value


def _require_evidence(value: object) -> SelectionEvidenceLog:
    if type(value) is not SelectionEvidenceLog:
        _invalid("invalid_fold_selection_trace_evidence")
    return value


def _require_receipt(value: object) -> FoldSelectionTraceArtifactReceipt:
    if type(value) is not FoldSelectionTraceArtifactReceipt:
        _invalid("invalid_selection_trace_artifact_receipt")
    try:
        value.__post_init__()
    except AppProcessError as error:
        raise FoldSelectionTraceArtifactValidationError(
            "invalid_selection_trace_artifact_receipt"
        ) from error
    return value


def _require_record_identity(
    identity: FoldSelectionTraceArtifactIdentity,
    kind: FoldSelectionTraceArtifactKind,
    value: object,
) -> ArtifactRecord:
    if type(value) is not ArtifactRecord:
        _invalid("invalid_selection_trace_artifact_receipt")
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
        _invalid("fold_selection_trace_artifact_identity_drift")
    expected = (
        identity.artifact_id(kind),
        identity.experiment_id,
        identity.candidate_id,
        identity.fold_id,
        identity.attempt_id,
        kind.value,
        identity.relative_path(kind),
        identity.reproduction_fingerprint,
        identity.attempt_created_at,
    )
    actual = (
        record.artifact_id,
        record.experiment_id,
        record.candidate_id,
        record.fold_id,
        record.attempt_id,
        record.artifact_kind,
        record.relative_path,
        record.reproduction_fingerprint,
        record.created_at,
    )
    if actual != expected:
        _invalid("fold_selection_trace_artifact_identity_drift")
    return record


def _validate_measurements(
    record: ArtifactRecord,
    frame: pl.DataFrame,
) -> None:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    measurement = measure_parquet_bytes(buffer.getvalue())
    if record.content_hash != measurement.content_hash:
        _invalid("selection_trace_content_hash_drift")
    if record.schema_hash != measurement.schema_hash:
        _invalid("selection_trace_schema_fingerprint_drift")
    if record.row_count != measurement.row_count:
        _invalid("selection_trace_row_count_drift")
    if record.byte_size != measurement.byte_size:
        _invalid("selection_trace_byte_size_drift")


def _validate_trade_dates(
    identity: FoldSelectionTraceArtifactIdentity,
    tables: dict[str, pl.DataFrame],
) -> None:
    for frame in tables.values():
        for raw_trade_date in frame["trade_date"].unique().to_list():
            if type(raw_trade_date) is not str:
                _invalid("invalid_selection_trace_trade_date")
            try:
                trade_date = date.fromisoformat(raw_trade_date)
            except ValueError as error:
                raise FoldSelectionTraceArtifactValidationError(
                    "invalid_selection_trace_trade_date"
                ) from error
            if trade_date.isoformat() != raw_trade_date:
                _invalid("invalid_selection_trace_trade_date")
            if not (
                identity.test_window.start <= trade_date <= identity.test_window.end
            ):
                _invalid("selection_trace_trade_date_outside_test_window")


def _validate_manifest(
    identity: FoldSelectionTraceArtifactIdentity,
    kind: FoldSelectionTraceArtifactKind,
    record: ArtifactRecord,
) -> None:
    try:
        manifest = ArtifactManifest.from_record(record)
    except ExperimentIntegrityError as error:
        raise FoldSelectionTraceArtifactValidationError(
            "fold_selection_trace_artifact_manifest_drift"
        ) from error
    if manifest.artifact_format is not ArtifactFormat.PARQUET:
        _invalid("fold_selection_trace_artifact_format_drift")
    if dict(manifest.audit) != identity.audit(kind):
        _invalid("fold_selection_trace_artifact_audit_drift")


def validate_fold_selection_trace_artifacts(
    identity: object,
    evidence: object,
    receipt: object,
) -> FoldSelectionTraceArtifactReceipt:
    """Validate exactly five indexed records against canonical trace frames."""
    typed_identity = _require_identity(identity)
    typed_evidence = _require_evidence(evidence)
    typed_receipt = _require_receipt(receipt)
    try:
        tables = serialize_selection_evidence(
            str(typed_identity.run_id),
            typed_evidence,
        )
    except AppProcessError as error:
        raise FoldSelectionTraceArtifactValidationError(
            "invalid_fold_selection_trace_evidence"
        ) from error
    _validate_trade_dates(typed_identity, tables)
    for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
        record = _require_record_identity(
            typed_identity,
            kind,
            typed_receipt.record(kind),
        )
        frame = tables[fold_selection_trace_table_name(kind)]
        _validate_measurements(record, frame)
        _validate_manifest(typed_identity, kind, record)
    return typed_receipt


def _receipt_integrity(
    identity: FoldSelectionTraceArtifactIdentity,
    reason: str,
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        "fold selection trace artifact publication receipt is inconsistent",
        details={
            "reason_code": "fold_selection_trace_artifact_receipt_drift",
            "reason": reason,
            "attempt_id": str(identity.attempt_id),
            "run_id": str(identity.run_id),
        },
    )


def require_fold_selection_trace_artifact_receipt(
    identity: FoldSelectionTraceArtifactIdentity,
    evidence: SelectionEvidenceLog,
    receipt: object,
) -> FoldSelectionTraceArtifactReceipt:
    """Require the complete five-record receipt before attempt completion."""
    try:
        return validate_fold_selection_trace_artifacts(
            identity,
            evidence,
            receipt,
        )
    except FoldSelectionTraceArtifactValidationError as error:
        raise _receipt_integrity(identity, error.reason) from error


def publish_verified_fold_selection_trace_artifacts(
    publisher: FoldSelectionTraceArtifactPublisher | None,
    identity: FoldSelectionTraceArtifactIdentity,
    evidence: SelectionEvidenceLog,
    *,
    lease_fence: LeaseFence,
    now_epoch_us: int,
) -> FoldSelectionTraceArtifactReceipt:
    """Publish and verify all five records inside one lease callback."""
    if publisher is None:
        raise _receipt_integrity(identity, "fold_selection_trace_publisher_missing")
    receipt = publisher.publish(
        identity,
        evidence,
        lease_fence=lease_fence,
        now_epoch_us=now_epoch_us,
    )
    return require_fold_selection_trace_artifact_receipt(
        identity,
        evidence,
        receipt,
    )
