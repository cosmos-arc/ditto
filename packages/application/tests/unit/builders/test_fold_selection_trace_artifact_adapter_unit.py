"""Tests for indexed attempt-scoped fold selection-trace publication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest
from ditto_analysis.errors import ExperimentConflictError, ExperimentIntegrityError
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
)
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.processes.execution.backtest_serialization import (
    serialize_selection_evidence,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactKind,
    LoadedFoldSelectionTraceArtifacts,
    fold_selection_trace_table_name,
)
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    FactorContributionEvidence,
    InitialUniverseEvidence,
    SelectionEvidence,
    SelectionEvidenceLog,
    SelectionExposureDeclaration,
    SelectionExposureEvidence,
    SelectionExposurePolicy,
    SelectionExposureSizeBucket,
)

NOW = datetime(2026, 7, 28, 1, 2, 3, 456789, tzinfo=UTC)
NOW_US = 1_775_000_000_000_000
EXPERIMENT_ID = ExperimentId("experiment-1")
FENCE = LeaseFence(
    experiment_id=EXPERIMENT_ID,
    owner_token="worker-1",
    revision=17,
    lease_until_epoch_us=NOW_US + 1_000_000,
)


class _InjectedIndexFailure(RuntimeError):
    """Simulate interruption after immutable bytes but before one index add."""


class _MemoryArtifactIndex:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve()
        self.records: dict[str, ArtifactRecord] = {}
        self.add_attempts = 0
        self.fail_on_add_attempt: int | None = None

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.relative_path == relative_path
            ),
            None,
        )

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = (lease_fence, now_epoch_us)
        commit_guard()
        self.add_attempts += 1
        if self.fail_on_add_attempt == self.add_attempts:
            self.fail_on_add_attempt = None
            raise _InjectedIndexFailure("injected interruption")
        matches = tuple(
            item
            for item in self.records.values()
            if item.artifact_id == record.artifact_id
            or item.relative_path == record.relative_path
        )
        if not matches:
            self.records[record.artifact_id] = record
            return
        existing = matches[0]
        if replace(existing, is_pinned=False, pinned_at=None, revision=0) != record:
            raise ExperimentConflictError(
                "artifact replay drift",
                details={"reason_code": "artifact_replay_drift"},
            )

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        _ = (artifact_id, expected_revision, pinned_at, commit_guard)
        raise AssertionError("pin is outside fold trace publication")


class _MissingIndexReader:
    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        _ = artifact_id
        return None

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        _ = relative_path
        return None


class _OneSidedIndexReader:
    def __init__(
        self,
        source: _MemoryArtifactIndex,
        *,
        missing_path: str,
    ) -> None:
        self._source = source
        self._missing_path = missing_path

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self._source.get_artifact(artifact_id)

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        if relative_path == self._missing_path:
            return None
        return self._source.get_artifact_by_relative_path(relative_path)


def _identity() -> FoldSelectionTraceArtifactIdentity:
    return FoldSelectionTraceArtifactIdentity(
        experiment_id=EXPERIMENT_ID,
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        attempt_created_at=NOW,
        run_id=BacktestRunId("run-1"),
        test_window=DateWindow(date(2026, 7, 1), date(2026, 7, 31)),
        reproduction_fingerprint=ContentHash("a" * 64),
    )


def _evidence() -> SelectionEvidenceLog:
    return SelectionEvidenceLog(
        initial_universe=(
            InitialUniverseEvidence(
                trade_date="2026-07-28",
                instrument_id=1,
                ordinal=1,
            ),
            InitialUniverseEvidence(
                trade_date="2026-07-28",
                instrument_id="000002.SZ",
                ordinal=2,
            ),
        ),
        exclusions=(
            ExclusionEvidence(
                trade_date="2026-07-28",
                instrument_id="000002.SZ",
                stage="top_k",
                reason_code=ExclusionReason.BELOW_TOP_K,
                message=None,
            ),
        ),
        selections=(
            SelectionEvidence(
                trade_date="2026-07-28",
                instrument_id=1,
                score=2.5,
                rank=1,
                selected=True,
            ),
        ),
        factor_contributions=(
            FactorContributionEvidence(
                trade_date="2026-07-28",
                instrument_id=1,
                factor_name="momentum",
                raw_value=3.0,
                processed_value=2.5,
                normalized_value=1.0,
                weight=2.5,
                contribution=2.5,
                factor_signal_score=2.5,
                rank=1,
                selected=True,
            ),
        ),
        exposure_declarations=(
            SelectionExposureDeclaration.from_policy(
                "2026-07-28",
                SelectionExposurePolicy.stock(),
            ),
        ),
        exposures=(
            SelectionExposureEvidence(
                trade_date="2026-07-28",
                instrument_id=1,
                selected_weight=1.0,
                industry_id="bank",
                size_value=50_000_000_000.0,
                size_bucket=SelectionExposureSizeBucket.MID,
            ),
        ),
    )


def _adapter(
    tmp_path: Path,
    *,
    adapter_index=None,
):
    from ditto_application.builders.fold_selection_trace_artifact_adapter import (
        IndexedFoldSelectionTraceArtifactAdapter,
    )

    index = _MemoryArtifactIndex(tmp_path)
    service = ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )
    return (
        IndexedFoldSelectionTraceArtifactAdapter(
            artifact_service=service,
            artifact_index_reader=adapter_index or index,
        ),
        index,
    )


def _publish_raw_tables(
    tmp_path: Path,
    tables: dict[str, pl.DataFrame],
):
    from ditto_application.builders.fold_selection_trace_artifact_adapter import (
        IndexedFoldSelectionTraceArtifactAdapter,
    )

    identity = _identity()
    index = _MemoryArtifactIndex(tmp_path)
    service = ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )
    for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
        service.publish_indexed_parquet(
            ArtifactPublicationSpec(
                artifact_id=identity.artifact_id(kind),
                experiment_id=identity.experiment_id,
                candidate_id=identity.candidate_id,
                fold_id=identity.fold_id,
                attempt_id=identity.attempt_id,
                artifact_kind=kind.value,
                relative_path=identity.relative_path(kind),
                reproduction_fingerprint=identity.reproduction_fingerprint,
                audit=identity.audit(kind),
                created_at=identity.attempt_created_at,
            ),
            tables[fold_selection_trace_table_name(kind)],
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )
    return IndexedFoldSelectionTraceArtifactAdapter(
        artifact_service=service,
        artifact_index_reader=index,
    )


def test_adapter_publishes_five_empty_tables_as_existing_indexed_parquet(
    tmp_path: Path,
) -> None:
    adapter, index = _adapter(tmp_path)

    receipt = adapter.publish(
        _identity(),
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )

    assert len(receipt.records) == 5
    assert tuple(record.artifact_kind for record in receipt.records) == tuple(
        kind.value for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )
    assert all(record.row_count == 0 for record in receipt.records)
    assert len(index.records) == 5
    assert all(
        (tmp_path / record.relative_path).is_file() for record in receipt.records
    )


def test_adapter_accepts_exact_idempotent_replay_and_rejects_content_drift(
    tmp_path: Path,
) -> None:
    adapter, _ = _adapter(tmp_path)
    identity = _identity()
    first = adapter.publish(
        identity,
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )

    assert (
        adapter.publish(
            identity,
            SelectionEvidenceLog(),
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )
        == first
    )
    changed = SelectionEvidenceLog(
        initial_universe=(
            InitialUniverseEvidence(
                trade_date="2026-07-28",
                instrument_id="000001.SZ",
                ordinal=1,
            ),
        ),
    )
    with pytest.raises(ExperimentConflictError):
        adapter.publish(
            identity,
            changed,
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )


def test_adapter_recovers_exactly_from_partial_index_replay(
    tmp_path: Path,
) -> None:
    adapter, index = _adapter(tmp_path)
    index.fail_on_add_attempt = 3

    with pytest.raises(_InjectedIndexFailure):
        adapter.publish(
            _identity(),
            SelectionEvidenceLog(),
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )

    assert len(index.records) == 2
    receipt = adapter.publish(
        _identity(),
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    assert len(receipt.records) == 5
    assert len(index.records) == 5


def test_adapter_rejects_receipt_not_visible_by_both_id_and_path(
    tmp_path: Path,
) -> None:
    adapter, _ = _adapter(tmp_path, adapter_index=_MissingIndexReader())

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter.publish(
            _identity(),
            SelectionEvidenceLog(),
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )

    assert (
        exc_info.value.details["reason_code"]
        == "fold_selection_trace_artifact_index_drift"
    )


def test_adapter_read_returns_none_only_when_all_four_id_and_path_refs_are_missing(
    tmp_path: Path,
) -> None:
    adapter, _ = _adapter(tmp_path)

    assert adapter.read(_identity()) is None


@pytest.mark.parametrize(
    "evidence",
    [SelectionEvidenceLog(), _evidence()],
    ids=("five-real-zero-row-files", "populated"),
)
def test_adapter_read_rebuilds_verified_selection_evidence_exactly(
    tmp_path: Path,
    evidence: SelectionEvidenceLog,
) -> None:
    adapter, _ = _adapter(tmp_path)
    identity = _identity()
    receipt = adapter.publish(
        identity,
        evidence,
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )

    loaded = adapter.read(identity)

    assert type(loaded) is LoadedFoldSelectionTraceArtifacts
    assert loaded.identity == identity
    assert loaded.receipt == receipt
    assert loaded.evidence == evidence


def test_adapter_read_rejects_partial_five_kind_presence(
    tmp_path: Path,
) -> None:
    adapter, index = _adapter(tmp_path)
    identity = _identity()
    adapter.publish(
        identity,
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    missing_id = identity.artifact_id(
        FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS
    )
    del index.records[missing_id]

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter.read(identity)

    assert exc_info.value.details["reason"] == "partial_fold_selection_trace_artifacts"


def test_adapter_read_rejects_one_sided_id_path_presence(
    tmp_path: Path,
) -> None:
    adapter, index = _adapter(tmp_path)
    identity = _identity()
    adapter.publish(
        identity,
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    adapter, _ = _adapter(
        tmp_path,
        adapter_index=_OneSidedIndexReader(
            index,
            missing_path=identity.relative_path(
                FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS
            ),
        ),
    )

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter.read(identity)

    assert exc_info.value.details["reason"] == "one_sided_artifact_index_binding"


def test_adapter_read_rejects_corrupt_verified_parquet_bytes(
    tmp_path: Path,
) -> None:
    adapter, _ = _adapter(tmp_path)
    identity = _identity()
    receipt = adapter.publish(
        identity,
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    record = receipt.record(FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS)
    (tmp_path / record.relative_path).write_bytes(b"corrupt")

    with pytest.raises(ExperimentIntegrityError):
        adapter.read(identity)


@pytest.mark.parametrize(
    ("table_name", "transform", "expected_reason"),
    [
        (
            "initial_universe_evidence",
            lambda frame: frame.with_columns(pl.lit("run-other").alias("run_id")),
            "invalid_fold_selection_trace_evidence",
        ),
        (
            "initial_universe_evidence",
            lambda frame: frame.with_columns(pl.lit("2026-08-01").alias("trade_date")),
            "selection_trace_trade_date_outside_test_window",
        ),
        (
            "initial_universe_evidence",
            lambda frame: frame.with_columns(
                pl.when(pl.col("instrument_id_kind") == "integer")
                .then(pl.lit("01"))
                .otherwise(pl.col("instrument_id"))
                .alias("instrument_id")
            ),
            "invalid_fold_selection_trace_evidence",
        ),
        (
            "initial_universe_evidence",
            lambda frame: frame.with_columns(pl.col("ordinal").cast(pl.Int32)),
            "selection_trace_schema_fingerprint_drift",
        ),
    ],
    ids=("run-id", "outside-date", "integer-id", "schema"),
)
def test_adapter_read_rejects_verified_bytes_with_semantic_drift(
    tmp_path: Path,
    table_name: str,
    transform: Callable[[pl.DataFrame], pl.DataFrame],
    expected_reason: str,
) -> None:
    identity = _identity()
    tables = serialize_selection_evidence(str(identity.run_id), _evidence())
    tables[table_name] = transform(tables[table_name])
    adapter = _publish_raw_tables(tmp_path, tables)

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter.read(identity)

    assert exc_info.value.details["reason"] == expected_reason
