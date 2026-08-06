# pyright: reportPrivateUsage=false, reportUnusedFunction=false
"""Trusted persisted fold and attempt binding for comparison evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from ditto_analysis.experiments import (
    AttemptId as _AttemptId,
)
from ditto_analysis.experiments import (
    AttemptPersistenceSpec as _AttemptPersistenceSpec,
)
from ditto_analysis.experiments import (
    AttemptProjection as _AttemptProjection,
)
from ditto_analysis.experiments import (
    AttemptView as _AttemptView,
)
from ditto_analysis.experiments import (
    BacktestRunId as _BacktestRunId,
)
from ditto_analysis.experiments import (
    CandidateId as _CandidateId,
)
from ditto_analysis.experiments import (
    ContentHash as _ContentHash,
)
from ditto_analysis.experiments import (
    DateWindow as _DateWindow,
)
from ditto_analysis.experiments import (
    ExperimentId as _ExperimentId,
)
from ditto_analysis.experiments import (
    ExperimentReaderProtocol as _ExperimentReaderProtocol,
)
from ditto_analysis.experiments import (
    ExperimentStatus as _ExperimentStatus,
)
from ditto_analysis.experiments import (
    FoldId as _FoldId,
)
from ditto_analysis.experiments import (
    FoldKey as _FoldKey,
)
from ditto_analysis.experiments import (
    FoldPersistenceSpec as _FoldPersistenceSpec,
)
from ditto_analysis.experiments import (
    FoldProjection as _FoldProjection,
)
from ditto_analysis.experiments import (
    FoldRole as _FoldRole,
)
from ditto_analysis.experiments import (
    FoldView as _FoldView,
)
from ditto_analysis.experiments import (
    canonical_payload as _canonical_payload,
)

from ditto_application.processes.experiments._comparison_evidence import FoldOutcome
from ditto_application.processes.experiments._evidence_values import _comparison_error

_PERSISTED_BINDING_TOKEN = object()
_PERSISTED_BINDING_SCHEMA_ID = "ditto.r3.persisted-fold-execution"
_PERSISTED_BINDING_SCHEMA_VERSION = 1


def _validate_views(
    fold: _FoldView,
    attempt: _AttemptView,
) -> None:
    if type(fold) is not _FoldView or type(attempt) is not _AttemptView:
        _comparison_error("invalid_persisted_execution_binding")
    fold_spec, fold_projection = fold.spec, fold.projection
    attempt_spec, attempt_projection = attempt.spec, attempt.projection
    if (
        type(fold_spec) is not _FoldPersistenceSpec
        or type(fold_projection) is not _FoldProjection
        or type(fold_spec.key) is not _FoldKey
        or type(attempt_spec) is not _AttemptPersistenceSpec
        or type(attempt_projection) is not _AttemptProjection
        or type(attempt_spec.attempt_id) is not _AttemptId
        or type(attempt_spec.reproduction_fingerprint) is not _ContentHash
        or type(attempt_projection.backtest_run_id) is not _BacktestRunId
        or type(attempt_spec.ordinal) is not int
        or attempt_spec.ordinal <= 0
        or fold_spec.fold_role is not _FoldRole.WALK_FORWARD
    ):
        _comparison_error("invalid_persisted_execution_binding")
    rebuilt = _FoldPersistenceSpec.create(
        fold_spec.key,
        fold_spec.ordinal,
        fold_spec.fold_role,
        fold_spec.train_window,
        fold_spec.test_window,
        fold_spec.purge_sessions,
        fold_spec.embargo_sessions,
    )
    if rebuilt != fold_spec:
        _comparison_error("persisted_fold_spec_drift")
    terminal = {_ExperimentStatus.COMPLETED, _ExperimentStatus.FAILED}
    if (
        fold_projection.key != fold_spec.key
        or attempt_spec.fold_key != fold_spec.key
        or attempt_projection.attempt_id != attempt_spec.attempt_id
        or attempt_projection.status not in terminal
        or fold_projection.status is not attempt_projection.status
    ):
        _comparison_error("persisted_attempt_lineage_drift")


@dataclass(frozen=True, slots=True)
class PersistedFoldExecutionEvidence:
    """Factory-only binding to durable fold and terminal attempt projections."""

    fold_view: _FoldView = field(repr=False)
    attempt_view: _AttemptView = field(repr=False)
    _factory_marker: object = field(repr=False, compare=False)
    content_hash: _ContentHash = field(init=False)

    def __post_init__(self) -> None:
        """Revalidate persisted views and derive their canonical binding hash."""
        if self._factory_marker is not _PERSISTED_BINDING_TOKEN:
            _comparison_error("persisted_execution_binding_factory_required")
        _validate_views(self.fold_view, self.attempt_view)
        object.__setattr__(
            self,
            "content_hash",
            _canonical_payload(self.canonical_payload()).content_hash,
        )

    @property
    def experiment_id(self) -> _ExperimentId:
        """Return the persisted experiment identity."""
        return self.fold_view.spec.key.experiment_id

    @property
    def candidate_id(self) -> _CandidateId:
        """Return the persisted candidate identity."""
        return self.fold_view.spec.key.candidate_id

    @property
    def fold_id(self) -> _FoldId:
        """Return the persisted fold identity."""
        return self.fold_view.spec.key.fold_id

    @property
    def fold_ordinal(self) -> int:
        """Return the persisted fold ordinal."""
        return self.fold_view.spec.ordinal

    @property
    def test_window(self) -> _DateWindow:
        """Return the persisted exact test window."""
        return self.fold_view.spec.test_window

    @property
    def attempt_id(self) -> _AttemptId:
        """Return the persisted attempt identity."""
        return self.attempt_view.spec.attempt_id

    @property
    def run_id(self) -> _BacktestRunId:
        """Return the terminal attempt's persisted backtest run identity."""
        return cast("_BacktestRunId", self.attempt_view.projection.backtest_run_id)

    @property
    def reproduction_fingerprint(self) -> _ContentHash:
        """Return the persisted attempt reproduction fingerprint."""
        return self.attempt_view.spec.reproduction_fingerprint

    @property
    def outcome(self) -> FoldOutcome:
        """Map the persisted terminal status to comparison outcome semantics."""
        if self.attempt_view.projection.status is _ExperimentStatus.COMPLETED:
            return FoldOutcome.COMPLETED
        return FoldOutcome.FAILED

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete versioned persisted execution identity."""
        return {
            "binding_schema": {
                "id": _PERSISTED_BINDING_SCHEMA_ID,
                "version": _PERSISTED_BINDING_SCHEMA_VERSION,
            },
            "attempt_id": str(self.attempt_id),
            "attempt_ordinal": self.attempt_view.spec.ordinal,
            "candidate_id": str(self.candidate_id),
            "experiment_id": str(self.experiment_id),
            "fold_id": str(self.fold_id),
            "fold_ordinal": self.fold_ordinal,
            "fold_spec_hash": str(self.fold_view.spec.payload_hash),
            "reproduction_fingerprint": str(self.reproduction_fingerprint),
            "run_id": str(self.run_id),
            "status": self.attempt_view.projection.status.value,
            "test_window": {
                "end": self.test_window.end.isoformat(),
                "start": self.test_window.start.isoformat(),
            },
        }


def _bind_persisted_fold_execution(
    fold: _FoldView, attempt: _AttemptView
) -> PersistedFoldExecutionEvidence:
    return PersistedFoldExecutionEvidence(
        fold,
        attempt,
        _PERSISTED_BINDING_TOKEN,
    )


def load_persisted_fold_execution(
    reader: _ExperimentReaderProtocol,
    fold_key: _FoldKey,
    attempt_id: _AttemptId,
) -> PersistedFoldExecutionEvidence:
    """Load and bind exact fold/attempt views through the persistence reader port."""
    if type(fold_key) is not _FoldKey or type(attempt_id) is not _AttemptId:
        _comparison_error("invalid_persisted_execution_lookup")
    try:
        fold = reader.get_fold(fold_key)
        attempt = reader.get_attempt(attempt_id)
    except AttributeError:
        _comparison_error("invalid_experiment_reader")
    if fold is None or attempt is None:
        _comparison_error("persisted_execution_not_found")
    if fold.spec.key != fold_key or attempt.spec.attempt_id != attempt_id:
        _comparison_error("persisted_execution_lookup_drift")
    return _bind_persisted_fold_execution(fold, attempt)


def _validate_persisted_fold_execution(
    value: object,
) -> PersistedFoldExecutionEvidence:
    if type(value) is not PersistedFoldExecutionEvidence:
        _comparison_error("invalid_persisted_execution_binding")
    binding = value
    _validate_views(binding.fold_view, binding.attempt_view)
    expected_hash = _canonical_payload(binding.canonical_payload()).content_hash
    if binding.content_hash != expected_hash:
        _comparison_error("persisted_execution_binding_hash_drift")
    return binding
