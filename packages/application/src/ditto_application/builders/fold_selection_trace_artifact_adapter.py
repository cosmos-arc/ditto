"""Indexed publisher for the four attempt-scoped fold selection traces."""

from __future__ import annotations

from typing import NoReturn

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import ArtifactRecord, LeaseFence
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceLog

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_serialization import (
    serialize_selection_evidence,
)
from ditto_application.processes.experiments._fold_selection_trace_artifact_validation import (  # noqa: E501
    FoldSelectionTraceArtifactValidationError,
    validate_fold_selection_trace_artifacts,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactIndexReader,
    FoldSelectionTraceArtifactKind,
    FoldSelectionTraceArtifactReceipt,
    fold_selection_trace_table_name,
)

__all__ = ["IndexedFoldSelectionTraceArtifactAdapter"]


def _integrity(
    identity: FoldSelectionTraceArtifactIdentity | None,
    reason: str,
    *,
    kind: FoldSelectionTraceArtifactKind | None = None,
) -> NoReturn:
    raise ExperimentIntegrityError(
        "indexed fold selection trace evidence is inconsistent",
        details={
            "reason_code": "fold_selection_trace_artifact_integrity_mismatch",
            "reason": reason,
            "attempt_id": (None if identity is None else str(identity.attempt_id)),
            "artifact_kind": None if kind is None else kind.value,
        },
    )


def _require_identity(
    value: object,
) -> FoldSelectionTraceArtifactIdentity:
    if type(value) is not FoldSelectionTraceArtifactIdentity:
        _integrity(None, "invalid_fold_selection_trace_artifact_identity")
    try:
        value.__post_init__()
    except AppProcessError as error:
        raise ExperimentIntegrityError(
            "indexed fold selection trace identity is invalid",
            details={
                "reason_code": ("fold_selection_trace_artifact_integrity_mismatch"),
                "reason": "invalid_fold_selection_trace_artifact_identity",
            },
        ) from error
    return value


def _require_evidence(
    identity: FoldSelectionTraceArtifactIdentity,
    value: object,
) -> SelectionEvidenceLog:
    if type(value) is not SelectionEvidenceLog:
        _integrity(identity, "invalid_fold_selection_trace_evidence")
    return value


class IndexedFoldSelectionTraceArtifactAdapter:
    """Publish all four trace frames through the immutable indexed service."""

    def __init__(
        self,
        *,
        artifact_service: ResearchArtifactService,
        artifact_index_reader: FoldSelectionTraceArtifactIndexReader,
    ) -> None:
        self._artifacts = artifact_service
        self._index = artifact_index_reader

    def publish(
        self,
        identity: FoldSelectionTraceArtifactIdentity,
        evidence: SelectionEvidenceLog,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> FoldSelectionTraceArtifactReceipt:
        """Publish/replay four Parquet facts and verify each index binding."""
        typed_identity = _require_identity(identity)
        typed_evidence = _require_evidence(typed_identity, evidence)
        tables = serialize_selection_evidence(
            str(typed_identity.run_id),
            typed_evidence,
        )
        records: list[ArtifactRecord] = []
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
            spec = ArtifactPublicationSpec(
                artifact_id=typed_identity.artifact_id(kind),
                experiment_id=typed_identity.experiment_id,
                candidate_id=typed_identity.candidate_id,
                fold_id=typed_identity.fold_id,
                attempt_id=typed_identity.attempt_id,
                artifact_kind=kind.value,
                relative_path=typed_identity.relative_path(kind),
                reproduction_fingerprint=(typed_identity.reproduction_fingerprint),
                audit=typed_identity.audit(kind),
                created_at=typed_identity.attempt_created_at,
            )
            record = self._artifacts.publish_indexed_parquet(
                spec,
                tables[fold_selection_trace_table_name(kind)],
                lease_fence=lease_fence,
                now_epoch_us=now_epoch_us,
            )
            by_id = self._index.get_artifact(spec.artifact_id)
            by_path = self._index.get_artifact_by_relative_path(spec.relative_path)
            if by_id != record or by_path != record:
                raise ExperimentIntegrityError(
                    "published fold selection trace is not durably indexed",
                    details={
                        "reason_code": ("fold_selection_trace_artifact_index_drift"),
                        "artifact_id": spec.artifact_id,
                        "artifact_kind": kind.value,
                    },
                )
            records.append(record)
        receipt = FoldSelectionTraceArtifactReceipt(*records)
        try:
            return validate_fold_selection_trace_artifacts(
                typed_identity,
                typed_evidence,
                receipt,
            )
        except FoldSelectionTraceArtifactValidationError as error:
            _integrity(typed_identity, error.reason)
