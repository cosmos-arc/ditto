"""Concurrency and fencing tests for the singleton experiment scheduler lease."""

# Imports inside _api are intentionally reflected into a SimpleNamespace.
# ruff: noqa: F401

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
    AttemptId,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    CheckpointRef,
    ContentHash,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldProtocolSpec,
    ResearchMetricDirection,
    ResearchMetricId,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PromotionObjective,
)

NOW = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)
NOW_US = 1_768_000_000_000_000


def _api() -> SimpleNamespace:
    from ditto_analysis.errors import (
        ExperimentConflictError,
        ExperimentIntegrityError,
        ExperimentLeaseLostError,
        ExperimentPersistenceError,
    )
    from ditto_analysis.experiments.persistence import (
        AttemptPersistenceSpec,
        AttemptProjection,
        DateWindow,
        FoldKey,
        FoldPersistenceSpec,
        FoldProjection,
        FoldRole,
        ResearchCycleIdentity,
        canonical_payload,
    )
    from ditto_analysis.storage.sqlite.experiments import (
        ResearchExperimentDatabase,
        SQLiteExperimentReader,
        SQLiteExperimentWriter,
    )

    return SimpleNamespace(**locals())


def _launch(experiment_id: str = "experiment-1") -> ExperimentLaunchSpec:
    candidates = (
        CandidateSpec(CandidateId("candidate-1"), 1, True, {"x": 1}),
        CandidateSpec(CandidateId("candidate-2"), 2, False, {"x": 2}),
    )
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
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
            CandidateId("candidate-1"),
            "Test durable scheduler behavior.",
            TrialFamilyDeclaration(
                "scheduler-test-family",
                tuple(
                    LogicalTrialIdentity(
                        ExperimentId(experiment_id),
                        candidate.candidate_id,
                        candidate.ordinal,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    )
                    for candidate in candidates
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec("r3-walk-forward", 1, ContentHash("b" * 64)),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 1024),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _initial_record(experiment_id: str = "experiment-1") -> ExperimentRecord:
    return ExperimentRecord(
        ExperimentId(experiment_id),
        ExperimentStatus.DRAFT,
        ExperimentDesiredState.RUN,
        ExperimentStage.PREFLIGHT,
        NOW,
    )


def _store(tmp_path: Path) -> tuple[Any, Any, Any, SimpleNamespace]:
    api = _api()
    database = api.ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = api.SQLiteExperimentReader(database)
    writer = api.SQLiteExperimentWriter(database)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-2026-h2", ContentHash("c" * 64)),
        _launch(),
        _initial_record(),
    )
    return database, reader, writer, api


def _add_fold(
    writer: Any,
    api: SimpleNamespace,
    *,
    candidate_id: str = "candidate-1",
    fold_id: str = "fold-1",
    ordinal: int = 1,
) -> Any:
    key = api.FoldKey(
        ExperimentId("experiment-1"), CandidateId(candidate_id), FoldId(fold_id)
    )
    spec = api.FoldPersistenceSpec.create(
        key,
        ordinal,
        api.FoldRole.WALK_FORWARD,
        api.DateWindow(date(2024, 1, 2), date(2025, 12, 31)),
        api.DateWindow(date(2026, 1, 5), date(2026, 3, 31)),
        2,
        1,
    )
    projection = api.FoldProjection(key, ExperimentStatus.QUEUED, None, NOW, NOW, 0)
    writer.add_fold(spec, projection)
    return key


def _attempt(
    api: SimpleNamespace,
    key: Any,
    attempt_id: str = "attempt-1",
    *,
    ordinal: int = 1,
    parent_attempt_id: AttemptId | None = None,
    resume_from_run_id: BacktestRunId | None = None,
    fingerprint: ContentHash | None = None,
) -> Any:
    spec = api.AttemptPersistenceSpec(
        AttemptId(attempt_id),
        key,
        ordinal,
        parent_attempt_id,
        resume_from_run_id,
        fingerprint or ContentHash("d" * 64),
        NOW,
    )
    projection = api.AttemptProjection(
        AttemptId(attempt_id),
        ExperimentStatus.QUEUED,
        None,
        None,
        None,
        NOW,
        NOW,
        0,
    )
    return spec, projection


def _enqueue_experiment(
    writer: Any,
    experiment_id: ExperimentId = ExperimentId("experiment-1"),
) -> Any:
    return writer.enqueue_experiment(
        experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer, experiment_id),
    )


def _current_enqueue_fence(
    writer: Any,
    experiment_id: ExperimentId = ExperimentId("experiment-1"),
) -> ExperimentEnqueueFence:
    reader = writer._reader
    return ExperimentEnqueueFence.create(
        gates=reader.list_gate_evaluations(experiment_id),
        folds=tuple(view.spec for view in reader.list_folds(experiment_id)),
    )


def _claim_queued_experiment(
    writer: Any,
    *,
    experiment_id: ExperimentId = ExperimentId("experiment-1"),
    owner: str = "owner-a",
    expected_slot_revision: int = 0,
    now_epoch_us: int = NOW_US,
    lease_until_epoch_us: int = NOW_US + 100,
) -> tuple[Any, Any]:
    queued = _enqueue_experiment(writer, experiment_id)
    lease = writer.try_claim_lease(
        experiment_id,
        owner,
        expected_revision=expected_slot_revision,
        now_epoch_us=now_epoch_us,
        lease_until_epoch_us=lease_until_epoch_us,
    )
    assert lease is not None
    return lease, queued


def _start_running_experiment(
    writer: Any,
    *,
    experiment_id: ExperimentId = ExperimentId("experiment-1"),
    owner: str = "owner-a",
    lease_until_epoch_us: int = NOW_US + 100,
) -> tuple[Any, Any]:
    lease, queued = _claim_queued_experiment(
        writer,
        experiment_id=experiment_id,
        owner=owner,
        lease_until_epoch_us=lease_until_epoch_us,
    )
    running = writer.transition_scheduled_experiment(
        experiment_id,
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=queued.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="dispatch",
        detail={},
    )
    return lease, running


def _start_running_attempt(
    writer: Any,
    api: SimpleNamespace,
    key: Any,
    *,
    owner: str = "owner-a",
    lease_until_epoch_us: int = NOW_US + 10,
) -> tuple[Any, Any, Any]:
    lease, _running_experiment = _start_running_experiment(
        writer,
        experiment_id=key.experiment_id,
        owner=owner,
        lease_until_epoch_us=lease_until_epoch_us,
    )
    spec, projection = _attempt(api, key)
    writer.claim_fold_and_add_attempt(
        key,
        spec,
        projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    running = writer.transition_attempt(
        spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-1"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    return lease, spec, running


def test_fresh_schema_has_exactly_one_free_global_slot(tmp_path: Path) -> None:
    _database, reader, _writer, _api_ns = _store(tmp_path)

    slot = reader.get_scheduler_slot()

    assert slot.slot_id == "global"
    assert slot.experiment_id is None
    assert slot.owner_token is None
    assert slot.revision == 0


def test_enqueue_allocates_queue_ordinals_atomically_and_reader_orders_them(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    barrier = Barrier(2)

    def enqueue(experiment_id: str) -> Any:
        barrier.wait()
        return writer.enqueue_experiment(
            ExperimentId(experiment_id),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={"certified": True},
            launch_fence=_current_enqueue_fence(writer, ExperimentId(experiment_id)),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        projections = tuple(executor.map(enqueue, ("experiment-1", "experiment-2")))

    assert {projection.queue_ordinal for projection in projections} == {1, 2}
    dispatchable = reader.list_dispatchable_experiments()
    assert [projection.queue_ordinal for projection in dispatchable] == [1, 2]
    assert [projection.record.status for projection in dispatchable] == [
        ExperimentStatus.QUEUED,
        ExperimentStatus.QUEUED,
    ]


def test_unowned_queued_cancel_drains_then_allows_the_next_queue_item(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    queued_first = _enqueue_experiment(writer)
    _enqueue_experiment(writer, ExperimentId("experiment-2"))
    cancel_requested = writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=queued_first.record.stage,
        failure_code=None,
        expected_revision=queued_first.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )

    candidates = reader.list_dispatchable_experiments()
    assert [candidate.record.experiment_id for candidate in candidates] == [
        ExperimentId("experiment-1"),
        ExperimentId("experiment-2"),
    ]
    assert [candidate.record.status for candidate in candidates] == [
        ExperimentStatus.CANCEL_REQUESTED,
        ExperimentStatus.QUEUED,
    ]

    drain_lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-drain",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert drain_lease is not None
    writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.CANCELLED,
        target_stage=cancel_requested.record.stage,
        failure_code=None,
        expected_revision=cancel_requested.revision,
        lease_fence=drain_lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="cancel_drained",
        detail={},
    )
    released = writer.release_lease(
        drain_lease.fence,
        now_epoch_us=NOW_US + 2,
    )

    next_lease = writer.try_claim_lease(
        ExperimentId("experiment-2"),
        "owner-next",
        expected_revision=released.revision,
        now_epoch_us=NOW_US + 3,
        lease_until_epoch_us=NOW_US + 200,
    )
    assert next_lease is not None


def test_queued_origin_cancel_waits_for_queued_folds_before_terminal_release(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    queued = _enqueue_experiment(writer)
    cancel_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=queued.record.stage,
        failure_code=None,
        expected_revision=queued.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    lease = writer.try_claim_lease(
        key.experiment_id,
        "owner-drain",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    before_experiment = reader.get_experiment_projection(key.experiment_id)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            key.experiment_id,
            target_status=ExperimentStatus.CANCELLED,
            target_stage=cancel_requested.record.stage,
            failure_code=None,
            expected_revision=cancel_requested.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 1,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="cancel_before_fold_drain",
            detail={},
        )

    assert exc_info.value.details == {
        "reason_code": "experiment_live_child",
        "target_status": ExperimentStatus.CANCELLED.value,
        "child_type": "fold",
        "child_status": ExperimentStatus.QUEUED.value,
        "candidate_id": "candidate-1",
        "fold_id": "fold-1",
    }
    assert reader.get_experiment_projection(key.experiment_id) == before_experiment
    assert reader.list_status_events(key.experiment_id) == before_events

    cancelled_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.CANCELLED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        reason_code="cancel_queued_fold",
        detail={},
    )
    cancelled = writer.transition_scheduled_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCELLED,
        target_stage=cancel_requested.record.stage,
        failure_code=None,
        expected_revision=cancel_requested.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="cancel_drained",
        detail={},
    )
    released = writer.release_lease(lease.fence, now_epoch_us=NOW_US + 4)

    assert cancelled_fold.status is ExperimentStatus.CANCELLED
    assert cancelled.record.status is ExperimentStatus.CANCELLED
    assert released.experiment_id is None


def test_terminal_transition_waits_for_running_attempt_then_releases_after_drain(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, attempt_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_experiment = reader.get_experiment_projection(key.experiment_id)
    cancel_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            key.experiment_id,
            target_status=ExperimentStatus.CANCELLED,
            target_stage=cancel_requested.record.stage,
            failure_code=None,
            expected_revision=cancel_requested.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
            occurred_at=NOW,
            attempt_started=True,
            precondition_repairable=False,
            reason_code="cancel_before_attempt_drain",
            detail={},
        )

    assert exc_info.value.details == {
        "reason_code": "experiment_live_child",
        "target_status": ExperimentStatus.CANCELLED.value,
        "child_type": "attempt",
        "child_status": ExperimentStatus.RUNNING.value,
        "attempt_id": str(attempt_spec.attempt_id),
    }
    assert reader.get_experiment_projection(key.experiment_id) == cancel_requested
    assert reader.list_status_events(key.experiment_id) == before_events

    cancelled_attempt = writer.transition_attempt(
        attempt_spec.attempt_id,
        target_status=ExperimentStatus.CANCELLED,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="attempt_cancelled",
        detail={},
    )
    running_fold = reader.get_fold(key).projection
    cancelled_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.CANCELLED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=running_fold.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
        reason_code="fold_cancelled",
        detail={},
    )
    cancelled = writer.transition_scheduled_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCELLED,
        target_stage=cancel_requested.record.stage,
        failure_code=None,
        expected_revision=cancel_requested.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 7,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="cancel_drained",
        detail={},
    )
    released = writer.release_lease(lease.fence, now_epoch_us=NOW_US + 8)

    assert cancelled_attempt.status is ExperimentStatus.CANCELLED
    assert cancelled_fold.status is ExperimentStatus.CANCELLED
    assert cancelled.record.status is ExperimentStatus.CANCELLED
    assert released.experiment_id is None


def test_terminal_transition_rejects_running_fold_without_an_attempt(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    claimed_fold = writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    cancel_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            key.experiment_id,
            target_status=ExperimentStatus.CANCELLED,
            target_stage=cancel_requested.record.stage,
            failure_code=None,
            expected_revision=cancel_requested.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="cancel_before_fold_drain",
            detail={},
        )

    assert exc_info.value.details == {
        "reason_code": "experiment_live_child",
        "target_status": ExperimentStatus.CANCELLED.value,
        "child_type": "fold",
        "child_status": ExperimentStatus.RUNNING.value,
        "candidate_id": "candidate-1",
        "fold_id": "fold-1",
    }
    assert reader.get_experiment_projection(key.experiment_id) == cancel_requested
    assert reader.get_fold(key).projection == claimed_fold


def test_unowned_non_queued_origin_cancel_request_fails_closed(
    tmp_path: Path,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    lease, running = _start_running_experiment(writer)
    writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment_scheduler_slot
        SET experiment_id=NULL, owner_token=NULL, lease_until_epoch_us=NULL,
            acquired_at_epoch_us=NULL, renewed_at_epoch_us=NULL,
            revision=revision + 1
        WHERE slot_id='global'
        """
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(_api_ns.ExperimentIntegrityError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-invalid",
            expected_revision=lease.fence.revision + 1,
            now_epoch_us=NOW_US + 2,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert (
        exc_info.value.details["reason_code"]
        == "scheduler_active_experiment_without_slot"
    )
    assert reader.get_scheduler_slot() == before_slot


def test_free_slot_rejects_out_of_order_queue_claim_without_occupying_slot(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    for experiment_id in ("experiment-1", "experiment-2"):
        writer.enqueue_experiment(
            ExperimentId(experiment_id),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer, ExperimentId(experiment_id)),
        )
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-2"),
            "owner-b",
            expected_revision=0,
            now_epoch_us=NOW_US,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert exc_info.value.details["reason_code"] == "scheduler_queue_order_violation"
    assert reader.get_scheduler_slot() == before_slot
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None


def test_non_run_queue_head_blocks_all_free_slot_claims_without_being_skipped(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    for experiment_id in ("experiment-1", "experiment-2"):
        writer.enqueue_experiment(
            ExperimentId(experiment_id),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer, ExperimentId(experiment_id)),
        )
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET desired_state='pause', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-2"),
            "owner-b",
            expected_revision=0,
            now_epoch_us=NOW_US,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert (
        exc_info.value.details["reason_code"] == "scheduler_queue_head_intent_mismatch"
    )
    assert reader.get_scheduler_slot() == before_slot


@pytest.mark.parametrize(
    "status",
    [
        ExperimentStatus.DRAFT,
        ExperimentStatus.BLOCKED,
        ExperimentStatus.COMPLETED,
    ],
)
def test_free_slot_rejects_non_queued_experiment_lifecycle(
    tmp_path: Path,
    status: ExperimentStatus,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    if status is ExperimentStatus.BLOCKED:
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=status,
            target_desired_state=ExperimentDesiredState.RUN,
            target_stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            expected_revision=0,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=True,
            reason_code="preflight_blocked",
            detail={},
        )
    elif status is ExperimentStatus.COMPLETED:
        writer.enqueue_experiment(
            ExperimentId("experiment-1"),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer),
        )
        connection = database.get_connection()
        connection.execute(
            """
            UPDATE experiment SET status='completed', revision=revision + 1
            WHERE experiment_id='experiment-1'
            """
        )
        connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-a",
            expected_revision=0,
            now_epoch_us=NOW_US,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert exc_info.value.details["reason_code"] == "scheduler_experiment_not_eligible"
    assert reader.get_scheduler_slot() == before_slot


def test_claimable_fold_reader_orders_candidate_then_fold_ordinal(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    for candidate_id, fold_id, ordinal in (
        ("candidate-2", "fold-2", 2),
        ("candidate-1", "fold-2", 2),
        ("candidate-2", "fold-1", 1),
        ("candidate-1", "fold-1", 1),
    ):
        _add_fold(
            writer,
            api,
            candidate_id=candidate_id,
            fold_id=fold_id,
            ordinal=ordinal,
        )

    claimable = reader.list_claimable_folds(ExperimentId("experiment-1"))
    assert [
        (str(view.spec.key.candidate_id), str(view.spec.key.fold_id))
        for view in claimable
    ] == [
        ("candidate-1", "fold-1"),
        ("candidate-1", "fold-2"),
        ("candidate-2", "fold-1"),
        ("candidate-2", "fold-2"),
    ]


def test_claim_contention_and_expiry_boundary_have_precise_semantics(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    first, _queued = _claim_queued_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert first.fence.revision == 1

    assert (
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-b",
            expected_revision=1,
            now_epoch_us=NOW_US + 99,
            lease_until_epoch_us=NOW_US + 200,
        )
        is None
    )
    reclaimed = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-b",
        expected_revision=1,
        now_epoch_us=NOW_US + 100,
        lease_until_epoch_us=NOW_US + 200,
    )
    assert reclaimed is not None
    assert reclaimed.fence.owner_token == "owner-b"
    assert reclaimed.fence.revision == 2
    assert reader.get_scheduler_slot().owner_token == "owner-b"

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.release_lease(first.fence, now_epoch_us=NOW_US + 101)


def test_expired_active_occupant_must_be_reclaimed_before_next_queue_item(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    for experiment_id in ("experiment-1", "experiment-2"):
        writer.enqueue_experiment(
            ExperimentId(experiment_id),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer, ExperimentId(experiment_id)),
        )
    first = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert first is not None
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-2"),
            "owner-b",
            expected_revision=first.revision,
            now_epoch_us=NOW_US + 10,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert exc_info.value.details["reason_code"] == "scheduler_reclaim_required"
    assert reader.get_scheduler_slot() == before_slot


def test_expired_occupant_intent_drift_fails_closed_without_slot_mutation(
    tmp_path: Path,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    first = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert first is not None
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET desired_state='pause', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-b",
            expected_revision=first.revision,
            now_epoch_us=NOW_US + 10,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert exc_info.value.details["reason_code"] == "scheduler_occupant_intent_mismatch"
    assert reader.get_scheduler_slot() == before_slot


def test_expired_illegal_occupant_lifecycle_fails_closed(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment_scheduler_slot
        SET experiment_id='experiment-1', owner_token='owner-a',
            lease_until_epoch_us=?, acquired_at_epoch_us=?,
            renewed_at_epoch_us=?, revision=1
        WHERE slot_id='global' AND revision=0
        """,
        (NOW_US + 10, NOW_US, NOW_US),
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-b",
            expected_revision=1,
            now_epoch_us=NOW_US + 10,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert (
        exc_info.value.details["reason_code"] == "scheduler_invalid_occupant_lifecycle"
    )
    assert reader.get_scheduler_slot() == before_slot


def test_terminal_expired_occupant_allows_current_queue_head_to_take_slot(
    tmp_path: Path,
) -> None:
    database, _reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    for experiment_id in ("experiment-1", "experiment-2"):
        writer.enqueue_experiment(
            ExperimentId(experiment_id),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer, ExperimentId(experiment_id)),
        )
    first = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert first is not None
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status='completed', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()

    second = writer.try_claim_lease(
        ExperimentId("experiment-2"),
        "owner-b",
        expected_revision=first.revision,
        now_epoch_us=NOW_US + 10,
        lease_until_epoch_us=NOW_US + 100,
    )

    assert second is not None
    assert second.experiment_id == ExperimentId("experiment-2")


def test_terminal_expired_occupant_with_live_child_blocks_slot_handoff(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    key = _add_fold(writer, api)
    first, attempt_spec, _running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 10,
    )
    _enqueue_experiment(writer, ExperimentId("experiment-2"))
    running_experiment = reader.get_experiment_projection(key.experiment_id)
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status='cancelled', revision=revision + 1
        WHERE experiment_id=?
        """,
        (str(key.experiment_id),),
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()
    before_fold = reader.get_fold(key)
    before_attempt = reader.get_attempt(attempt_spec.attempt_id)
    before_changes = connection.total_changes

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-2"),
            "owner-b",
            expected_revision=first.revision,
            now_epoch_us=NOW_US + 10,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert exc_info.value.details == {
        "reason_code": "scheduler_terminal_live_child",
        "target_status": ExperimentStatus.CANCELLED.value,
        "child_type": "attempt",
        "child_status": ExperimentStatus.RUNNING.value,
        "attempt_id": str(attempt_spec.attempt_id),
    }
    assert reader.get_scheduler_slot() == before_slot
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id) == before_attempt
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


@pytest.mark.parametrize(
    ("status", "desired_state"),
    [
        (ExperimentStatus.QUEUED, ExperimentDesiredState.RUN),
        (ExperimentStatus.RUNNING, ExperimentDesiredState.RUN),
        (ExperimentStatus.PAUSE_REQUESTED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.PAUSED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.CANCEL_REQUESTED, ExperimentDesiredState.CANCEL),
    ],
)
def test_expired_active_occupant_can_reclaim_its_own_slot(
    tmp_path: Path,
    status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    first = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert first is not None
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status=?, desired_state=?, revision=revision + 1
        WHERE experiment_id='experiment-1'
        """,
        (status.value, desired_state.value),
    )
    connection.commit()

    reclaimed = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-b",
        expected_revision=first.revision,
        now_epoch_us=NOW_US + 10,
        lease_until_epoch_us=NOW_US + 100,
    )

    assert reclaimed is not None
    assert reclaimed.owner_token == "owner-b"
    assert reader.get_scheduler_slot().revision == reclaimed.revision


def test_terminal_experiment_cannot_renew_but_can_release_its_slot(
    tmp_path: Path,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status='completed', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.renew_lease(
            lease.fence,
            now_epoch_us=NOW_US + 1,
            new_lease_until_epoch_us=NOW_US + 200,
        )

    assert exc_info.value.details["reason_code"] == "scheduler_renewal_not_allowed"
    assert reader.get_scheduler_slot() == before_slot
    released = writer.release_lease(lease.fence, now_epoch_us=NOW_US + 1)
    assert released.experiment_id is None


def test_release_rechecks_terminal_experiment_has_no_live_children(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, attempt_spec, _running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_experiment = reader.get_experiment_projection(key.experiment_id)
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status='cancelled', revision=revision + 1
        WHERE experiment_id=?
        """,
        (str(key.experiment_id),),
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()
    before_fold = reader.get_fold(key)
    before_attempt = reader.get_attempt(attempt_spec.attempt_id)
    before_changes = connection.total_changes

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.release_lease(lease.fence, now_epoch_us=NOW_US + 4)

    assert exc_info.value.details == {
        "reason_code": "scheduler_terminal_live_child",
        "target_status": ExperimentStatus.CANCELLED.value,
        "child_type": "attempt",
        "child_status": ExperimentStatus.RUNNING.value,
        "attempt_id": str(attempt_spec.attempt_id),
    }
    assert reader.get_scheduler_slot() == before_slot
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id) == before_attempt
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


def test_active_experiment_cannot_release_its_slot(
    tmp_path: Path,
) -> None:
    _database, reader, writer, _api_ns = _store(tmp_path)
    writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.release_lease(lease.fence, now_epoch_us=NOW_US + 1)

    assert exc_info.value.details["reason_code"] == "scheduler_release_not_allowed"
    assert reader.get_scheduler_slot() == before_slot


def test_free_slot_fails_closed_when_an_active_experiment_has_no_slot(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    writer.create_experiment(
        api.ResearchCycleIdentity("cycle-second", ContentHash("e" * 64)),
        _launch("experiment-2"),
        _initial_record("experiment-2"),
    )
    for experiment_id in ("experiment-1", "experiment-2"):
        writer.enqueue_experiment(
            ExperimentId(experiment_id),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer, ExperimentId(experiment_id)),
        )
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status='running', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_slot = reader.get_scheduler_slot()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-2"),
            "owner-b",
            expected_revision=0,
            now_epoch_us=NOW_US,
            lease_until_epoch_us=NOW_US + 100,
        )

    assert (
        exc_info.value.details["reason_code"]
        == "scheduler_active_experiment_without_slot"
    )
    assert reader.get_scheduler_slot() == before_slot
    assert not connection.in_transaction


def test_stale_claim_revision_is_not_reported_as_ordinary_contention(
    tmp_path: Path,
) -> None:
    _database, _reader, writer, api = _store(tmp_path)
    first, _queued = _claim_queued_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )

    assert (
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-b",
            expected_revision=first.revision,
            now_epoch_us=NOW_US + 1,
            lease_until_epoch_us=NOW_US + 200,
        )
        is None
    )
    with pytest.raises(api.ExperimentLeaseLostError) as exc_info:
        writer.try_claim_lease(
            ExperimentId("experiment-1"),
            "owner-c",
            expected_revision=0,
            now_epoch_us=NOW_US + 1,
            lease_until_epoch_us=NOW_US + 200,
        )
    assert exc_info.value.details["reason_code"] == "scheduler_lease_stale_revision"


@pytest.mark.parametrize("owner_count", [2, 8])
def test_concurrent_claims_have_exactly_one_winner(
    tmp_path: Path, owner_count: int
) -> None:
    database, _reader, writer, _api_ns = _store(tmp_path)
    _enqueue_experiment(writer)
    barrier = Barrier(owner_count)

    def claim(index: int) -> Any:
        barrier.wait()
        try:
            return writer.try_claim_lease(
                ExperimentId("experiment-1"),
                f"owner-{index}",
                expected_revision=0,
                now_epoch_us=NOW_US,
                lease_until_epoch_us=NOW_US + 1_000,
            )
        except _api_ns.ExperimentLeaseLostError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=owner_count) as executor:
        results = tuple(executor.map(claim, range(owner_count)))

    leases = tuple(
        result
        for result in results
        if not isinstance(result, _api_ns.ExperimentLeaseLostError)
    )
    stale = tuple(
        result
        for result in results
        if isinstance(result, _api_ns.ExperimentLeaseLostError)
    )
    assert len(leases) == 1
    assert len(stale) == owner_count - 1
    assert all(
        error.details["reason_code"] == "scheduler_lease_stale_revision"
        for error in stale
    )
    assert (
        database.get_connection()
        .execute(
            "SELECT revision FROM experiment_scheduler_slot WHERE slot_id='global'"
        )
        .fetchone()[0]
        == 1
    )


def test_renew_and_release_are_revisioned_and_fenced(tmp_path: Path) -> None:
    _database, reader, writer, api = _store(tmp_path)
    lease, queued = _claim_queued_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )

    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 10,
        new_lease_until_epoch_us=NOW_US + 200,
    )
    assert renewed.acquired_at_epoch_us == NOW_US
    assert renewed.renewed_at_epoch_us == NOW_US + 10
    assert renewed.fence.revision == 2

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.renew_lease(
            lease.fence,
            now_epoch_us=NOW_US + 11,
            new_lease_until_epoch_us=NOW_US + 300,
        )

    cancel_requested = writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.CANCEL_REQUESTED,
        target_desired_state=ExperimentDesiredState.CANCEL,
        target_stage=queued.record.stage,
        failure_code=None,
        expected_revision=queued.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_cancel",
        detail={},
    )
    writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.CANCELLED,
        target_stage=cancel_requested.record.stage,
        failure_code=None,
        expected_revision=cancel_requested.revision,
        lease_fence=renewed.fence,
        now_epoch_us=NOW_US + 12,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="cancel_drained",
        detail={},
    )
    released = writer.release_lease(renewed.fence, now_epoch_us=NOW_US + 13)
    assert released.owner_token is None
    assert released.revision == 3
    assert reader.get_scheduler_slot() == released


def test_scheduler_experiment_transition_requires_the_current_lease_fence(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 1,
        new_lease_until_epoch_us=NOW_US + 200,
    )

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.transition_scheduled_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.RUNNING,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            expected_revision=queued.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="dispatch",
            detail={},
        )
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == queued

    with pytest.raises(ExperimentSpecError) as stage_exc:
        writer.transition_scheduled_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.RUNNING,
            target_stage=ExperimentStage.WALK_FORWARD,
            failure_code=None,
            expected_revision=queued.revision,
            lease_fence=renewed.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="skip_exploration",
            detail={},
        )
    assert (
        stage_exc.value.details["reason_code"]
        == "scheduler_dispatch_requires_exploration"
    )

    running = writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=queued.revision,
        lease_fence=renewed.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="dispatch",
        detail={},
    )
    assert running.record.status is ExperimentStatus.RUNNING
    with pytest.raises(ExperimentSpecError) as terminal_exc:
        writer.transition_scheduled_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.COMPLETED,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            expected_revision=running.revision,
            lease_fence=renewed.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            attempt_started=True,
            precondition_repairable=False,
            reason_code="premature_completion",
            detail={},
        )
    assert terminal_exc.value.details["reason_code"] == "terminal_stage_not_evidence"


def test_resumed_scheduler_dispatch_preserves_later_stage() -> None:
    from ditto_analysis.storage.sqlite.experiments._experiment_control import (
        validate_experiment_status_stage_transition,
    )

    validate_experiment_status_stage_transition(
        ExperimentStatus.QUEUED,
        ExperimentStage.CANDIDATE_SELECTION,
        ExperimentStatus.RUNNING,
        ExperimentStage.CANDIDATE_SELECTION,
    )

    with pytest.raises(ExperimentSpecError) as captured:
        validate_experiment_status_stage_transition(
            ExperimentStatus.QUEUED,
            ExperimentStage.CANDIDATE_SELECTION,
            ExperimentStatus.RUNNING,
            ExperimentStage.HOLDOUT,
        )

    assert captured.value.details["reason_code"] == "experiment_stage_must_be_preserved"


@pytest.mark.parametrize(
    ("current_status", "target_status", "source_desired", "wrong_target_desired"),
    [
        (
            ExperimentStatus.DRAFT,
            ExperimentStatus.BLOCKED,
            ExperimentDesiredState.RUN,
            ExperimentDesiredState.PAUSE,
        ),
        (
            ExperimentStatus.QUEUED,
            ExperimentStatus.CANCEL_REQUESTED,
            ExperimentDesiredState.RUN,
            ExperimentDesiredState.RUN,
        ),
        (
            ExperimentStatus.RUNNING,
            ExperimentStatus.PAUSE_REQUESTED,
            ExperimentDesiredState.RUN,
            ExperimentDesiredState.RUN,
        ),
        (
            ExperimentStatus.RUNNING,
            ExperimentStatus.CANCEL_REQUESTED,
            ExperimentDesiredState.RUN,
            ExperimentDesiredState.RUN,
        ),
        (
            ExperimentStatus.PAUSED,
            ExperimentStatus.QUEUED,
            ExperimentDesiredState.PAUSE,
            ExperimentDesiredState.PAUSE,
        ),
        (
            ExperimentStatus.PAUSED,
            ExperimentStatus.CANCEL_REQUESTED,
            ExperimentDesiredState.PAUSE,
            ExperimentDesiredState.PAUSE,
        ),
    ],
)
def test_every_operator_edge_requires_its_exact_target_intent(
    tmp_path: Path,
    current_status: ExperimentStatus,
    target_status: ExperimentStatus,
    source_desired: ExperimentDesiredState,
    wrong_target_desired: ExperimentDesiredState,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    if current_status is ExperimentStatus.DRAFT:
        expected_revision = 0
    else:
        queued = writer.enqueue_experiment(
            ExperimentId("experiment-1"),
            expected_revision=0,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer),
        )
        expected_revision = queued.revision
        if current_status is not ExperimentStatus.QUEUED:
            connection = database.get_connection()
            connection.execute(
                """
                UPDATE experiment SET status=?, desired_state=?, revision=revision + 1
                WHERE experiment_id='experiment-1'
                """,
                (current_status.value, source_desired.value),
            )
            connection.commit()
            expected_revision += 1
    before_projection = reader.get_experiment_projection(ExperimentId("experiment-1"))
    before_events = reader.list_status_events(ExperimentId("experiment-1"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_experiment(
            ExperimentId("experiment-1"),
            target_status=target_status,
            target_desired_state=wrong_target_desired,
            target_stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            expected_revision=expected_revision,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=(target_status is ExperimentStatus.BLOCKED),
            reason_code="wrong_operator_intent",
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "experiment_desired_state_mismatch"
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == (
        before_projection
    )
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events


def test_pause_allows_queued_fold_and_retains_the_scheduler_slot(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(writer)
    pause_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )

    paused = writer.transition_scheduled_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSED,
        target_stage=pause_requested.record.stage,
        failure_code=None,
        expected_revision=pause_requested.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="pause_drained",
        detail={},
    )

    assert paused.record.status is ExperimentStatus.PAUSED
    assert reader.get_fold(key).projection.status is ExperimentStatus.QUEUED
    assert reader.get_scheduler_slot().experiment_id == key.experiment_id


def test_pause_rejects_running_fold_after_attempt_drain_without_writes(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    attempt_spec, attempt_projection = _attempt(api, key)
    running_fold, _queued_attempt = writer.claim_fold_and_add_attempt(
        key,
        attempt_spec,
        attempt_projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    running_attempt = writer.transition_attempt(
        attempt_spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-1"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    completed_attempt = writer.transition_attempt(
        attempt_spec.attempt_id,
        target_status=ExperimentStatus.COMPLETED,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="attempt_completed",
        detail={},
    )
    pause_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )

    preserved_fold = reader.get_fold(key).projection
    before_events = reader.list_status_events(key.experiment_id)
    before_slot = reader.get_scheduler_slot()
    connection = database.get_connection()
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            key.experiment_id,
            target_status=ExperimentStatus.PAUSED,
            target_stage=pause_requested.record.stage,
            failure_code=None,
            expected_revision=pause_requested.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 5,
            occurred_at=NOW,
            attempt_started=True,
            precondition_repairable=False,
            reason_code="pause_without_fold_requeue",
            detail={},
        )

    assert exc_info.value.details == {
        "reason_code": "experiment_live_child",
        "target_status": ExperimentStatus.PAUSED.value,
        "child_type": "fold",
        "child_status": ExperimentStatus.RUNNING.value,
        "candidate_id": "candidate-1",
        "fold_id": "fold-1",
    }
    assert reader.get_experiment_projection(key.experiment_id) == pause_requested
    assert reader.get_fold(key).projection == running_fold == preserved_fold
    assert reader.get_attempt(attempt_spec.attempt_id).projection == completed_attempt
    assert reader.list_status_events(key.experiment_id) == before_events
    assert reader.get_scheduler_slot() == before_slot
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


@pytest.mark.parametrize(
    ("child_state", "expected_child_type", "expected_child_status"),
    [
        ("queued_attempt", "attempt", ExperimentStatus.QUEUED),
        ("running_attempt", "attempt", ExperimentStatus.RUNNING),
    ],
)
def test_pause_rejects_live_child_without_writes(
    tmp_path: Path,
    child_state: str,
    expected_child_type: str,
    expected_child_status: ExperimentStatus,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    attempt_spec, attempt_projection = _attempt(api, key)
    writer.claim_fold_and_add_attempt(
        key,
        attempt_spec,
        attempt_projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    if child_state == "running_attempt":
        writer.transition_attempt(
            attempt_spec.attempt_id,
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=BacktestRunId("backtest-run-1"),
            checkpoint_ref=None,
            failure_code=None,
            expected_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            reason_code="attempt_started",
            detail={},
        )
    pause_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=(child_state == "running_attempt"),
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_attempt = reader.get_attempt(attempt_spec.attempt_id)
    before_events = reader.list_status_events(key.experiment_id)
    before_slot = reader.get_scheduler_slot()
    connection = database.get_connection()
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            key.experiment_id,
            target_status=ExperimentStatus.PAUSED,
            target_stage=pause_requested.record.stage,
            failure_code=None,
            expected_revision=pause_requested.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
            occurred_at=NOW,
            attempt_started=(child_state == "running_attempt"),
            precondition_repairable=False,
            reason_code="pause_before_child_drain",
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "experiment_live_child"
    assert exc_info.value.details["target_status"] == ExperimentStatus.PAUSED.value
    assert exc_info.value.details["child_type"] == expected_child_type
    assert exc_info.value.details["child_status"] == expected_child_status.value
    assert reader.get_experiment_projection(key.experiment_id) == pause_requested
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id) == before_attempt
    assert reader.list_status_events(key.experiment_id) == before_events
    assert reader.get_scheduler_slot() == before_slot
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


@pytest.mark.parametrize(
    "attempt_status",
    [ExperimentStatus.QUEUED, ExperimentStatus.RUNNING],
)
def test_pause_requeue_rejects_live_attempt_without_writes(
    tmp_path: Path,
    attempt_status: ExperimentStatus,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running_experiment = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    attempt_spec, initial_attempt = _attempt(api, key)
    _running_fold, live_attempt = writer.claim_fold_and_add_attempt(
        key,
        attempt_spec,
        initial_attempt,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    if attempt_status is ExperimentStatus.RUNNING:
        live_attempt = writer.transition_attempt(
            attempt_spec.attempt_id,
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=BacktestRunId("backtest-run-1"),
            checkpoint_ref=None,
            failure_code=None,
            expected_revision=live_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            reason_code="attempt_started",
            detail={},
        )
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=(attempt_status is ExperimentStatus.RUNNING),
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_attempt = reader.get_attempt(attempt_spec.attempt_id)
    before_events = reader.list_status_events(key.experiment_id)
    connection = database.get_connection()
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_fold_for_pause(
            key,
            expected_fold_revision=before_fold.projection.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
            occurred_at=NOW,
            detail={"checkpoint": "pending"},
        )

    assert exc_info.value.details == {
        "reason_code": "pause_requeue_live_attempt",
        "attempt_id": str(attempt_spec.attempt_id),
        "attempt_status": attempt_status.value,
    }
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id).projection == live_attempt
    assert reader.get_attempt(attempt_spec.attempt_id) == before_attempt
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


def test_pause_requeue_requires_pause_requested_parent_without_writes(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_fold = writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    before_events = reader.list_status_events(key.experiment_id)
    connection = database.get_connection()
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_fold_for_pause(
            key,
            expected_fold_revision=running_fold.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            detail={},
        )

    assert exc_info.value.details == {
        "reason_code": "pause_requeue_not_requested",
        "status": ExperimentStatus.RUNNING.value,
        "desired_state": ExperimentDesiredState.RUN.value,
    }
    assert reader.get_fold(key).projection == running_fold
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


@pytest.mark.parametrize(
    ("fence_case", "expected_reason", "now_epoch_us"),
    [
        ("wrong_owner", "scheduler_lease_lost", NOW_US + 3),
        ("expired", "scheduler_lease_expired", NOW_US + 10),
    ],
)
def test_pause_requeue_rejects_invalid_fence_without_writes(
    tmp_path: Path,
    fence_case: str,
    expected_reason: str,
    now_epoch_us: int,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 10,
    )
    running_fold = writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    fence = lease.fence
    if fence_case == "wrong_owner":
        fence = type(lease.fence)(
            experiment_id=lease.fence.experiment_id,
            owner_token="owner-b",
            revision=lease.fence.revision,
            lease_until_epoch_us=lease.fence.lease_until_epoch_us,
        )
    before_events = reader.list_status_events(key.experiment_id)
    before_slot = reader.get_scheduler_slot()
    connection = database.get_connection()
    before_changes = connection.total_changes

    with pytest.raises(api.ExperimentLeaseLostError) as exc_info:
        writer.requeue_fold_for_pause(
            key,
            expected_fold_revision=running_fold.revision,
            lease_fence=fence,
            now_epoch_us=now_epoch_us,
            occurred_at=NOW,
            detail={},
        )

    assert exc_info.value.details["reason_code"] == expected_reason
    assert reader.get_fold(key).projection == running_fold
    assert reader.list_status_events(key.experiment_id) == before_events
    assert reader.get_scheduler_slot() == before_slot
    assert connection.total_changes == before_changes
    assert not connection.in_transaction


def test_pause_requeue_event_failure_rolls_back_fold_update(tmp_path: Path) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_fold = writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)
    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER abort_pause_requeue_fold_event
        BEFORE INSERT ON experiment_status_event
        WHEN NEW.subject_type='fold'
          AND NEW.reason_code='pause_recovery_requeue'
        BEGIN
            SELECT RAISE(ABORT, 'injected pause requeue event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.requeue_fold_for_pause(
            key,
            expected_fold_revision=running_fold.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            detail={"must_rollback": True},
        )

    assert exc_info.value.details["reason_code"] == "invalid_pause_requeue"
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events
    assert not connection.in_transaction


def test_pause_requeue_reclaim_resume_dispatches_checkpoint_successor(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    old_lease, parent_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 10,
    )
    running_experiment = reader.get_experiment_projection(key.experiment_id)
    pause_requested = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    checkpointed = writer.transition_attempt(
        parent_spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=CheckpointRef("checkpoint-1"),
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=old_lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="checkpoint_saved",
        detail={},
    )
    terminal_attempt = writer.transition_attempt(
        parent_spec.attempt_id,
        target_status=ExperimentStatus.CANCELLED,
        backtest_run_id=checkpointed.backtest_run_id,
        checkpoint_ref=checkpointed.checkpoint_ref,
        failure_code=None,
        expected_revision=checkpointed.revision,
        lease_fence=old_lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="pause_attempt_drained",
        detail={},
    )
    old_claimed_fold = reader.get_fold(key).projection

    new_lease = writer.try_claim_lease(
        key.experiment_id,
        "owner-b",
        expected_revision=old_lease.revision,
        now_epoch_us=NOW_US + 10,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert new_lease is not None
    assert reader.get_fold(key).projection == old_claimed_fold
    assert old_claimed_fold.claim_owner_token == old_lease.owner_token

    requeued_fold = writer.requeue_fold_for_pause(
        key,
        expected_fold_revision=old_claimed_fold.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 11,
        occurred_at=NOW,
        detail={"reclaimed_from": old_lease.owner_token},
    )
    paused = writer.transition_scheduled_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSED,
        target_stage=pause_requested.record.stage,
        failure_code=None,
        expected_revision=pause_requested.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 12,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="pause_drained",
        detail={},
    )
    resumed = writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.QUEUED,
        target_desired_state=ExperimentDesiredState.RUN,
        target_stage=paused.record.stage,
        failure_code=None,
        expected_revision=paused.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_resume",
        detail={},
    )
    rerunning = writer.transition_scheduled_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=resumed.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 13,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="resume_dispatch",
        detail={},
    )
    successor_spec, successor_initial = _attempt(
        api,
        key,
        "attempt-2",
        ordinal=2,
        parent_attempt_id=parent_spec.attempt_id,
        resume_from_run_id=checkpointed.backtest_run_id,
    )
    successor_fold, successor = writer.claim_fold_and_add_attempt(
        key,
        successor_spec,
        successor_initial,
        expected_fold_revision=requeued_fold.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 14,
        occurred_at=NOW,
    )

    assert terminal_attempt.status is ExperimentStatus.CANCELLED
    assert terminal_attempt.checkpoint_ref == CheckpointRef("checkpoint-1")
    assert requeued_fold.status is ExperimentStatus.QUEUED
    assert requeued_fold.claim_owner_token is None
    assert paused.record.status is ExperimentStatus.PAUSED
    assert rerunning.record.status is ExperimentStatus.RUNNING
    assert successor_fold.status is ExperimentStatus.RUNNING
    assert successor_fold.claim_owner_token == new_lease.owner_token
    assert successor == successor_initial
    assert reader.get_attempt(successor_spec.attempt_id).spec == successor_spec
    assert reader.get_scheduler_slot().owner_token == new_lease.owner_token
    assert "pause_recovery_requeue" in {
        event.reason_code for event in reader.list_status_events(key.experiment_id)
    }


def test_operator_resume_is_paused_to_queued_run_and_preserves_queue_identity(
    tmp_path: Path,
) -> None:
    _database, reader, writer, _api_ns = _store(tmp_path)
    lease, running = _start_running_experiment(writer)
    pause_requested = writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    paused = writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.PAUSED,
        target_stage=pause_requested.record.stage,
        failure_code=None,
        expected_revision=pause_requested.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="pause_drained",
        detail={},
    )

    resumed = writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.QUEUED,
        target_desired_state=ExperimentDesiredState.RUN,
        target_stage=paused.record.stage,
        failure_code=None,
        expected_revision=paused.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_resume",
        detail={},
    )

    assert resumed.record.status is ExperimentStatus.QUEUED
    assert resumed.record.desired_state is ExperimentDesiredState.RUN
    assert resumed.record.stage is ExperimentStage.EXPLORATION
    assert resumed.queue_ordinal == 1
    assert reader.list_status_events(ExperimentId("experiment-1"))[
        -1
    ].desired_state is (ExperimentDesiredState.RUN)


def test_scheduler_cannot_execute_operator_owned_paused_to_queued_resume(
    tmp_path: Path,
) -> None:
    _database, reader, writer, _api_ns = _store(tmp_path)
    lease, running = _start_running_experiment(writer)
    pause_requested = writer.transition_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    paused = writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.PAUSED,
        target_stage=pause_requested.record.stage,
        failure_code=None,
        expected_revision=pause_requested.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="pause_drained",
        detail={},
    )
    before_events = reader.list_status_events(ExperimentId("experiment-1"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.QUEUED,
            target_stage=paused.record.stage,
            failure_code=None,
            expected_revision=paused.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="scheduler_resume_bypass",
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "operator_transition_requires_operator_command"
    )
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == paused
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events


def test_enqueue_rejects_draft_with_non_run_intent_without_queue_allocation(
    tmp_path: Path,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET desired_state='pause', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_projection = reader.get_experiment_projection(ExperimentId("experiment-1"))
    before_events = reader.list_status_events(ExperimentId("experiment-1"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.enqueue_experiment(
            ExperimentId("experiment-1"),
            expected_revision=1,
            occurred_at=NOW,
            reason_code="preflight_passed",
            detail={},
            launch_fence=_current_enqueue_fence(writer),
        )

    assert exc_info.value.details["reason_code"] == "experiment_desired_state_mismatch"
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == (
        before_projection
    )
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events


def test_scheduler_dispatch_rejects_queued_projection_with_non_run_intent(
    tmp_path: Path,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET desired_state='pause', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_projection = reader.get_experiment_projection(ExperimentId("experiment-1"))
    before_events = reader.list_status_events(ExperimentId("experiment-1"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_scheduled_experiment(
            ExperimentId("experiment-1"),
            target_status=ExperimentStatus.RUNNING,
            target_stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            expected_revision=queued.revision + 1,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 1,
            occurred_at=NOW,
            attempt_started=False,
            precondition_repairable=False,
            reason_code="dispatch",
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "experiment_desired_state_mismatch"
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == (
        before_projection
    )
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events


def test_stage_advance_rejects_running_projection_with_non_run_intent(
    tmp_path: Path,
) -> None:
    database, reader, writer, _api_ns = _store(tmp_path)
    lease, running = _start_running_experiment(writer)
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET desired_state='pause', revision=revision + 1
        WHERE experiment_id='experiment-1'
        """
    )
    connection.commit()
    before_projection = reader.get_experiment_projection(ExperimentId("experiment-1"))
    before_events = reader.list_status_events(ExperimentId("experiment-1"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.advance_experiment_stage(
            ExperimentId("experiment-1"),
            target_stage=ExperimentStage.WALK_FORWARD,
            expected_revision=running.revision + 1,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
            reason_code="exploration_complete",
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "experiment_desired_state_mismatch"
    assert reader.get_experiment_projection(ExperimentId("experiment-1")) == (
        before_projection
    )
    assert reader.list_status_events(ExperimentId("experiment-1")) == before_events


def test_running_experiment_stage_advances_are_fenced_ordered_and_evented(
    tmp_path: Path,
) -> None:
    _database, reader, writer, _api_ns = _store(tmp_path)
    queued = writer.enqueue_experiment(
        ExperimentId("experiment-1"),
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=_current_enqueue_fence(writer),
    )
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    running = writer.transition_scheduled_experiment(
        ExperimentId("experiment-1"),
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=queued.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="dispatch",
        detail={},
    )
    walk_forward = writer.advance_experiment_stage(
        ExperimentId("experiment-1"),
        target_stage=ExperimentStage.WALK_FORWARD,
        expected_revision=running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        reason_code="exploration_complete",
        detail={},
    )
    assert walk_forward.record.status is ExperimentStatus.RUNNING
    assert walk_forward.record.stage is ExperimentStage.WALK_FORWARD

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.advance_experiment_stage(
            ExperimentId("experiment-1"),
            target_stage=ExperimentStage.HOLDOUT,
            expected_revision=walk_forward.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            reason_code="skip_candidate_selection",
            detail={},
        )
    assert (
        exc_info.value.details["reason_code"] == "invalid_experiment_stage_transition"
    )
    assert (
        reader.get_experiment_projection(ExperimentId("experiment-1")) == walk_forward
    )
    assert reader.list_status_events(ExperimentId("experiment-1"))[-1].stage is (
        ExperimentStage.WALK_FORWARD
    )


def test_downstream_fold_and_attempt_cas_require_current_unexpired_fence(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running_experiment = _start_running_experiment(writer)
    claimed = writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    assert claimed.status is ExperimentStatus.RUNNING
    assert claimed.claim_owner_token == "owner-a"

    attempt_spec, attempt_projection = _attempt(api, key)
    writer.add_attempt(
        attempt_spec,
        attempt_projection,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
    )
    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 3,
        new_lease_until_epoch_us=NOW_US + 200,
    )

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.transition_attempt(
            AttemptId("attempt-1"),
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=BacktestRunId("backtest-run-1"),
            checkpoint_ref=None,
            failure_code=None,
            expected_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
            occurred_at=NOW,
            reason_code="started",
            detail={},
        )
    assert reader.get_attempt(AttemptId("attempt-1")).projection.revision == 0

    running = writer.transition_attempt(
        AttemptId("attempt-1"),
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-1"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=renewed.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="started",
        detail={},
    )
    assert running.revision == 1


@pytest.mark.parametrize(
    ("experiment_status", "desired_state"),
    [
        (ExperimentStatus.PAUSE_REQUESTED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.PAUSED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.CANCEL_REQUESTED, ExperimentDesiredState.CANCEL),
        (ExperimentStatus.COMPLETED, ExperimentDesiredState.RUN),
        (ExperimentStatus.RUNNING, ExperimentDesiredState.PAUSE),
    ],
)
def test_claim_fold_rejects_non_dispatchable_experiment_without_writes(
    tmp_path: Path,
    experiment_status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running = _start_running_experiment(writer)
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status=?, desired_state=?, revision=revision + 1
        WHERE experiment_id=?
        """,
        (experiment_status.value, desired_state.value, str(key.experiment_id)),
    )
    connection.commit()
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.claim_fold(
            key,
            expected_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "experiment_not_dispatchable"
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes


@pytest.mark.parametrize(
    ("experiment_status", "desired_state"),
    [
        (ExperimentStatus.PAUSE_REQUESTED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.PAUSED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.CANCEL_REQUESTED, ExperimentDesiredState.CANCEL),
        (ExperimentStatus.COMPLETED, ExperimentDesiredState.RUN),
        (ExperimentStatus.RUNNING, ExperimentDesiredState.PAUSE),
    ],
)
def test_atomic_dispatch_rejects_non_dispatchable_experiment_without_writes(
    tmp_path: Path,
    experiment_status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    attempt_spec, attempt_projection = _attempt(api, key)
    lease, _running = _start_running_experiment(writer)
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE experiment SET status=?, desired_state=?, revision=revision + 1
        WHERE experiment_id=?
        """,
        (experiment_status.value, desired_state.value, str(key.experiment_id)),
    )
    connection.commit()
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.claim_fold_and_add_attempt(
            key,
            attempt_spec,
            attempt_projection,
            expected_fold_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "experiment_not_dispatchable"
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id) is None
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes


def test_operator_pause_commit_blocks_atomic_dispatch_with_the_existing_fence(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    attempt_spec, attempt_projection = _attempt(api, key)
    lease, running = _start_running_experiment(writer)
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    connection = database.get_connection()
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.claim_fold_and_add_attempt(
            key,
            attempt_spec,
            attempt_projection,
            expected_fold_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "experiment_not_dispatchable"
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id) is None
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes


def test_operator_pause_blocks_new_attempt_insert_on_an_owned_fold(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, running = _start_running_experiment(writer)
    writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    attempt_spec, attempt_projection = _attempt(api, key)
    connection = database.get_connection()
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.add_attempt(
            attempt_spec,
            attempt_projection,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
        )

    assert exc_info.value.details["reason_code"] == "experiment_not_dispatchable"
    assert reader.get_fold(key) == before_fold
    assert reader.get_attempt(attempt_spec.attempt_id) is None
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes


def test_operator_pause_blocks_queued_attempt_from_starting(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    attempt_spec, attempt_projection = _attempt(api, key)
    lease, running = _start_running_experiment(writer)
    writer.claim_fold_and_add_attempt(
        key,
        attempt_spec,
        attempt_projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    writer.transition_experiment(
        key.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=running.record.stage,
        failure_code=None,
        expected_revision=running.revision,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    connection = database.get_connection()
    before_attempt = reader.get_attempt(attempt_spec.attempt_id)
    before_events = reader.list_status_events(key.experiment_id)
    before_changes = connection.total_changes

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_attempt(
            attempt_spec.attempt_id,
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=BacktestRunId("backtest-run-1"),
            checkpoint_ref=None,
            failure_code=None,
            expected_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            reason_code="attempt_started",
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "experiment_not_dispatchable"
    assert reader.get_attempt(attempt_spec.attempt_id) == before_attempt
    assert reader.list_status_events(key.experiment_id) == before_events
    assert connection.total_changes == before_changes


@pytest.mark.parametrize(
    ("requested_status", "requested_desired_state"),
    [
        (ExperimentStatus.PAUSE_REQUESTED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.CANCEL_REQUESTED, ExperimentDesiredState.CANCEL),
    ],
)
def test_running_attempt_can_checkpoint_and_finish_after_control_request(
    tmp_path: Path,
    requested_status: ExperimentStatus,
    requested_desired_state: ExperimentDesiredState,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, attempt_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_experiment = reader.get_experiment_projection(key.experiment_id)
    assert running_experiment is not None
    writer.transition_experiment(
        key.experiment_id,
        target_status=requested_status,
        target_desired_state=requested_desired_state,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_control_requested",
        detail={},
    )

    checkpoint_ref = CheckpointRef("checkpoint-1")
    checkpointed = writer.transition_attempt(
        attempt_spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=checkpoint_ref,
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="checkpoint_saved",
        detail={},
    )
    terminal = writer.transition_attempt(
        attempt_spec.attempt_id,
        target_status=ExperimentStatus.CANCELLED,
        backtest_run_id=checkpointed.backtest_run_id,
        checkpoint_ref=checkpointed.checkpoint_ref,
        failure_code=None,
        expected_revision=checkpointed.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="control_request_drained",
        detail={},
    )

    assert checkpointed.status is ExperimentStatus.RUNNING
    assert checkpointed.checkpoint_ref == checkpoint_ref
    assert terminal.status is ExperimentStatus.CANCELLED
    assert terminal.checkpoint_ref == checkpoint_ref


def test_add_attempt_rejects_a_stale_fence_before_inserting_any_rows(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running_experiment = _start_running_experiment(writer)
    writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 3,
        new_lease_until_epoch_us=NOW_US + 200,
    )
    spec, projection = _attempt(api, key)

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.add_attempt(
            spec,
            projection,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
        )
    assert reader.get_attempt(AttemptId("attempt-1")) is None

    writer.add_attempt(
        spec,
        projection,
        lease_fence=renewed.fence,
        now_epoch_us=NOW_US + 4,
    )
    assert reader.get_attempt(AttemptId("attempt-1")) is not None


def test_claim_fold_and_add_attempt_is_one_atomic_dispatch_transaction(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    second_key = api.FoldKey(
        ExperimentId("experiment-1"), CandidateId("candidate-1"), FoldId("fold-2")
    )
    second_fold = api.FoldPersistenceSpec.create(
        second_key,
        2,
        api.FoldRole.WALK_FORWARD,
        api.DateWindow(date(2024, 1, 2), date(2025, 12, 31)),
        api.DateWindow(date(2026, 4, 1), date(2026, 6, 30)),
        2,
        1,
    )
    writer.add_fold(
        second_fold,
        api.FoldProjection(second_key, ExperimentStatus.QUEUED, None, NOW, NOW, 0),
    )
    lease, _running_experiment = _start_running_experiment(writer)
    spec, projection = _attempt(api, key)

    fold_projection, attempt_projection = writer.claim_fold_and_add_attempt(
        key,
        spec,
        projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )

    assert fold_projection.status is ExperimentStatus.RUNNING
    assert attempt_projection == projection
    assert reader.get_fold(key).projection.revision == 1
    assert reader.get_attempt(AttemptId("attempt-1")).projection == projection
    events = reader.list_status_events(ExperimentId("experiment-1"))
    assert [(event.subject_type.value, event.subject_revision) for event in events] == [
        ("experiment", 0),
        ("experiment", 1),
        ("experiment", 2),
        ("fold", 0),
        ("fold", 1),
        ("fold", 0),
        ("attempt", 0),
    ]

    database.get_connection().execute(
        """
        CREATE TRIGGER abort_attempt_dispatch
        BEFORE INSERT ON experiment_attempt
        BEGIN
            SELECT RAISE(ABORT, 'injected attempt dispatch failure');
        END
        """
    )
    database.get_connection().commit()
    second_spec, second_projection = _attempt(api, second_key, "attempt-2")

    with pytest.raises(api.ExperimentPersistenceError):
        writer.claim_fold_and_add_attempt(
            second_key,
            second_spec,
            second_projection,
            expected_fold_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
        )

    assert reader.get_fold(second_key).projection.status is ExperimentStatus.QUEUED
    assert reader.get_fold(second_key).projection.revision == 0
    assert reader.get_attempt(AttemptId("attempt-2")) is None


def test_atomic_successor_dispatch_rejects_missing_parent_without_mutating_fold(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running_experiment = _start_running_experiment(writer)
    retry = api.AttemptPersistenceSpec(
        AttemptId("attempt-retry"),
        key,
        2,
        AttemptId("attempt-parent"),
        BacktestRunId("resume-run"),
        ContentHash("d" * 64),
        NOW,
    )
    projection = api.AttemptProjection(
        AttemptId("attempt-retry"),
        ExperimentStatus.QUEUED,
        None,
        None,
        None,
        NOW,
        NOW,
        0,
    )

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.claim_fold_and_add_attempt(
            key,
            retry,
            projection,
            expected_fold_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 2,
            occurred_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "invalid_retry_parent_lineage"
    assert reader.get_fold(key).projection.status is ExperimentStatus.QUEUED
    assert reader.get_attempt(AttemptId("attempt-retry")) is None


def test_reclaimed_owner_recovers_interrupted_work_and_dispatches_successor(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    old_lease, parent_spec, running_attempt = _start_running_attempt(writer, api, key)
    new_lease = writer.try_claim_lease(
        key.experiment_id,
        "owner-b",
        expected_revision=old_lease.revision,
        now_epoch_us=NOW_US + 10,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert new_lease is not None

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.requeue_interrupted_fold(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=1,
            expected_attempt_revision=running_attempt.revision,
            lease_fence=old_lease.fence,
            now_epoch_us=NOW_US + 11,
            occurred_at=NOW,
            detail={"reclaimed_by": "owner-b"},
        )
    assert reader.get_fold(key).projection.status is ExperimentStatus.RUNNING
    assert reader.get_attempt(parent_spec.attempt_id).projection == running_attempt

    recovered_fold, interrupted_attempt = writer.requeue_interrupted_fold(
        key,
        parent_spec.attempt_id,
        expected_fold_revision=1,
        expected_attempt_revision=running_attempt.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 11,
        occurred_at=NOW,
        detail={"reclaimed_by": "owner-b"},
    )
    assert recovered_fold.status is ExperimentStatus.QUEUED
    assert recovered_fold.claim_owner_token is None
    assert interrupted_attempt.status is ExperimentStatus.FAILED
    assert interrupted_attempt.failure_code is ExperimentFailureCode.LEASE_LOST
    assert (
        database.get_connection()
        .execute(
            """
            SELECT count(*) FROM experiment_attempt
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
              AND status IN ('queued', 'running')
            """,
            (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
        )
        .fetchone()[0]
        == 0
    )

    successor_spec, successor_initial = _attempt(
        api,
        key,
        "attempt-2",
        ordinal=2,
        parent_attempt_id=parent_spec.attempt_id,
        resume_from_run_id=running_attempt.backtest_run_id,
    )
    claimed_fold, successor = writer.claim_fold_and_add_attempt(
        key,
        successor_spec,
        successor_initial,
        expected_fold_revision=recovered_fold.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 12,
        occurred_at=NOW,
    )

    assert claimed_fold.status is ExperimentStatus.RUNNING
    assert successor == successor_initial
    assert reader.get_attempt(parent_spec.attempt_id).projection == interrupted_attempt
    assert reader.get_attempt(successor_spec.attempt_id).spec == successor_spec
    assert (
        database.get_connection()
        .execute(
            """
            SELECT count(*) FROM experiment_attempt
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
              AND status IN ('queued', 'running')
            """,
            (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
        )
        .fetchone()[0]
        == 1
    )
    reasons = {
        event.reason_code for event in reader.list_status_events(key.experiment_id)
    }
    assert {"crash_recovery_interrupted", "crash_recovery_requeue"} <= reasons


def test_crash_recovery_attempt_and_fold_events_rollback_together(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    old_lease, parent_spec, running_attempt = _start_running_attempt(writer, api, key)
    new_lease = writer.try_claim_lease(
        key.experiment_id,
        "owner-b",
        expected_revision=old_lease.revision,
        now_epoch_us=NOW_US + 10,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert new_lease is not None
    connection = database.get_connection()
    connection.execute(
        """
        CREATE TRIGGER abort_crash_recovery_fold_event
        BEFORE INSERT ON experiment_status_event
        WHEN NEW.subject_type='fold' AND NEW.reason_code='crash_recovery_requeue'
        BEGIN
            SELECT RAISE(ABORT, 'injected recovery event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(api.ExperimentPersistenceError):
        writer.requeue_interrupted_fold(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=1,
            expected_attempt_revision=running_attempt.revision,
            lease_fence=new_lease.fence,
            now_epoch_us=NOW_US + 11,
            occurred_at=NOW,
            detail={},
        )

    assert reader.get_fold(key).projection.status is ExperimentStatus.RUNNING
    assert reader.get_fold(key).projection.revision == 1
    assert reader.get_attempt(parent_spec.attempt_id).projection == running_attempt
    assert all(
        event.reason_code
        not in {"crash_recovery_interrupted", "crash_recovery_requeue"}
        for event in reader.list_status_events(key.experiment_id)
    )


def test_current_owner_cannot_misclassify_its_live_attempt_as_crash_orphan(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_fold = reader.get_fold(key).projection
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_interrupted_fold(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=running_fold.revision,
            expected_attempt_revision=running_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "crash_recovery_requires_reclaimed_owner"
    )
    assert reader.get_fold(key).projection == running_fold
    assert reader.get_attempt(parent_spec.attempt_id).projection == running_attempt
    assert reader.list_status_events(key.experiment_id) == before_events


@pytest.mark.parametrize(
    ("drift", "reason_code"),
    [
        ("parent", "invalid_retry_parent_lineage"),
        ("fingerprint", "retry_fingerprint_drift"),
        ("resume", "retry_resume_source_mismatch"),
    ],
)
def test_atomic_successor_dispatch_validates_parent_before_fold_claim(
    tmp_path: Path,
    drift: str,
    reason_code: str,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    old_lease, parent_spec, running_attempt = _start_running_attempt(writer, api, key)
    new_lease = writer.try_claim_lease(
        key.experiment_id,
        "owner-b",
        expected_revision=old_lease.revision,
        now_epoch_us=NOW_US + 10,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert new_lease is not None
    recovered_fold, _interrupted = writer.requeue_interrupted_fold(
        key,
        parent_spec.attempt_id,
        expected_fold_revision=1,
        expected_attempt_revision=running_attempt.revision,
        lease_fence=new_lease.fence,
        now_epoch_us=NOW_US + 11,
        occurred_at=NOW,
        detail={},
    )
    successor_spec, successor_initial = _attempt(
        api,
        key,
        "attempt-2",
        ordinal=2,
        parent_attempt_id=(
            AttemptId("missing-parent") if drift == "parent" else parent_spec.attempt_id
        ),
        resume_from_run_id=(
            BacktestRunId("wrong-run")
            if drift == "resume"
            else running_attempt.backtest_run_id
        ),
        fingerprint=(
            ContentHash("e" * 64)
            if drift == "fingerprint"
            else parent_spec.reproduction_fingerprint
        ),
    )

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.claim_fold_and_add_attempt(
            key,
            successor_spec,
            successor_initial,
            expected_fold_revision=recovered_fold.revision,
            lease_fence=new_lease.fence,
            now_epoch_us=NOW_US + 12,
            occurred_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == reason_code
    assert reader.get_fold(key).projection == recovered_fold
    assert reader.get_attempt(successor_spec.attempt_id) is None


def test_expired_fence_cannot_claim_or_write_work(tmp_path: Path) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running_experiment = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 10,
    )

    with pytest.raises(api.ExperimentLeaseLostError) as exc_info:
        writer.claim_fold(
            key,
            expected_revision=0,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 10,
            occurred_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "scheduler_lease_expired"
    assert reader.get_fold(key).projection.status is ExperimentStatus.QUEUED


@pytest.mark.parametrize("reason_code", ["pause_recovery", "crash_recovery"])
def test_generic_fold_transition_cannot_requeue_running_fold_with_live_attempt(
    tmp_path: Path,
    reason_code: str,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, attempt_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    running_fold = reader.get_fold(key).projection
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.transition_fold(
            key,
            target_status=ExperimentStatus.QUEUED,
            claim_owner_token=None,
            failure_code=None,
            expected_revision=running_fold.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
            occurred_at=NOW,
            reason_code=reason_code,
            detail={},
        )
    assert (
        exc_info.value.details["reason_code"]
        == "recovery_transition_requires_atomic_api"
    )
    assert reader.get_fold(key).projection == running_fold
    assert reader.get_attempt(attempt_spec.attempt_id).projection == running_attempt
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_work_items_cannot_transition_back_to_live_states(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running_experiment = _start_running_experiment(writer)
    spec, projection = _attempt(api, key)
    writer.claim_fold_and_add_attempt(
        key,
        spec,
        projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    running = writer.transition_attempt(
        AttemptId("attempt-1"),
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-1"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="started",
        detail={},
    )
    completed = writer.transition_attempt(
        AttemptId("attempt-1"),
        target_status=ExperimentStatus.COMPLETED,
        backtest_run_id=BacktestRunId("backtest-run-1"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="completed",
        detail={},
    )

    with pytest.raises(ExperimentSpecError) as attempt_exc:
        writer.transition_attempt(
            AttemptId("attempt-1"),
            target_status=ExperimentStatus.RUNNING,
            backtest_run_id=BacktestRunId("backtest-run-1"),
            checkpoint_ref=None,
            failure_code=None,
            expected_revision=completed.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 5,
            occurred_at=NOW,
            reason_code="illegal_restart",
            detail={},
        )
    assert attempt_exc.value.details["reason_code"] == "invalid_attempt_transition"
    assert reader.get_attempt(AttemptId("attempt-1")).projection == completed

    terminal_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.COMPLETED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="completed",
        detail={},
    )
    with pytest.raises(ExperimentSpecError) as fold_exc:
        writer.transition_fold(
            key,
            target_status=ExperimentStatus.RUNNING,
            claim_owner_token=lease.owner_token,
            failure_code=None,
            expected_revision=terminal_fold.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 6,
            occurred_at=NOW,
            reason_code="illegal_restart",
            detail={},
        )
    assert fold_exc.value.details["reason_code"] == "invalid_fold_transition"
    assert reader.get_fold(key).projection == terminal_fold


def _failed_fold_for_terminal_retry(
    writer: Any,
    reader: Any,
    api: SimpleNamespace,
    key: Any,
    *,
    failure_code: ExperimentFailureCode = ExperimentFailureCode.SYSTEM_ERROR,
) -> tuple[Any, Any, Any, Any]:
    lease, parent_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    failed_attempt = writer.transition_attempt(
        parent_spec.attempt_id,
        target_status=ExperimentStatus.FAILED,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=running_attempt.checkpoint_ref,
        failure_code=failure_code,
        expected_revision=running_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="attempt_failed",
        detail={},
    )
    running_fold_view = reader.get_fold(key)
    assert running_fold_view is not None
    failed_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.FAILED,
        claim_owner_token=None,
        failure_code=failure_code,
        expected_revision=running_fold_view.projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="fold_failed",
        detail={},
    )
    return lease, parent_spec, failed_attempt, failed_fold


@pytest.mark.parametrize(
    "failure_code",
    [ExperimentFailureCode.SYSTEM_ERROR, ExperimentFailureCode.LEASE_LOST],
)
def test_retryable_terminal_fold_requeues_atomically_and_appends_event(
    tmp_path: Path,
    failure_code: ExperimentFailureCode,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer,
        reader,
        api,
        key,
        failure_code=failure_code,
    )

    requeued = writer.requeue_failed_fold_for_retry(
        key,
        parent_spec.attempt_id,
        expected_fold_revision=failed_fold.revision,
        expected_parent_attempt_revision=failed_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
        detail={"failure_code": failure_code.value},
    )

    assert requeued.status is ExperimentStatus.QUEUED
    assert requeued.claim_owner_token is None
    assert requeued.revision == failed_fold.revision + 1
    fold_view = reader.get_fold(key)
    assert fold_view is not None
    assert fold_view.projection == requeued
    parent_view = reader.get_attempt(parent_spec.attempt_id)
    assert parent_view is not None
    assert parent_view.projection == failed_attempt
    assert len(reader.list_attempts(key)) == 1
    retry_events = [
        event
        for event in reader.list_status_events(key.experiment_id)
        if event.reason_code == "terminal_fold_retry"
    ]
    assert len(retry_events) == 1
    retry_event = retry_events[0]
    assert retry_event.previous_status is ExperimentStatus.FAILED
    assert retry_event.status is ExperimentStatus.QUEUED
    assert retry_event.failure_code is None
    assert retry_event.subject_revision == requeued.revision
    assert retry_event.detail == {"failure_code": failure_code.value}


def test_terminal_fold_retry_rejects_candidate_failure_without_writes(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer,
        reader,
        api,
        key,
        failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
    )
    before_fold = reader.get_fold(key)
    before_attempts = reader.list_attempts(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=failed_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 6,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "terminal_fold_retry_failure_not_retryable"
    )
    assert reader.get_fold(key) == before_fold
    assert reader.list_attempts(key) == before_attempts
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_fold_retry_rejects_cancelled_fold_without_writes(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    cancelled_attempt = writer.transition_attempt(
        parent_spec.attempt_id,
        target_status=ExperimentStatus.CANCELLED,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="attempt_cancelled",
        detail={},
    )
    running_fold_view = reader.get_fold(key)
    assert running_fold_view is not None
    cancelled_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.CANCELLED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=running_fold_view.projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="fold_cancelled",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=cancelled_fold.revision,
            expected_parent_attempt_revision=cancelled_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 6,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "terminal_fold_retry_requires_failed_fold"
    )
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events


@pytest.mark.parametrize(
    ("target_status", "target_desired_state"),
    [
        (ExperimentStatus.PAUSED, ExperimentDesiredState.PAUSE),
        (ExperimentStatus.CANCELLED, ExperimentDesiredState.CANCEL),
    ],
)
def test_terminal_fold_retry_rejects_inactive_parent_experiment_without_writes(
    tmp_path: Path,
    target_status: ExperimentStatus,
    target_desired_state: ExperimentDesiredState,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer, reader, api, key
    )
    running_experiment = reader.get_experiment_projection(key.experiment_id)
    assert running_experiment is not None
    requested_status = (
        ExperimentStatus.PAUSE_REQUESTED
        if target_status is ExperimentStatus.PAUSED
        else ExperimentStatus.CANCEL_REQUESTED
    )
    requested = writer.transition_experiment(
        key.experiment_id,
        target_status=requested_status,
        target_desired_state=target_desired_state,
        target_stage=running_experiment.record.stage,
        failure_code=None,
        expected_revision=running_experiment.revision,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="operator_control",
        detail={},
    )
    writer.transition_scheduled_experiment(
        key.experiment_id,
        target_status=target_status,
        target_stage=requested.record.stage,
        failure_code=None,
        expected_revision=requested.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="control_drained",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_attempts = reader.list_attempts(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=failed_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 7,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "terminal_fold_retry_experiment_not_running"
    )
    assert reader.get_fold(key) == before_fold
    assert reader.list_attempts(key) == before_attempts
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_fold_retry_rejects_cancelled_parent_attempt_without_writes(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, running_attempt = _start_running_attempt(
        writer,
        api,
        key,
        lease_until_epoch_us=NOW_US + 100,
    )
    cancelled_attempt = writer.transition_attempt(
        parent_spec.attempt_id,
        target_status=ExperimentStatus.CANCELLED,
        backtest_run_id=running_attempt.backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="attempt_cancelled",
        detail={},
    )
    running_fold_view = reader.get_fold(key)
    assert running_fold_view is not None
    failed_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.FAILED,
        claim_owner_token=None,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        expected_revision=running_fold_view.projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="fold_failed",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=cancelled_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 6,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "terminal_fold_retry_parent_not_retryable"
    )
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_fold_retry_rejects_wrong_parent_lineage_without_writes(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    other_key = _add_fold(
        writer,
        api,
        candidate_id="candidate-2",
        fold_id="fold-2",
        ordinal=1,
    )
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer, reader, api, key
    )
    wrong_spec, wrong_initial = _attempt(api, other_key, "attempt-other")
    writer.claim_fold_and_add_attempt(
        other_key,
        wrong_spec,
        wrong_initial,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
    )
    wrong_running = writer.transition_attempt(
        wrong_spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-other"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 7,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    wrong_failed = writer.transition_attempt(
        wrong_spec.attempt_id,
        target_status=ExperimentStatus.FAILED,
        backtest_run_id=wrong_running.backtest_run_id,
        checkpoint_ref=None,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        expected_revision=wrong_running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 8,
        occurred_at=NOW,
        reason_code="attempt_failed",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_attempts = reader.list_attempts(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            wrong_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=wrong_failed.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 9,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"]
        == "terminal_fold_retry_parent_lineage_invalid"
    )
    assert reader.get_fold(key) == before_fold
    assert reader.list_attempts(key) == before_attempts
    assert reader.list_status_events(key.experiment_id) == before_events
    assert reader.get_attempt(parent_spec.attempt_id).projection == failed_attempt


@pytest.mark.parametrize("stale_target", ["fold", "parent"])
def test_terminal_fold_retry_rejects_stale_revision_without_writes(
    tmp_path: Path,
    stale_target: str,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer, reader, api, key
    )
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(api.ExperimentConflictError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=(
                failed_fold.revision - 1
                if stale_target == "fold"
                else failed_fold.revision
            ),
            expected_parent_attempt_revision=(
                failed_attempt.revision - 1
                if stale_target == "parent"
                else failed_attempt.revision
            ),
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 6,
            occurred_at=NOW,
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "stale_projection_revision"
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events


@pytest.mark.parametrize(
    ("fence_case", "expected_reason"),
    [
        ("wrong_owner", "scheduler_lease_lost"),
        ("expired", "scheduler_lease_expired"),
    ],
)
def test_terminal_fold_retry_rejects_invalid_fence_without_writes(
    tmp_path: Path,
    fence_case: str,
    expected_reason: str,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer, reader, api, key
    )
    fence = lease.fence
    now_epoch_us = NOW_US + 6
    if fence_case == "wrong_owner":
        fence = type(lease.fence)(
            experiment_id=lease.fence.experiment_id,
            owner_token="owner-b",
            revision=lease.fence.revision,
            lease_until_epoch_us=lease.fence.lease_until_epoch_us,
        )
    else:
        now_epoch_us = lease.fence.lease_until_epoch_us
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(api.ExperimentLeaseLostError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=failed_attempt.revision,
            lease_fence=fence,
            now_epoch_us=now_epoch_us,
            occurred_at=NOW,
            detail={},
        )

    assert exc_info.value.details["reason_code"] == expected_reason
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_fold_retry_rejects_live_attempt_without_writes(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, _running_experiment = _start_running_experiment(
        writer,
        lease_until_epoch_us=NOW_US + 100,
    )
    parent_spec, initial = _attempt(api, key)
    running_fold, queued_attempt = writer.claim_fold_and_add_attempt(
        key,
        parent_spec,
        initial,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    failed_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.FAILED,
        claim_owner_token=None,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        expected_revision=running_fold.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="fold_failed",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_attempts = reader.list_attempts(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=queued_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 4,
            occurred_at=NOW,
            detail={},
        )

    assert exc_info.value.details["reason_code"] == "terminal_fold_retry_live_attempt"
    assert reader.get_fold(key) == before_fold
    assert reader.list_attempts(key) == before_attempts
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_fold_retry_rejects_non_latest_parent_without_writes(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, first_spec, first_failed, first_fold = _failed_fold_for_terminal_retry(
        writer,
        reader,
        api,
        key,
    )
    requeued = writer.requeue_failed_fold_for_retry(
        key,
        first_spec.attempt_id,
        expected_fold_revision=first_fold.revision,
        expected_parent_attempt_revision=first_failed.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
        detail={},
    )
    second_spec, second_initial = _attempt(
        api,
        key,
        "attempt-2",
        ordinal=2,
        parent_attempt_id=first_spec.attempt_id,
        resume_from_run_id=first_failed.backtest_run_id,
        fingerprint=first_spec.reproduction_fingerprint,
    )
    second_running_fold, _second_queued = writer.claim_fold_and_add_attempt(
        key,
        second_spec,
        second_initial,
        expected_fold_revision=requeued.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 7,
        occurred_at=NOW,
    )
    second_running = writer.transition_attempt(
        second_spec.attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId("backtest-run-2"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 8,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    writer.transition_attempt(
        second_spec.attempt_id,
        target_status=ExperimentStatus.FAILED,
        backtest_run_id=second_running.backtest_run_id,
        checkpoint_ref=None,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        expected_revision=second_running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 9,
        occurred_at=NOW,
        reason_code="attempt_failed",
        detail={},
    )
    second_failed_fold = writer.transition_fold(
        key,
        target_status=ExperimentStatus.FAILED,
        claim_owner_token=None,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        expected_revision=second_running_fold.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 10,
        occurred_at=NOW,
        reason_code="fold_failed",
        detail={},
    )
    before_fold = reader.get_fold(key)
    before_attempts = reader.list_attempts(key)
    before_events = reader.list_status_events(key.experiment_id)

    with pytest.raises(ExperimentSpecError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            first_spec.attempt_id,
            expected_fold_revision=second_failed_fold.revision,
            expected_parent_attempt_revision=first_failed.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 11,
            occurred_at=NOW,
            detail={},
        )

    assert (
        exc_info.value.details["reason_code"] == "terminal_fold_retry_parent_not_latest"
    )
    assert reader.get_fold(key) == before_fold
    assert reader.list_attempts(key) == before_attempts
    assert reader.list_status_events(key.experiment_id) == before_events


def test_terminal_fold_retry_event_failure_rolls_back_fold_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3

    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease, parent_spec, failed_attempt, failed_fold = _failed_fold_for_terminal_retry(
        writer, reader, api, key
    )
    before_fold = reader.get_fold(key)
    before_events = reader.list_status_events(key.experiment_id)

    def fail_event_insert(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.IntegrityError("injected terminal retry event failure")

    monkeypatch.setattr(writer, "_insert_event", fail_event_insert)

    with pytest.raises(api.ExperimentIntegrityError) as exc_info:
        writer.requeue_failed_fold_for_retry(
            key,
            parent_spec.attempt_id,
            expected_fold_revision=failed_fold.revision,
            expected_parent_attempt_revision=failed_attempt.revision,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 6,
            occurred_at=NOW,
            detail={"must_rollback": True},
        )

    assert exc_info.value.details["reason_code"] == "invalid_terminal_fold_retry"
    assert reader.get_fold(key) == before_fold
    assert reader.list_status_events(key.experiment_id) == before_events
