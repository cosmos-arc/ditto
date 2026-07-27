"""Indexed publisher for the four attempt-scoped fold selection traces."""

from __future__ import annotations

from typing import NoReturn

import polars as pl
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import ArtifactRecord, LeaseFence
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    FactorContributionEvidence,
    InitialUniverseEvidence,
    SelectionEvidence,
    SelectionEvidenceLog,
)
from ditto_strategy.errors import StrategySpecError

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
    LoadedFoldSelectionTraceArtifacts,
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


class _SelectionTraceDecodeError(ValueError):
    """
    Local control-flow signal for selection trace row decode failures.

    Caught and normalized to a typed integrity error at the decode boundary;
    never escapes to callers.
    """


def _decode_instrument_id(row: dict[str, object]) -> int | str:
    raw_value = row["instrument_id"]
    raw_kind = row["instrument_id_kind"]
    if type(raw_value) is not str or not raw_value:
        raise _SelectionTraceDecodeError("instrument_id must be a non-empty string")
    if raw_kind == "string":
        return raw_value
    if raw_kind != "integer":
        raise _SelectionTraceDecodeError("instrument_id_kind is unsupported")
    parsed = int(raw_value)
    if str(parsed) != raw_value:
        raise _SelectionTraceDecodeError("integer instrument_id is not canonical")
    return parsed


def _require_run_id(
    row: dict[str, object],
    identity: FoldSelectionTraceArtifactIdentity,
) -> None:
    if row["run_id"] != str(identity.run_id):
        raise _SelectionTraceDecodeError("selection trace row identifies another run")


def _decode_evidence(
    identity: FoldSelectionTraceArtifactIdentity,
    frames: dict[FoldSelectionTraceArtifactKind, pl.DataFrame],
) -> SelectionEvidenceLog:
    try:
        initial_universe = tuple(
            InitialUniverseEvidence(
                trade_date=str(row["trade_date"]),
                instrument_id=_decode_instrument_id(row),
                ordinal=row["ordinal"],
            )
            for row in frames[
                FoldSelectionTraceArtifactKind.CANDIDATE_UNIVERSE
            ].iter_rows(named=True)
            if not _require_run_id(row, identity)
        )
        exclusions = tuple(
            ExclusionEvidence(
                trade_date=str(row["trade_date"]),
                instrument_id=_decode_instrument_id(row),
                stage=row["stage"],
                reason_code=ExclusionReason(row["reason_code"]),
                message=row["message"],
            )
            for row in frames[
                FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS
            ].iter_rows(named=True)
            if not _require_run_id(row, identity)
        )
        selections = tuple(
            SelectionEvidence(
                trade_date=str(row["trade_date"]),
                instrument_id=_decode_instrument_id(row),
                score=row["score"],
                rank=row["rank"],
                selected=row["selected"],
            )
            for row in frames[
                FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS
            ].iter_rows(named=True)
            if not _require_run_id(row, identity)
        )
        contributions = tuple(
            FactorContributionEvidence(
                trade_date=str(row["trade_date"]),
                instrument_id=_decode_instrument_id(row),
                factor_name=row["factor_name"],
                raw_value=row["raw_value"],
                processed_value=row["processed_value"],
                normalized_value=row["normalized_value"],
                weight=row["weight"],
                contribution=row["contribution"],
                factor_signal_score=row["factor_signal_score"],
                rank=row["rank"],
                selected=row["selected"],
            )
            for row in frames[
                FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS
            ].iter_rows(named=True)
            if not _require_run_id(row, identity)
        )
        evidence = SelectionEvidenceLog(
            initial_universe=initial_universe,
            exclusions=exclusions,
            selections=selections,
            factor_contributions=contributions,
        )
        encoded = serialize_selection_evidence(str(identity.run_id), evidence)
    except (
        AppProcessError,
        KeyError,
        OverflowError,
        StrategySpecError,
        TypeError,
        ValueError,
    ) as error:
        raise FoldSelectionTraceArtifactValidationError(
            "invalid_fold_selection_trace_evidence"
        ) from error
    for kind, frame in frames.items():
        expected = encoded[fold_selection_trace_table_name(kind)]
        if frame.schema != expected.schema:
            raise FoldSelectionTraceArtifactValidationError(
                "selection_trace_schema_fingerprint_drift"
            )
        if not frame.equals(expected, null_equal=True):
            raise FoldSelectionTraceArtifactValidationError(
                "fold_selection_trace_decode_round_trip_drift"
            )
    return evidence


class IndexedFoldSelectionTraceArtifactAdapter:
    """Publish and read all four traces through the immutable indexed service."""

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

    def read(
        self,
        identity: FoldSelectionTraceArtifactIdentity,
    ) -> LoadedFoldSelectionTraceArtifacts | None:
        """Read one exact all-four trace bundle through verified indexed APIs."""
        typed_identity = _require_identity(identity)
        records: list[ArtifactRecord] = []
        frames: dict[FoldSelectionTraceArtifactKind, pl.DataFrame] = {}
        missing_kinds: list[FoldSelectionTraceArtifactKind] = []
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
            artifact_id = typed_identity.artifact_id(kind)
            relative_path = typed_identity.relative_path(kind)
            by_id = self._index.get_artifact(artifact_id)
            by_path = self._index.get_artifact_by_relative_path(relative_path)
            if by_id is None and by_path is None:
                missing_kinds.append(kind)
                continue
            if by_id is None or by_path is None:
                _integrity(
                    typed_identity,
                    "one_sided_artifact_index_binding",
                    kind=kind,
                )
            if by_id != by_path:
                _integrity(
                    typed_identity,
                    "artifact_id_path_binding_drift",
                    kind=kind,
                )
            records.append(by_id)
        if len(missing_kinds) == len(FOLD_SELECTION_TRACE_ARTIFACT_KINDS):
            return None
        if missing_kinds:
            _integrity(
                typed_identity,
                "partial_fold_selection_trace_artifacts",
                kind=missing_kinds[0],
            )
        receipt = FoldSelectionTraceArtifactReceipt(*records)
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
            frames[kind] = self._artifacts.read_indexed_parquet(
                typed_identity.artifact_id(kind)
            )
        try:
            evidence = _decode_evidence(typed_identity, frames)
            validate_fold_selection_trace_artifacts(
                typed_identity,
                evidence,
                receipt,
            )
            return LoadedFoldSelectionTraceArtifacts(
                typed_identity,
                receipt,
                evidence,
            )
        except FoldSelectionTraceArtifactValidationError as error:
            _integrity(typed_identity, error.reason)
