"""Tests for indexed attempt-scoped fold selection-trace publication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

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
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
)
from ditto_strategy.alpha.selection_evidence import (
    InitialUniverseEvidence,
    SelectionEvidenceLog,
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


def test_adapter_publishes_four_empty_tables_as_existing_indexed_parquet(
    tmp_path: Path,
) -> None:
    adapter, index = _adapter(tmp_path)

    receipt = adapter.publish(
        _identity(),
        SelectionEvidenceLog(),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )

    assert len(receipt.records) == 4
    assert tuple(record.artifact_kind for record in receipt.records) == tuple(
        kind.value for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )
    assert all(record.row_count == 0 for record in receipt.records)
    assert len(index.records) == 4
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
    assert len(receipt.records) == 4
    assert len(index.records) == 4


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
