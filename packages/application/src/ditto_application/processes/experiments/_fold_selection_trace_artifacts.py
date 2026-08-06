"""Typed attempt-scoped identities for durable fold selection traces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast

from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.experiments.persistence import validate_artifact_relative_path
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceLog

from ditto_application.exceptions import AppProcessError

__all__ = [
    "FOLD_SELECTION_TRACE_ARTIFACT_KINDS",
    "FOLD_SELECTION_TRACE_SCHEMA_VERSION",
    "FoldSelectionTraceArtifactIdentity",
    "FoldSelectionTraceArtifactIndexReader",
    "FoldSelectionTraceArtifactKind",
    "FoldSelectionTraceArtifactPublisher",
    "FoldSelectionTraceArtifactReader",
    "FoldSelectionTraceArtifactReceipt",
    "LoadedFoldSelectionTraceArtifacts",
    "fold_selection_trace_table_name",
]

FOLD_SELECTION_TRACE_SCHEMA_VERSION = 1
_ARTIFACT_ID_PREFIX = "fold-selection-trace-v1"


class FoldSelectionTraceArtifactKind(StrEnum):
    """Five independent Schema-v1 Parquet facts for one completed fold."""

    CANDIDATE_UNIVERSE = "fold_selection_trace_candidate_universe_v1"
    CANDIDATE_EXCLUSIONS = "fold_selection_trace_candidate_exclusions_v1"
    CANDIDATE_SELECTIONS = "fold_selection_trace_candidate_selections_v1"
    FACTOR_CONTRIBUTIONS = "fold_selection_trace_factor_contributions_v1"
    EXPOSURES = "fold_selection_trace_exposures_v1"


FOLD_SELECTION_TRACE_ARTIFACT_KINDS = (
    FoldSelectionTraceArtifactKind.CANDIDATE_UNIVERSE,
    FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS,
    FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS,
    FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS,
    FoldSelectionTraceArtifactKind.EXPOSURES,
)

_LOGICAL_NAMES = {
    FoldSelectionTraceArtifactKind.CANDIDATE_UNIVERSE: "candidate_universe",
    FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS: "candidate_exclusions",
    FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS: "candidate_selections",
    FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS: "factor_contributions",
    FoldSelectionTraceArtifactKind.EXPOSURES: "exposures",
}
_SERIALIZED_TABLE_NAMES = {
    FoldSelectionTraceArtifactKind.CANDIDATE_UNIVERSE: ("initial_universe_evidence"),
    FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS: "exclusion_evidence",
    FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS: "selection_evidence",
    FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS: (
        "factor_contribution_evidence"
    ),
    FoldSelectionTraceArtifactKind.EXPOSURES: "selection_exposure_evidence",
}


def _contract_error(reason: str) -> AppProcessError:
    return AppProcessError(
        "fold selection trace artifact contract is invalid",
        details={"code": "SPEC_INVALID", "reason": reason},
    )


def _is_exact_aware_utc_datetime(value: object) -> bool:
    if type(value) is not datetime or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() == timedelta(0)
    except (OverflowError, TypeError, ValueError):
        return False


def _require_kind(value: object) -> FoldSelectionTraceArtifactKind:
    if type(value) is not FoldSelectionTraceArtifactKind:
        raise _contract_error("invalid_fold_selection_trace_artifact_kind")
    return value


def fold_selection_trace_table_name(
    kind: FoldSelectionTraceArtifactKind,
) -> str:
    """Map one durable kind to the established pure serializer table."""
    return _SERIALIZED_TABLE_NAMES[_require_kind(kind)]


@dataclass(frozen=True, slots=True)
class FoldSelectionTraceArtifactIdentity:
    """Complete attempt/run identity shared by the four trace artifacts."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId
    attempt_id: AttemptId
    attempt_created_at: datetime
    run_id: BacktestRunId
    test_window: DateWindow
    reproduction_fingerprint: ContentHash

    def __post_init__(self) -> None:
        """Reject erased lineage before deriving any durable address."""
        typed = (
            (self.experiment_id, ExperimentId),
            (self.candidate_id, CandidateId),
            (self.fold_id, FoldId),
            (self.attempt_id, AttemptId),
            (self.run_id, BacktestRunId),
            (self.test_window, DateWindow),
            (self.reproduction_fingerprint, ContentHash),
        )
        if any(
            type(value) is not expected for value, expected in typed
        ) or not _is_exact_aware_utc_datetime(self.attempt_created_at):
            raise _contract_error("invalid_fold_selection_trace_artifact_identity")
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
            validate_artifact_relative_path(self.relative_path(kind))

    def artifact_id(self, kind: FoldSelectionTraceArtifactKind) -> str:
        """Derive a deterministic ID over kind and complete attempt lineage."""
        typed_kind = _require_kind(kind)
        identity_hash = canonical_payload(
            {
                "artifact_kind": typed_kind.value,
                "attempt_created_at": self.attempt_created_at.isoformat(),
                "attempt_id": str(self.attempt_id),
                "candidate_id": str(self.candidate_id),
                "experiment_id": str(self.experiment_id),
                "fold_id": str(self.fold_id),
                "reproduction_fingerprint": str(self.reproduction_fingerprint),
                "run_id": str(self.run_id),
                "schema_version": FOLD_SELECTION_TRACE_SCHEMA_VERSION,
                "test_window": {
                    "end": self.test_window.end.isoformat(),
                    "start": self.test_window.start.isoformat(),
                },
            }
        ).content_hash
        return f"{_ARTIFACT_ID_PREFIX}-{identity_hash}"

    def relative_path(self, kind: FoldSelectionTraceArtifactKind) -> str:
        """Return the fixed attempt-scoped logical Parquet path."""
        logical_name = _LOGICAL_NAMES[_require_kind(kind)]
        return (
            f"experiments/{self.experiment_id}/candidates/{self.candidate_id}/"
            f"folds/{self.fold_id}/attempts/{self.attempt_id}/"
            f"{logical_name}.parquet"
        )

    def audit(self, kind: FoldSelectionTraceArtifactKind) -> dict[str, object]:
        """Return redundant identity fields for manifest fail-closed checks."""
        typed_kind = _require_kind(kind)
        return {
            "artifact_kind": typed_kind.value,
            "attempt_id": str(self.attempt_id),
            "candidate_id": str(self.candidate_id),
            "created_at": self.attempt_created_at.isoformat(),
            "experiment_id": str(self.experiment_id),
            "fold_id": str(self.fold_id),
            "logical_name": _LOGICAL_NAMES[typed_kind],
            "reproduction_fingerprint": str(self.reproduction_fingerprint),
            "run_id": str(self.run_id),
            "schema_version": FOLD_SELECTION_TRACE_SCHEMA_VERSION,
            "test_window": {
                "end": self.test_window.end.isoformat(),
                "start": self.test_window.start.isoformat(),
            },
        }


@dataclass(frozen=True, slots=True)
class FoldSelectionTraceArtifactReceipt:
    """Fixed five-record publication receipt; zero rows remain present facts."""

    candidate_universe: ArtifactRecord
    candidate_exclusions: ArtifactRecord
    candidate_selections: ArtifactRecord
    factor_contributions: ArtifactRecord
    exposures: ArtifactRecord

    def __post_init__(self) -> None:
        """Keep partial or structurally erased receipts out of the contract."""
        if any(type(record) is not ArtifactRecord for record in self.records):
            raise _contract_error("invalid_fold_selection_trace_artifact_receipt")

    @property
    def records(self) -> tuple[ArtifactRecord, ...]:
        """Return records in the canonical logical-kind order."""
        return (
            self.candidate_universe,
            self.candidate_exclusions,
            self.candidate_selections,
            self.factor_contributions,
            self.exposures,
        )

    def record(
        self,
        kind: FoldSelectionTraceArtifactKind,
    ) -> ArtifactRecord:
        """Return the exact record paired with one typed durable kind."""
        typed_kind = _require_kind(kind)
        return cast(
            "dict[FoldSelectionTraceArtifactKind, ArtifactRecord]",
            dict(zip(FOLD_SELECTION_TRACE_ARTIFACT_KINDS, self.records, strict=True)),
        )[typed_kind]


@dataclass(frozen=True, slots=True)
class LoadedFoldSelectionTraceArtifacts:
    """One all-five verified read with its exact attempt identity and evidence."""

    identity: FoldSelectionTraceArtifactIdentity
    receipt: FoldSelectionTraceArtifactReceipt
    evidence: SelectionEvidenceLog

    def __post_init__(self) -> None:
        """Reject erased values at the verified-reader boundary."""
        if (
            type(self.identity) is not FoldSelectionTraceArtifactIdentity
            or type(self.receipt) is not FoldSelectionTraceArtifactReceipt
            or type(self.evidence) is not SelectionEvidenceLog
        ):
            raise _contract_error("invalid_loaded_fold_selection_trace_artifacts")
        self.identity.__post_init__()
        self.receipt.__post_init__()
        self.evidence.__post_init__()


class FoldSelectionTraceArtifactPublisher(Protocol):
    """Worker port for one all-five fold trace publication."""

    def publish(
        self,
        identity: FoldSelectionTraceArtifactIdentity,
        evidence: SelectionEvidenceLog,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> FoldSelectionTraceArtifactReceipt:
        """Publish all five trace tables using the same renewed lease fence."""
        ...


class FoldSelectionTraceArtifactReader(Protocol):
    """Evidence-collection port for an all-or-none verified fold trace."""

    def read(
        self,
        identity: FoldSelectionTraceArtifactIdentity,
    ) -> LoadedFoldSelectionTraceArtifacts | None:
        """Return five verified files, or ``None`` only when all five are absent."""
        ...


class FoldSelectionTraceArtifactIndexReader(Protocol):
    """Narrow index port used to prove ID/path publication identity."""

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        """Return one immutable indexed fact by deterministic ID."""
        ...

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        """Return one immutable indexed fact by attempt-scoped path."""
        ...
