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
    CandidateId,
    CandidateSpec,
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
    SnapshotId,
    StrategyVersion,
)

NOW = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)
NOW_US = 1_768_000_000_000_000


def _api() -> SimpleNamespace:
    from ditto_analysis.errors import (
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
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=(
            CandidateSpec(CandidateId("candidate-1"), 1, True, {"x": 1}),
            CandidateSpec(CandidateId("candidate-2"), 2, False, {"x": 2}),
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


def _start_running_attempt(
    writer: Any,
    api: SimpleNamespace,
    key: Any,
    *,
    owner: str = "owner-a",
    lease_until_epoch_us: int = NOW_US + 10,
) -> tuple[Any, Any, Any]:
    lease = writer.try_claim_lease(
        key.experiment_id,
        owner,
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=lease_until_epoch_us,
    )
    assert lease is not None
    spec, projection = _attempt(api, key)
    writer.claim_fold_and_add_attempt(
        key,
        spec,
        projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
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
        now_epoch_us=NOW_US + 2,
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
    first = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert first is not None
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


def test_stale_claim_revision_is_not_reported_as_ordinary_contention(
    tmp_path: Path,
) -> None:
    _database, _reader, writer, api = _store(tmp_path)
    first = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert first is not None

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

    released = writer.release_lease(renewed.fence, now_epoch_us=NOW_US + 12)
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
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    claimed = writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )
    assert claimed.status is ExperimentStatus.RUNNING
    assert claimed.claim_owner_token == "owner-a"

    attempt_spec, attempt_projection = _attempt(api, key)
    writer.add_attempt(
        attempt_spec,
        attempt_projection,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
    )
    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 2,
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
            now_epoch_us=NOW_US + 3,
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
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="started",
        detail={},
    )
    assert running.revision == 1


def test_add_attempt_rejects_a_stale_fence_before_inserting_any_rows(
    tmp_path: Path,
) -> None:
    _database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    writer.claim_fold(
        key,
        expected_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )
    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 2,
        new_lease_until_epoch_us=NOW_US + 200,
    )
    spec, projection = _attempt(api, key)

    with pytest.raises(api.ExperimentLeaseLostError):
        writer.add_attempt(
            spec,
            projection,
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 3,
        )
    assert reader.get_attempt(AttemptId("attempt-1")) is None

    writer.add_attempt(
        spec,
        projection,
        lease_fence=renewed.fence,
        now_epoch_us=NOW_US + 3,
    )
    assert reader.get_attempt(AttemptId("attempt-1")) is not None


def test_claim_fold_and_add_attempt_is_one_atomic_dispatch_transaction(
    tmp_path: Path,
) -> None:
    database, reader, writer, api = _store(tmp_path)
    key = _add_fold(writer, api)
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    spec, projection = _attempt(api, key)

    fold_projection, attempt_projection = writer.claim_fold_and_add_attempt(
        key,
        spec,
        projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
    )

    assert fold_projection.status is ExperimentStatus.RUNNING
    assert attempt_projection == projection
    assert reader.get_fold(key).projection.revision == 1
    assert reader.get_attempt(AttemptId("attempt-1")).projection == projection
    events = reader.list_status_events(ExperimentId("experiment-1"))
    assert [(event.subject_type.value, event.subject_revision) for event in events] == [
        ("experiment", 0),
        ("fold", 0),
        ("fold", 1),
        ("attempt", 0),
    ]

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
            now_epoch_us=NOW_US + 2,
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
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
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
            now_epoch_us=NOW_US + 1,
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
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 10,
    )
    assert lease is not None

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
    lease = writer.try_claim_lease(
        ExperimentId("experiment-1"),
        "owner-a",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 100,
    )
    assert lease is not None
    spec, projection = _attempt(api, key)
    writer.claim_fold_and_add_attempt(
        key,
        spec,
        projection,
        expected_fold_revision=0,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
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
        now_epoch_us=NOW_US + 2,
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
        now_epoch_us=NOW_US + 3,
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
            now_epoch_us=NOW_US + 4,
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
        now_epoch_us=NOW_US + 4,
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
            now_epoch_us=NOW_US + 5,
            occurred_at=NOW,
            reason_code="illegal_restart",
            detail={},
        )
    assert fold_exc.value.details["reason_code"] == "invalid_fold_transition"
    assert reader.get_fold(key).projection == terminal_fold
