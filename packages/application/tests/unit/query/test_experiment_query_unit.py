"""Unit tests for the application-owned experiment read model."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentPersistenceError
from ditto_analysis.experiments import (
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldProtocolSpec,
    FoldRole,
    FoldView,
    GateEvaluationRecord,
    LogicalTrialIdentity,
    ResearchCycleIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    SnapshotId,
    StatusEventRecord,
    StatusSubjectType,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.experiments import ExperimentQueryFacade

NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)


def _aggregate() -> tuple[
    ResearchCycleIdentity,
    ExperimentLaunchSpec,
    ExperimentProjection,
    tuple[FoldView, ...],
]:
    experiment_id = ExperimentId("exp-query-1")
    candidates = (
        CandidateSpec(
            candidate_id=CandidateId("candidate-baseline"),
            ordinal=1,
            is_baseline=True,
            parameters={"__ditto_baseline_v1__": "{}"},
        ),
        CandidateSpec(
            candidate_id=CandidateId("candidate-default"),
            ordinal=2,
            is_baseline=False,
            parameters={},
        ),
    )
    spec = ExperimentLaunchSpec(
        experiment_id=experiment_id,
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=candidates,
        execution_bindings=tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(f"{candidate.ordinal + 16:064x}"),
            )
            for candidate in candidates
        ),
        promotion_objective=PromotionObjective(
            ObjectiveMetric(
                ResearchMetricId.NET_RETURN,
                ResearchMetricDirection.MAXIMIZE,
            ),
            (),
            (),
            CandidateId("candidate-baseline"),
            "Test experiment query behavior.",
            TrialFamilyDeclaration(
                "query-test-family",
                tuple(
                    LogicalTrialIdentity(
                        experiment_id,
                        candidate.candidate_id,
                        candidate.ordinal,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    )
                    for candidate in candidates
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec(
            protocol_id="r3-complete-month-walk-forward",
            protocol_version=1,
            protocol_hash=ContentHash("b" * 64),
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(candidate_limit=128, fold_run_limit=7),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )
    projection = ExperimentProjection(
        record=ExperimentRecord(
            experiment_id=experiment_id,
            status=ExperimentStatus.QUEUED,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=NOW,
        ),
        queue_ordinal=4,
        revision=1,
        updated_at=NOW,
    )
    folds: list[FoldView] = []
    for candidate in candidates:
        key = FoldKey(
            experiment_id=experiment_id,
            candidate_id=candidate.candidate_id,
            fold_id=FoldId(f"{candidate.candidate_id}-exploration"),
        )
        fold_spec = FoldPersistenceSpec.create(
            key=key,
            ordinal=1,
            fold_role=FoldRole.EXPLORATION,
            train_window=None,
            test_window=DateWindow(date(2016, 1, 4), date(2020, 12, 31)),
            purge_sessions=5,
            embargo_sessions=5,
        )
        folds.append(
            FoldView(
                spec=fold_spec,
                projection=FoldProjection(
                    key=key,
                    status=ExperimentStatus.QUEUED,
                    claim_owner_token=None,
                    created_at=NOW,
                    updated_at=NOW,
                    revision=0,
                ),
            )
        )
    return (
        ResearchCycleIdentity("cycle-1", ContentHash("c" * 64)),
        spec,
        projection,
        tuple(folds),
    )


class _Reader:
    def __init__(self) -> None:
        cycle, spec, projection, folds = _aggregate()
        self.cycle: ResearchCycleIdentity | None = cycle
        self.spec: ExperimentLaunchSpec | None = spec
        self.projection: ExperimentProjection | None = projection
        self.candidates = tuple(reversed(spec.candidates))
        self.folds = folds
        self.gate: GateEvaluationRecord | None = None
        self.events: tuple[StatusEventRecord, ...] = ()
        self.holdout_claim = None
        self.read_error: ExperimentPersistenceError | None = None

    def get_research_cycle_identity(self, experiment_id: ExperimentId):
        return self.cycle

    def get_launch_spec(self, experiment_id: ExperimentId):
        if self.read_error is not None:
            raise self.read_error
        return self.spec

    def get_experiment_projection(self, experiment_id: ExperimentId):
        return self.projection

    def list_candidates(self, experiment_id: ExperimentId):
        return self.candidates

    def list_folds(self, experiment_id: ExperimentId):
        return tuple(reversed(self.folds))

    def get_gate_evaluation(self, evaluation_id: str):
        return self.gate

    def list_status_events(self, experiment_id: ExperimentId):
        return self.events

    def get_holdout_claim_for_experiment(self, experiment_id: ExperimentId):
        return self.holdout_claim


def _facade(reader: _Reader) -> ExperimentQueryFacade:
    """Treat the deliberately narrow fake as the complete injected read port."""
    return ExperimentQueryFacade(
        reader=cast("ExperimentReaderProtocol", reader),
    )


def _running_projection(projection: ExperimentProjection) -> ExperimentProjection:
    return replace(
        projection,
        record=replace(projection.record, status=ExperimentStatus.RUNNING),
        revision=projection.revision + 1,
        updated_at=projection.updated_at + timedelta(seconds=1),
    )


def _running_fold(view: FoldView) -> FoldView:
    return replace(
        view,
        projection=replace(
            view.projection,
            status=ExperimentStatus.RUNNING,
            claim_owner_token="worker-1",
            revision=view.projection.revision + 1,
            updated_at=view.projection.updated_at + timedelta(seconds=1),
        ),
    )


def test_detail_maps_complete_persisted_truth_in_stable_ordinal_order() -> None:
    reader = _Reader()

    detail = _facade(reader).get("exp-query-1")

    assert detail is not None
    assert detail.experiment_id == "exp-query-1"
    assert detail.research_cycle_id == "cycle-1"
    assert detail.status == "queued"
    assert detail.queue_ordinal == 4
    assert detail.revision == 1
    assert detail.candidate_count == 2
    assert [candidate.ordinal for candidate in detail.candidates] == [1, 2]
    assert detail.candidates[0].is_baseline is True
    assert [fold.candidate_id for fold in detail.folds] == [
        "candidate-baseline",
        "candidate-default",
    ]
    assert detail.fold_protocol_id == "r3-complete-month-walk-forward"
    assert detail.fold_run_limit == 7
    assert detail.selection_state is None


def test_detail_recovers_persisted_candidate_selection_server_truth() -> None:
    reader = _Reader()
    assert reader.projection is not None
    reader.projection = replace(
        reader.projection,
        record=replace(
            reader.projection.record,
            status=ExperimentStatus.RUNNING,
            stage=ExperimentStage.CANDIDATE_SELECTION,
        ),
        revision=9,
        updated_at=NOW + timedelta(minutes=1),
    )
    reader.events = (
        StatusEventRecord(
            event_id="event-selection-1",
            experiment_id=ExperimentId("exp-query-1"),
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            subject_type=StatusSubjectType.EXPERIMENT,
            subject_revision=9,
            previous_status=ExperimentStatus.RUNNING,
            status=ExperimentStatus.RUNNING,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.CANDIDATE_SELECTION,
            failure_code=None,
            reason_code="candidate_preselected",
            detail={
                "candidate_evidence_artifact_id": "candidate-bundle-1",
                "candidate_evidence_content_hash": "d" * 64,
                "candidate_id": "candidate-default",
                "comparison_payload_hash": "e" * 64,
                "rationale": "objective winner",
                "schema_version": 1,
                "selection_evidence_content_hash": "f" * 64,
                "selection_id": "candidate-selection:one",
            },
            detail_hash=ContentHash("1" * 64),
            occurred_at=NOW + timedelta(minutes=1),
        ),
    )

    detail = _facade(reader).get("exp-query-1")

    assert detail is not None
    assert detail.selection_state is not None
    assert detail.selection_state.selection_id == "candidate-selection:one"
    assert detail.selection_state.experiment_id == "exp-query-1"
    assert detail.selection_state.candidate_id == "candidate-default"
    assert detail.selection_state.revision == 9
    assert detail.selection_state.event_id == "event-selection-1"
    assert detail.selection_state.holdout_claim_id is None


def test_detail_retries_once_after_parent_drift_and_returns_one_coherent_view() -> None:
    class _OneParentDriftReader(_Reader):
        def __init__(self) -> None:
            super().__init__()
            self.projection_reads = 0
            self.drifted = False

        def get_experiment_projection(self, experiment_id: ExperimentId):
            self.projection_reads += 1
            return self.projection

        def get_research_cycle_identity(self, experiment_id: ExperimentId):
            if not self.drifted:
                assert self.projection is not None
                self.projection = _running_projection(self.projection)
                self.folds = (_running_fold(self.folds[0]), *self.folds[1:])
                self.drifted = True
            return self.cycle

    reader = _OneParentDriftReader()

    detail = _facade(reader).get("exp-query-1")

    assert detail is not None
    assert detail.status == "running"
    assert detail.revision == 2
    assert detail.folds[0].status == "running"
    assert reader.projection_reads == 4


def test_detail_fails_closed_after_parent_projection_drifts_twice() -> None:
    class _ContinuouslyDriftingReader(_Reader):
        def __init__(self) -> None:
            super().__init__()
            self.projection_reads = 0
            self.drift_count = 0

        def get_experiment_projection(self, experiment_id: ExperimentId):
            self.projection_reads += 1
            return self.projection

        def get_research_cycle_identity(self, experiment_id: ExperimentId):
            assert self.projection is not None
            self.drift_count += 1
            stage = (
                ExperimentStage.PREFLIGHT
                if self.drift_count == 1
                else ExperimentStage.EXPLORATION
            )
            running = _running_projection(self.projection)
            self.projection = replace(
                running,
                record=replace(running.record, stage=stage),
            )
            return self.cycle

    reader = _ContinuouslyDriftingReader()

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details["code"] == "EXPERIMENT_READ_INTEGRITY"
    assert exc_info.value.details["reason"] == "concurrent_experiment_update"
    assert reader.projection_reads == 4


def test_detail_treats_projection_disappearance_after_initial_read_as_drift() -> None:
    class _DisappearingProjectionReader(_Reader):
        def __init__(self) -> None:
            super().__init__()
            self.projection_reads = 0

        def get_experiment_projection(self, experiment_id: ExperimentId):
            self.projection_reads += 1
            if self.projection_reads == 1:
                return self.projection
            return None

    reader = _DisappearingProjectionReader()

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details["reason"] == "concurrent_experiment_update"


def test_detail_accepts_fold_change_while_running_parent_is_stable() -> None:
    class _StableRunningReader(_Reader):
        def __init__(self) -> None:
            super().__init__()
            assert self.projection is not None
            self.projection = _running_projection(self.projection)
            self.projection_reads = 0
            self.fold_changed = False

        def get_experiment_projection(self, experiment_id: ExperimentId):
            self.projection_reads += 1
            return self.projection

        def list_folds(self, experiment_id: ExperimentId):
            if not self.fold_changed:
                self.folds = (_running_fold(self.folds[0]), *self.folds[1:])
                self.fold_changed = True
            return tuple(reversed(self.folds))

    reader = _StableRunningReader()

    detail = _facade(reader).get("exp-query-1")

    assert detail is not None
    assert detail.status == "running"
    assert detail.folds[0].status == "running"
    assert reader.projection_reads == 2


@pytest.mark.parametrize(
    ("parent_status", "desired_state"),
    [
        (ExperimentStatus.DRAFT, ExperimentDesiredState.RUN),
        (ExperimentStatus.BLOCKED, ExperimentDesiredState.RUN),
        (ExperimentStatus.QUEUED, ExperimentDesiredState.RUN),
        (ExperimentStatus.PAUSED, ExperimentDesiredState.PAUSE),
    ],
)
def test_detail_rejects_running_fold_for_non_running_parent(
    parent_status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    reader = _Reader()
    assert reader.projection is not None
    reader.projection = replace(
        reader.projection,
        record=replace(
            reader.projection.record,
            status=parent_status,
            desired_state=desired_state,
        ),
        queue_ordinal=None
        if parent_status in {ExperimentStatus.DRAFT, ExperimentStatus.BLOCKED}
        else reader.projection.queue_ordinal,
    )
    reader.folds = (_running_fold(reader.folds[0]), *reader.folds[1:])

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details == {
        "code": "EXPERIMENT_READ_INTEGRITY",
        "reason": "fold_parent_status_mismatch",
        "experiment_id": "exp-query-1",
        "parent_status": parent_status.value,
        "candidate_id": "candidate-baseline",
        "fold_id": "candidate-baseline-exploration",
        "fold_status": "running",
    }


@pytest.mark.parametrize(
    ("parent_status", "failure_code"),
    [
        (ExperimentStatus.CANCELLED, None),
        (ExperimentStatus.COMPLETED, None),
        (
            ExperimentStatus.COMPLETED_WITH_FAILURES,
            ExperimentFailureCode.CANDIDATE_FAILED,
        ),
        (ExperimentStatus.FAILED, ExperimentFailureCode.SYSTEM_ERROR),
    ],
)
def test_detail_rejects_live_fold_for_terminal_parent(
    parent_status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
) -> None:
    reader = _Reader()
    assert reader.projection is not None
    reader.projection = replace(
        reader.projection,
        record=replace(
            reader.projection.record,
            status=parent_status,
            failure_code=failure_code,
        ),
    )

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details["reason"] == "fold_parent_status_mismatch"
    assert exc_info.value.details["parent_status"] == parent_status.value
    assert exc_info.value.details["fold_status"] == "queued"


@pytest.mark.parametrize(
    ("parent_status", "desired_state"),
    [
        (ExperimentStatus.PAUSE_REQUESTED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.CANCEL_REQUESTED, ExperimentDesiredState.CANCEL),
    ],
)
def test_detail_allows_running_fold_while_parent_transition_is_draining(
    parent_status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    reader = _Reader()
    assert reader.projection is not None
    reader.projection = replace(
        reader.projection,
        record=replace(
            reader.projection.record,
            status=parent_status,
            desired_state=desired_state,
        ),
    )
    reader.folds = (_running_fold(reader.folds[0]), *reader.folds[1:])

    detail = _facade(reader).get("exp-query-1")

    assert detail is not None
    assert detail.status == parent_status.value
    assert detail.folds[0].status == "running"


def test_detail_keeps_partial_draft_fold_growth_visible() -> None:
    class _GrowingDraftReader(_Reader):
        def __init__(self) -> None:
            super().__init__()
            assert self.projection is not None
            self.projection = replace(
                self.projection,
                record=replace(
                    self.projection.record,
                    status=ExperimentStatus.DRAFT,
                ),
                queue_ordinal=None,
                revision=0,
            )
            self.projection_reads = 0
            self.remaining_fold = self.folds[1]
            self.folds = self.folds[:1]

        def get_experiment_projection(self, experiment_id: ExperimentId):
            self.projection_reads += 1
            return self.projection

        def list_folds(self, experiment_id: ExperimentId):
            self.folds = (*self.folds, self.remaining_fold)
            return tuple(reversed(self.folds))

    reader = _GrowingDraftReader()

    detail = _facade(reader).get("exp-query-1")

    assert detail is not None
    assert detail.status == "draft"
    assert detail.fold_count == 2
    assert reader.projection_reads == 2


@pytest.mark.parametrize("missing", ["cycle", "spec"])
def test_partial_persisted_aggregate_fails_closed(missing: str) -> None:
    reader = _Reader()
    setattr(reader, missing, None)

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details["code"] == "EXPERIMENT_READ_INTEGRITY"
    assert exc_info.value.details["reason"] == "partial_experiment_aggregate"


def test_gate_read_rejects_cross_experiment_lineage() -> None:
    reader = _Reader()
    reader.gate = GateEvaluationRecord(
        evaluation_id="gate-1",
        experiment_id=ExperimentId("different-experiment"),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        rule_id="validation.history",
        policy_version="r3-v1",
        layer="preflight",
        outcome="pass",
        observed={"eligible_months": 96},
        policy={"minimum_months": 96},
        artifact_id=None,
        evaluated_at=NOW,
    )

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get_gate(
            "exp-query-1",
            "gate-1",
        )

    assert exc_info.value.details["code"] == "EXPERIMENT_READ_INTEGRITY"
    assert exc_info.value.details["reason"] == "gate_experiment_mismatch"


def test_missing_experiment_projection_returns_none() -> None:
    reader = _Reader()
    reader.cycle = None
    reader.spec = None
    reader.projection = None

    assert _facade(reader).get("exp-query-1") is None


def test_absent_projection_is_a_coherent_read_during_concurrent_root_create() -> None:
    class _RootCreatedAfterCycleRead(_Reader):
        def __init__(self) -> None:
            super().__init__()
            self.cycle = None
            self.spec = None
            self.projection = None
            self.cycle_read_count = 0

        def get_research_cycle_identity(self, experiment_id: ExperimentId):
            observed = self.cycle
            self.cycle_read_count += 1
            self.cycle, self.spec, self.projection, self.folds = _aggregate()
            return observed

    reader = _RootCreatedAfterCycleRead()

    assert _facade(reader).get("exp-query-1") is None
    assert reader.cycle_read_count == 0


def test_analysis_read_error_is_translated_without_leaking_analysis_exception() -> None:
    reader = _Reader()
    reader.read_error = ExperimentPersistenceError(
        "storage unavailable",
        details={"reason_code": "experiment_read_failed"},
    )

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details == {
        "code": "EXPERIMENT_READ_FAILED",
        "reason_code": "experiment_read_failed",
    }
    assert isinstance(exc_info.value.__cause__, ExperimentPersistenceError)


def test_candidate_drift_from_launch_spec_fails_closed() -> None:
    reader = _Reader()
    reader.candidates = reader.candidates[:-1]

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details["reason"] == "candidate_aggregate_mismatch"


def test_fold_projection_key_drift_fails_closed() -> None:
    reader = _Reader()
    view = reader.folds[0]
    drifted_key = FoldKey(
        experiment_id=view.spec.key.experiment_id,
        candidate_id=view.spec.key.candidate_id,
        fold_id=FoldId("different-fold"),
    )
    reader.folds = (
        FoldView(
            spec=view.spec,
            projection=replace(view.projection, key=drifted_key),
        ),
        *reader.folds[1:],
    )

    with pytest.raises(AppQueryError) as exc_info:
        _facade(reader).get("exp-query-1")

    assert exc_info.value.details["reason"] == "fold_lineage_mismatch"


def test_gate_maps_nested_values_to_deeply_immutable_application_values() -> None:
    reader = _Reader()
    reader.gate = GateEvaluationRecord(
        evaluation_id="gate-1",
        experiment_id=ExperimentId("exp-query-1"),
        candidate_id=CandidateId("candidate-default"),
        fold_id=None,
        attempt_id=None,
        rule_id="validation.history",
        policy_version="r3-v1",
        layer="preflight",
        outcome="pass",
        observed={"windows": [{"months": 96}]},
        policy={"minimum_months": 96},
        artifact_id=None,
        evaluated_at=NOW,
    )

    gate = _facade(reader).get_gate("exp-query-1", "gate-1")

    assert gate is not None
    assert gate.experiment_id == "exp-query-1"
    assert gate.candidate_id == "candidate-default"
    assert gate.observed == {"windows": ({"months": 96},)}
    observed = cast("dict[str, object]", gate.observed)
    with pytest.raises(TypeError):
        observed["windows"] = ()
    nested = cast("tuple[dict[str, object], ...]", observed["windows"])[0]
    with pytest.raises(TypeError):
        nested["months"] = 97


def test_missing_gate_returns_none() -> None:
    assert _facade(_Reader()).get_gate("exp-query-1", "missing-gate") is None
