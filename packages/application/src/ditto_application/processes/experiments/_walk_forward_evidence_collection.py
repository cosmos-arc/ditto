"""Typed collection of persisted walk-forward comparison evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CandidateId,
    CheckpointRef,
    ContentHash,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
)

from ditto_application.processes.experiments._evidence_inputs import (
    FoldEvidenceInput,
    SnapshotManifestProjection,
    assemble_candidate_fold_evidence,
)
from ditto_application.processes.experiments._evidence_values import (
    comparison_error,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactReader,
    LoadedFoldSelectionTraceArtifacts,
)
from ditto_application.processes.experiments._oos_fold_registration import (
    OOSFoldRegistration,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactIdentity,
    BacktestReportArtifactReader,
)
from ditto_application.processes.experiments._walk_forward_execution_semantics import (
    ValidatedWalkForwardExecutionSemantics,
    WalkForwardExecutionBindings,
    WalkForwardExecutionSemanticsResolver,
    build_walk_forward_execution_bindings,
    resolve_walk_forward_execution_semantics,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
)
from ditto_application.processes.experiments.comparison import (
    BaselineComparisonIdentity,
    CandidateComparisonProjection,
    CandidateFoldEvidence,
    FoldOutcome,
    build_candidate_comparison,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)
from ditto_application.processes.experiments.walk_forward import (
    WalkForwardAggregation,
    aggregate_walk_forward,
)

__all__ = [
    "CollectedWalkForwardEvidence",
    "WalkForwardEvidenceAssembler",
]

_EVIDENCE_TERMINAL_STATUSES = frozenset(
    {
        ExperimentStatus.CANCELLED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }
)
_ROW_STATUSES = frozenset(
    {
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }
)
_REQUIRED_BASELINE_FOLDS = 2


def _canonical_row_order(
    rows: tuple[CandidateFoldEvidence, ...],
) -> tuple[CandidateFoldEvidence, ...]:
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.fold_ordinal,
                row.candidate_ordinal,
                str(row.fold_id),
                str(row.candidate_id),
            ),
        )
    )


def _missing_artifact_ref(row: CandidateFoldEvidence) -> str:
    return BacktestReportArtifactIdentity(
        experiment_id=row.experiment_id,
        candidate_id=row.candidate_id,
        fold_id=row.fold_id,
        attempt_id=row.attempt_id,
        attempt_created_at=row.execution_binding.attempt_view.spec.created_at,
        run_id=row.run_id,
        test_window=row.test_window,
        reproduction_fingerprint=row.reproduction_fingerprint,
    ).relative_path


def _selection_trace_identity(
    row: CandidateFoldEvidence,
) -> FoldSelectionTraceArtifactIdentity:
    return FoldSelectionTraceArtifactIdentity(
        experiment_id=row.experiment_id,
        candidate_id=row.candidate_id,
        fold_id=row.fold_id,
        attempt_id=row.attempt_id,
        attempt_created_at=row.execution_binding.attempt_view.spec.created_at,
        run_id=row.run_id,
        test_window=row.test_window,
        reproduction_fingerprint=row.reproduction_fingerprint,
    )


def _validated_selection_traces(
    rows: tuple[CandidateFoldEvidence, ...],
    value: object,
) -> dict[FoldSelectionTraceArtifactIdentity, LoadedFoldSelectionTraceArtifacts]:
    if type(value) is not tuple or any(
        type(item) is not LoadedFoldSelectionTraceArtifacts
        for item in cast("tuple[object, ...]", value)
    ):
        comparison_error("invalid_fold_selection_trace_artifacts")
    traces = cast("tuple[LoadedFoldSelectionTraceArtifacts, ...]", value)
    by_identity = {bundle.identity: bundle for bundle in traces}
    if len(by_identity) != len(traces):
        comparison_error("duplicate_fold_selection_trace_artifacts")
    expected = tuple(
        by_identity[identity]
        for row in rows
        if row.outcome is FoldOutcome.COMPLETED
        and (identity := _selection_trace_identity(row)) in by_identity
    )
    if traces != expected:
        comparison_error("noncanonical_fold_selection_trace_artifacts")
    return by_identity


def _expected_missing_artifact_refs(
    rows: tuple[CandidateFoldEvidence, ...],
    traces: dict[
        FoldSelectionTraceArtifactIdentity,
        LoadedFoldSelectionTraceArtifacts,
    ],
) -> tuple[str, ...]:
    expected: list[str] = []
    for row in rows:
        if row.outcome is not FoldOutcome.COMPLETED:
            continue
        if row.report_artifact is None:
            expected.append(_missing_artifact_ref(row))
        trace_identity = _selection_trace_identity(row)
        if trace_identity not in traces:
            expected.extend(
                trace_identity.relative_path(kind)
                for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
            )
    return tuple(sorted(expected, key=str.encode))


@dataclass(frozen=True, slots=True)
class CollectedWalkForwardEvidence:
    """One immutable comparison, aggregation, and its exact source rows."""

    comparison: CandidateComparisonProjection
    aggregation: WalkForwardAggregation
    source_rows: tuple[CandidateFoldEvidence, ...]
    fold_cost_config_hashes: tuple[ContentHash, ...]
    selection_traces: tuple[LoadedFoldSelectionTraceArtifacts, ...]
    missing_artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject detached, reordered, or noncanonical collection results."""
        if (
            type(self.comparison) is not CandidateComparisonProjection
            or type(self.aggregation) is not WalkForwardAggregation
            or self.aggregation.baseline != self.comparison.baseline
            or self.aggregation != aggregate_walk_forward(self.comparison)
        ):
            comparison_error("invalid_collected_walk_forward_evidence")
        raw_rows: object = self.source_rows
        if type(raw_rows) is not tuple or any(
            type(row) is not CandidateFoldEvidence
            for row in cast("tuple[object, ...]", raw_rows)
        ):
            comparison_error("invalid_collected_walk_forward_evidence")
        rows = self.source_rows
        if (
            rows != _canonical_row_order(rows)
            or tuple(fold.source for fold in self.comparison.folds) != rows
        ):
            comparison_error("noncanonical_collected_source_rows")
        raw_cost_hashes: object = self.fold_cost_config_hashes
        if (
            type(raw_cost_hashes) is not tuple
            or len(raw_cost_hashes) != len(rows)
            or any(
                type(item) is not ContentHash
                for item in cast("tuple[object, ...]", raw_cost_hashes)
            )
        ):
            comparison_error("invalid_fold_cost_config_hashes")
        trace_by_identity = _validated_selection_traces(
            rows,
            self.selection_traces,
        )
        raw_refs: object = self.missing_artifact_refs
        if type(raw_refs) is not tuple or any(
            type(ref) is not str or not ref or ref != ref.strip()
            for ref in cast("tuple[object, ...]", raw_refs)
        ):
            comparison_error("invalid_missing_artifact_refs")
        refs = self.missing_artifact_refs
        if refs != tuple(sorted(set(refs), key=str.encode)):
            comparison_error("noncanonical_missing_artifact_refs")
        expected_refs = _expected_missing_artifact_refs(rows, trace_by_identity)
        if refs != expected_refs:
            comparison_error("missing_artifact_ref_parity_drift")


def _revalidate_snapshot(
    snapshot: ExperimentSchedulerSnapshot,
) -> ExperimentSchedulerSnapshot:
    raw_folds: object = snapshot.folds
    raw_attempts: object = snapshot.attempts
    if type(raw_folds) is not tuple or type(raw_attempts) is not tuple:
        comparison_error("invalid_scheduler_snapshot")
    if any(
        type(fold) is not FoldView
        or type(fold.spec) is not FoldPersistenceSpec
        or type(fold.projection) is not FoldProjection
        for fold in cast("tuple[object, ...]", raw_folds)
    ):
        comparison_error("invalid_walk_forward_fold")
    if any(
        type(attempt) is not AttemptView
        or type(attempt.spec) is not AttemptPersistenceSpec
        or type(attempt.projection) is not AttemptProjection
        for attempt in cast("tuple[object, ...]", raw_attempts)
    ):
        comparison_error("invalid_attempt_evidence")
    try:
        return ExperimentSchedulerSnapshot(
            projection=snapshot.projection,
            launch_spec=snapshot.launch_spec,
            folds=snapshot.folds,
            attempts=snapshot.attempts,
            holdout_claim=snapshot.holdout_claim,
        )
    except (AttributeError, TypeError):
        comparison_error("invalid_scheduler_snapshot")


def _validate_fold(
    fold: object,
    *,
    experiment_id: ExperimentId,
    candidate_ids: set[CandidateId],
) -> FoldView:
    if type(fold) is not FoldView:
        comparison_error("invalid_walk_forward_fold")
    typed = fold
    spec = typed.spec
    projection = typed.projection
    if (
        type(spec) is not FoldPersistenceSpec
        or type(projection) is not FoldProjection
        or type(spec.key) is not FoldKey
        or spec.key.experiment_id != experiment_id
        or spec.key.candidate_id not in candidate_ids
        or projection.key != spec.key
    ):
        comparison_error("walk_forward_fold_lineage_drift")
    rebuilt = FoldPersistenceSpec.create(
        spec.key,
        spec.ordinal,
        spec.fold_role,
        spec.train_window,
        spec.test_window,
        spec.purge_sessions,
        spec.embargo_sessions,
    )
    if rebuilt != spec:
        comparison_error("persisted_fold_spec_drift")
    return typed


def _walk_forward_topology_key(fold: FoldView) -> tuple[object, ...]:
    spec = fold.spec
    return (
        spec.key.fold_id,
        spec.ordinal,
        spec.train_window,
        spec.test_window,
        spec.purge_sessions,
        spec.embargo_sessions,
    )


def _validate_shared_walk_forward_topology(
    folds: tuple[FoldView, ...],
    bindings: WalkForwardExecutionBindings,
) -> None:
    baseline_folds = tuple(
        fold
        for fold in folds
        if fold.spec.key.candidate_id == bindings.baseline.candidate_id
    )
    if len(baseline_folds) != _REQUIRED_BASELINE_FOLDS:
        comparison_error("baseline_two_walk_forward_folds_required")
    baseline_topology = frozenset(
        _walk_forward_topology_key(fold) for fold in baseline_folds
    )
    for candidate in sorted(
        bindings.candidates.values(),
        key=lambda item: item.ordinal,
    ):
        candidate_folds = tuple(
            fold
            for fold in folds
            if fold.spec.key.candidate_id == candidate.candidate_id
        )
        candidate_topology = frozenset(
            _walk_forward_topology_key(fold) for fold in candidate_folds
        )
        if (
            len(candidate_folds) != _REQUIRED_BASELINE_FOLDS
            or candidate_topology != baseline_topology
        ):
            comparison_error(
                "candidate_walk_forward_topology_drift",
                candidate_id=str(candidate.candidate_id),
            )
        if all(
            fold.projection.status is ExperimentStatus.CANCELLED
            for fold in candidate_folds
        ):
            comparison_error(
                "candidate_walk_forward_source_rows_missing",
                candidate_id=str(candidate.candidate_id),
            )


def _walk_forward_folds(
    snapshot: ExperimentSchedulerSnapshot,
    bindings: WalkForwardExecutionBindings,
) -> tuple[FoldView, ...]:
    folds = tuple(
        _validate_fold(
            fold,
            experiment_id=snapshot.launch_spec.experiment_id,
            candidate_ids=set(bindings.candidates),
        )
        for fold in snapshot.folds
    )
    selected = tuple(
        fold for fold in folds if fold.spec.fold_role is FoldRole.WALK_FORWARD
    )
    if not selected:
        comparison_error("walk_forward_evidence_missing")
    for fold in selected:
        status = fold.projection.status
        if (
            type(status) is not ExperimentStatus
            or status not in _EVIDENCE_TERMINAL_STATUSES
        ):
            comparison_error(
                "walk_forward_fold_not_terminal",
                fold_id=str(fold.spec.key.fold_id),
            )
    _validate_shared_walk_forward_topology(selected, bindings)
    return tuple(
        sorted(
            selected,
            key=lambda fold: (
                bindings.candidates[fold.spec.key.candidate_id].ordinal,
                fold.spec.ordinal,
                str(fold.spec.key.fold_id),
            ),
        )
    )


def _utc_datetime(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == UTC.utcoffset(value)
    )


def _validate_attempt_shape(attempt: object, fold_key: FoldKey) -> AttemptView:
    if type(attempt) is not AttemptView:
        comparison_error("invalid_attempt_evidence")
    typed = attempt
    spec = typed.spec
    projection = typed.projection
    if (
        type(spec) is not AttemptPersistenceSpec
        or type(projection) is not AttemptProjection
        or type(spec.attempt_id) is not AttemptId
        or type(spec.reproduction_fingerprint) is not ContentHash
        or type(spec.ordinal) is not int
        or spec.ordinal <= 0
        or spec.fold_key != fold_key
        or projection.attempt_id != spec.attempt_id
        or type(projection.status) is not ExperimentStatus
        or (
            projection.backtest_run_id is not None
            and type(projection.backtest_run_id) is not BacktestRunId
        )
        or (
            projection.checkpoint_ref is not None
            and type(projection.checkpoint_ref) is not CheckpointRef
        )
        or (
            projection.failure_code is not None
            and type(projection.failure_code) is not ExperimentFailureCode
        )
        or not _utc_datetime(spec.created_at)
        or not _utc_datetime(projection.created_at)
        or spec.created_at != projection.created_at
    ):
        comparison_error("attempt_identity_drift")
    return typed


def _validate_attempt_outcome(attempt: AttemptView) -> None:
    projection = attempt.projection
    status = projection.status
    if status is ExperimentStatus.QUEUED and (
        projection.backtest_run_id is not None
        or projection.checkpoint_ref is not None
        or projection.failure_code is not None
    ):
        comparison_error("queued_attempt_projection_invalid")
    if (
        status in _ROW_STATUSES
        and type(projection.backtest_run_id) is not BacktestRunId
    ):
        comparison_error("terminal_attempt_run_id_missing")
    if status is ExperimentStatus.COMPLETED and projection.failure_code is not None:
        comparison_error("completed_attempt_failure_code_drift")
    if (
        status is ExperimentStatus.FAILED
        and type(projection.failure_code) is not ExperimentFailureCode
    ):
        comparison_error("failed_attempt_failure_code_missing")
    if status is ExperimentStatus.CANCELLED and projection.failure_code is not None:
        comparison_error("cancelled_attempt_failure_code_drift")


def _validate_attempt_lineage(history: tuple[AttemptView, ...]) -> None:
    seen_runs: set[BacktestRunId] = set()
    for index, attempt in enumerate(history):
        _validate_attempt_outcome(attempt)
        spec = attempt.spec
        projection = attempt.projection
        run_id = projection.backtest_run_id
        if run_id is not None:
            if run_id in seen_runs:
                comparison_error("attempt_run_identity_drift")
            seen_runs.add(run_id)
        if index == 0:
            if (
                spec.parent_attempt_id is not None
                or spec.resume_from_run_id is not None
            ):
                comparison_error("first_attempt_invalid")
            continue
        parent = history[index - 1]
        if (
            parent.projection.status
            not in {ExperimentStatus.CANCELLED, ExperimentStatus.FAILED}
            or spec.parent_attempt_id != parent.spec.attempt_id
            or spec.reproduction_fingerprint != parent.spec.reproduction_fingerprint
            or (
                spec.resume_from_run_id is not None
                and all(
                    ancestor.projection.backtest_run_id != spec.resume_from_run_id
                    for ancestor in history[:index]
                )
            )
        ):
            comparison_error("attempt_lineage_drift")


def _attempt_history(
    snapshot: ExperimentSchedulerSnapshot,
    fold: FoldView,
) -> tuple[AttemptView, ...]:
    matching_values: list[AttemptView] = []
    for raw_attempt in snapshot.attempts:
        if (
            type(raw_attempt) is not AttemptView
            or type(raw_attempt.spec) is not AttemptPersistenceSpec
        ):
            comparison_error("invalid_attempt_evidence")
        attempt = raw_attempt
        if attempt.spec.fold_key == fold.spec.key:
            matching_values.append(_validate_attempt_shape(attempt, fold.spec.key))
    matching = tuple(matching_values)
    attempt_ids = tuple(attempt.spec.attempt_id for attempt in matching)
    if len(set(attempt_ids)) != len(attempt_ids):
        comparison_error("duplicate_attempt_identity")
    ordinals = tuple(attempt.spec.ordinal for attempt in matching)
    if len(set(ordinals)) != len(ordinals):
        comparison_error(
            "duplicate_attempt_ordinal",
            fold_id=str(fold.spec.key.fold_id),
        )
    history = tuple(sorted(matching, key=lambda item: item.spec.ordinal))
    if history and tuple(item.spec.ordinal for item in history) != tuple(
        range(1, len(history) + 1)
    ):
        comparison_error("attempt_ordinal_gap")
    _validate_attempt_lineage(history)
    return history


def _selected_attempt(
    snapshot: ExperimentSchedulerSnapshot,
    fold: FoldView,
) -> AttemptView | None:
    history = _attempt_history(snapshot, fold)
    status = fold.projection.status
    if not history:
        if status is ExperimentStatus.CANCELLED:
            return None
        comparison_error(
            "terminal_attempt_evidence_missing",
            fold_id=str(fold.spec.key.fold_id),
        )
    latest = history[-1]
    if latest.projection.status not in _EVIDENCE_TERMINAL_STATUSES:
        comparison_error(
            "latest_attempt_not_terminal",
            fold_id=str(fold.spec.key.fold_id),
        )
    if latest.projection.status is not status:
        comparison_error(
            "fold_attempt_status_mismatch",
            fold_id=str(fold.spec.key.fold_id),
        )
    return latest


class WalkForwardEvidenceAssembler:
    """Collect exact terminal WF attempts and verified reports into R3 evidence."""

    def __init__(
        self,
        *,
        report_reader: BacktestReportArtifactReader,
        fold_selection_trace_reader: FoldSelectionTraceArtifactReader,
        semantics_resolver: WalkForwardExecutionSemanticsResolver,
    ) -> None:
        self._report_reader = report_reader
        self._fold_selection_trace_reader = fold_selection_trace_reader
        self._semantics_resolver = semantics_resolver

    def _baseline_identity(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        manifest: SnapshotManifestProjection,
        bindings: WalkForwardExecutionBindings,
        folds: tuple[FoldView, ...],
        selected: dict[FoldKey, AttemptView | None],
        semantics_by_fold: dict[FoldKey, ValidatedWalkForwardExecutionSemantics],
    ) -> BaselineComparisonIdentity:
        baseline_folds = tuple(
            fold
            for fold in folds
            if fold.spec.key.candidate_id == bindings.baseline.candidate_id
        )
        if len(baseline_folds) != _REQUIRED_BASELINE_FOLDS:
            comparison_error("baseline_two_walk_forward_folds_required")
        plans: list[BaselineExecutionPlan] = []
        for fold in baseline_folds:
            attempt = selected[fold.spec.key]
            if attempt is None:
                comparison_error("baseline_attempt_evidence_missing")
            semantics = semantics_by_fold[fold.spec.key].semantics
            plan = semantics.baseline_plan
            if type(plan) is not BaselineExecutionPlan:
                comparison_error("baseline_plan_required")
            if (
                semantics.reproduction_fingerprint
                != attempt.spec.reproduction_fingerprint
                or plan.snapshot.snapshot_id != str(snapshot.launch_spec.snapshot_id)
                or plan.snapshot.manifest_hash != str(manifest.snapshot_hash)
                or semantics.snapshot.known_at_policy != manifest.pit_policy
            ):
                comparison_error("baseline_execution_semantics_drift")
            plans.append(plan)
        if plans[0] != plans[1] or plans[0].canonical_hash != plans[1].canonical_hash:
            comparison_error("baseline_plan_identity_drift")
        registrations = tuple(
            OOSFoldRegistration(
                fold.spec.key.fold_id,
                fold.spec.ordinal,
                fold.spec.test_window,
            )
            for fold in baseline_folds
        )
        return BaselineComparisonIdentity(
            snapshot.launch_spec.experiment_id,
            bindings.baseline.candidate_id,
            plans[0],
            registrations,
        )

    def _source_rows(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        manifest: SnapshotManifestProjection,
        bindings: WalkForwardExecutionBindings,
        folds: tuple[FoldView, ...],
        selected: dict[FoldKey, AttemptView | None],
    ) -> tuple[
        tuple[CandidateFoldEvidence, ...],
        tuple[LoadedFoldSelectionTraceArtifacts, ...],
        tuple[str, ...],
    ]:
        rows: list[CandidateFoldEvidence] = []
        traces_by_fold: dict[FoldKey, LoadedFoldSelectionTraceArtifacts] = {}
        missing: list[str] = []
        for fold in folds:
            attempt = selected[fold.spec.key]
            if attempt is None or fold.projection.status is ExperimentStatus.CANCELLED:
                continue
            candidate = bindings.candidates[fold.spec.key.candidate_id]
            execution = bindings.execution[fold.spec.key.candidate_id]
            report = None
            failure_reason = None
            if fold.projection.status is ExperimentStatus.COMPLETED:
                run_id = attempt.projection.backtest_run_id
                if type(run_id) is not BacktestRunId:
                    comparison_error("terminal_attempt_run_id_missing")
                identity = BacktestReportArtifactIdentity(
                    experiment_id=fold.spec.key.experiment_id,
                    candidate_id=fold.spec.key.candidate_id,
                    fold_id=fold.spec.key.fold_id,
                    attempt_id=attempt.spec.attempt_id,
                    attempt_created_at=attempt.spec.created_at,
                    run_id=run_id,
                    test_window=fold.spec.test_window,
                    reproduction_fingerprint=attempt.spec.reproduction_fingerprint,
                )
                report = self._report_reader.read(identity)
                if report is None:
                    missing.append(identity.relative_path)
                trace_identity = FoldSelectionTraceArtifactIdentity(
                    experiment_id=fold.spec.key.experiment_id,
                    candidate_id=fold.spec.key.candidate_id,
                    fold_id=fold.spec.key.fold_id,
                    attempt_id=attempt.spec.attempt_id,
                    attempt_created_at=attempt.spec.created_at,
                    run_id=run_id,
                    test_window=fold.spec.test_window,
                    reproduction_fingerprint=(attempt.spec.reproduction_fingerprint),
                )
                trace = self._fold_selection_trace_reader.read(trace_identity)
                if trace is None:
                    missing.extend(
                        trace_identity.relative_path(kind)
                        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
                    )
                else:
                    traces_by_fold[fold.spec.key] = trace
            else:
                failure = attempt.projection.failure_code
                if type(failure) is not ExperimentFailureCode:
                    comparison_error("failed_attempt_failure_code_missing")
                failure_reason = failure.value
            rows.append(
                assemble_candidate_fold_evidence(
                    FoldEvidenceInput(
                        fold_view=fold,
                        attempt_view=attempt,
                        candidate_ordinal=candidate.ordinal,
                        snapshot_id=snapshot.launch_spec.snapshot_id,
                        snapshot_hash=manifest.snapshot_hash,
                        parameter_hash=execution.parameter_hash,
                        resolved_spec_hash=execution.resolved_spec_hash,
                        report_artifact=report,
                        failure_reason=failure_reason,
                    )
                )
            )
        canonical_rows = _canonical_row_order(tuple(rows))
        return (
            canonical_rows,
            tuple(
                traces_by_fold[row.execution_binding.fold_view.spec.key]
                for row in canonical_rows
                if row.outcome is FoldOutcome.COMPLETED
                and row.execution_binding.fold_view.spec.key in traces_by_fold
            ),
            tuple(sorted(set(missing), key=str.encode)),
        )

    def assemble(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        manifest: SnapshotManifestProjection,
    ) -> CollectedWalkForwardEvidence:
        """Build deterministic comparison evidence from one persisted snapshot."""
        if (
            type(snapshot) is not ExperimentSchedulerSnapshot
            or type(manifest) is not SnapshotManifestProjection
        ):
            comparison_error("invalid_walk_forward_collection_input")
        manifest = SnapshotManifestProjection(
            manifest.snapshot_hash,
            manifest.registry_hash,
            manifest.pit_policy,
        )
        snapshot = _revalidate_snapshot(snapshot)
        bindings = build_walk_forward_execution_bindings(snapshot)
        folds = _walk_forward_folds(snapshot, bindings)
        selected = {fold.spec.key: _selected_attempt(snapshot, fold) for fold in folds}
        semantics_by_fold = resolve_walk_forward_execution_semantics(
            self._semantics_resolver,
            snapshot,
            manifest,
            bindings,
            folds,
            selected,
        )
        baseline = self._baseline_identity(
            snapshot,
            manifest,
            bindings,
            folds,
            selected,
            semantics_by_fold,
        )
        rows, selection_traces, missing = self._source_rows(
            snapshot,
            manifest,
            bindings,
            folds,
            selected,
        )
        cost_hashes = tuple(
            semantics_by_fold[row.execution_binding.fold_view.spec.key].cost_config_hash
            for row in rows
        )
        comparison = build_candidate_comparison(baseline, rows)
        aggregation = aggregate_walk_forward(comparison)
        return CollectedWalkForwardEvidence(
            comparison,
            aggregation,
            rows,
            cost_hashes,
            selection_traces,
            missing,
        )
