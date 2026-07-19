"""Narrow domain ports for experiment control-plane consumers."""

from __future__ import annotations

from typing import Protocol

from ditto_analysis.experiments.models import (
    AttemptId,
    AttemptRecord,
    CandidateRecord,
    ExperimentId,
    ExperimentRecord,
    FoldId,
    FoldRecord,
)

__all__ = ["ExperimentReaderProtocol", "ExperimentWriterProtocol"]


class ExperimentReaderProtocol(Protocol):
    """Read immutable experiment projections without dict-shaped leakage."""

    def get_experiment(self, experiment_id: ExperimentId) -> ExperimentRecord | None:
        """Return one experiment projection when it exists."""
        ...

    def list_candidates(
        self, experiment_id: ExperimentId
    ) -> tuple[CandidateRecord, ...]:
        """Return candidates in stable ordinal order."""
        ...

    def list_folds(self, experiment_id: ExperimentId) -> tuple[FoldRecord, ...]:
        """Return folds in stable ordinal order."""
        ...

    def list_attempts(self, fold_id: FoldId) -> tuple[AttemptRecord, ...]:
        """Return append-only attempts in stable ordinal order."""
        ...

    def get_attempt(self, attempt_id: AttemptId) -> AttemptRecord | None:
        """Return one immutable attempt projection when it exists."""
        ...


class ExperimentWriterProtocol(Protocol):
    """Append immutable domain facts; no scheduler or I/O implementation."""

    def add_experiment(self, record: ExperimentRecord) -> None:
        """Append the initial experiment projection."""
        ...

    def add_candidate(self, record: CandidateRecord) -> None:
        """Append one candidate identity."""
        ...

    def add_fold(self, record: FoldRecord) -> None:
        """Append one fold identity."""
        ...

    def add_attempt(self, record: AttemptRecord) -> None:
        """Append a new attempt without overwriting prior evidence."""
        ...
