"""Task 22 acceptance for bounded, durable R3 scheduler capacity and recovery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from ditto_analysis.errors import ExperimentLeaseLostError
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    CheckpointRef,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
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
    LogicalTrialIdentity,
    ResearchCycleIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    SchedulerLease,
    SnapshotId,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
    canonical_payload,
)
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    build_successor_queued_attempt,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.planning import (
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ParameterAxis,
)
from ditto_application.processes.experiments.planning_contracts import (
    declare_trial_family,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
    ExperimentPreflightStatus,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
)
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)

NOW = datetime(2026, 7, 28, 2, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)
pytestmark = [pytest.mark.integration, pytest.mark.e2e]


class _AttemptLineageFactory:
    """
    Narrow scheduler fixture for deterministic attempt identity only.

    It intentionally does not claim to construct an execution bundle. Artifact
    durability is proved separately through the production indexed artifact API.
    """

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        spec, projection = self._attempt(
            fold,
            ordinal=1,
            parent=None,
            occurred_at=occurred_at,
        )
        return FirstAttempt(spec, projection)

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt:
        return build_successor_queued_attempt(
            fold,
            parent,
            resume_from_run_id=resume_from_run_id,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _attempt(
        fold: FoldView,
        *,
        ordinal: int,
        parent: AttemptView | None,
        occurred_at: datetime,
        resume_from_run_id: BacktestRunId | None = None,
    ) -> tuple[AttemptPersistenceSpec, AttemptProjection]:
        attempt_id = AttemptId(
            f"attempt-{fold.spec.key.experiment_id}-"
            f"{fold.spec.key.candidate_id}-{fold.spec.key.fold_id}-{ordinal}"
        )
        fingerprint = canonical_payload(
            {
                "fixture_contract": "task22_scheduler_attempt_lineage_v1",
                "fold_key": {
                    "experiment_id": str(fold.spec.key.experiment_id),
                    "candidate_id": str(fold.spec.key.candidate_id),
                    "fold_id": str(fold.spec.key.fold_id),
                },
                "fold_payload_hash": str(fold.spec.payload_hash),
            }
        ).content_hash
        if parent is not None:
            fingerprint = parent.spec.reproduction_fingerprint
        return (
            AttemptPersistenceSpec(
                attempt_id,
                fold.spec.key,
                ordinal,
                None if parent is None else parent.spec.attempt_id,
                resume_from_run_id,
                fingerprint,
                occurred_at,
            ),
            AttemptProjection(
                attempt_id,
                ExperimentStatus.QUEUED,
                None,
                None,
                None,
                occurred_at,
                occurred_at,
                0,
            ),
        )


def _launch(
    experiment_id: str,
    *,
    worker_count: int,
    candidate_count: int,
) -> ExperimentLaunchSpec:
    candidates = tuple(
        CandidateSpec(
            CandidateId(f"candidate-{ordinal}"),
            ordinal,
            ordinal == 1,
            {"value": ordinal},
        )
        for ordinal in range(1, candidate_count + 1)
    )
    experiment = ExperimentId(experiment_id)
    return ExperimentLaunchSpec(
        experiment_id=experiment,
        strategy_version=StrategyVersion("strategy@task22"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-task22"),
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
            candidates[0].candidate_id,
            "Bound scheduler capacity without duplicate work.",
            TrialFamilyDeclaration(
                f"task22-family-{experiment_id}",
                tuple(
                    LogicalTrialIdentity(
                        experiment,
                        candidate.candidate_id,
                        candidate.ordinal,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    )
                    for candidate in candidates
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec("r3", 1, ContentHash("b" * 64)),
        seed=42,
        worker_count=worker_count,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _folds(spec: ExperimentLaunchSpec) -> tuple[FoldPersistenceSpec, ...]:
    folds: list[FoldPersistenceSpec] = []
    roles = (
        FoldRole.EXPLORATION,
        FoldRole.WALK_FORWARD,
        FoldRole.WALK_FORWARD,
        FoldRole.HOLDOUT,
    )
    for candidate in spec.candidates:
        for ordinal, role in enumerate(roles, start=1):
            folds.append(
                FoldPersistenceSpec.create(
                    FoldKey(
                        spec.experiment_id,
                        candidate.candidate_id,
                        FoldId(f"fold-{candidate.ordinal}-{ordinal}"),
                    ),
                    ordinal,
                    role,
                    (
                        None
                        if role is FoldRole.EXPLORATION
                        else DateWindow(date(2020, 1, 1), date(2024, 12, 31))
                    ),
                    DateWindow(
                        date(2025, ordinal, 1),
                        date(2025, ordinal, 28),
                    ),
                    2,
                    1,
                )
            )
    return tuple(folds)


def _persist_enqueued(
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
) -> None:
    writer.create_experiment(
        ResearchCycleIdentity(
            f"cycle-{launch.experiment_id}",
            ContentHash("c" * 64),
        ),
        launch,
        ExperimentRecord(
            launch.experiment_id,
            ExperimentStatus.DRAFT,
            ExperimentDesiredState.RUN,
            ExperimentStage.PREFLIGHT,
            NOW,
        ),
    )
    folds = _folds(launch)
    for fold in folds:
        writer.add_fold(
            fold,
            FoldProjection(
                fold.key,
                ExperimentStatus.QUEUED,
                None,
                NOW,
                NOW,
                0,
            ),
        )
    writer.enqueue_experiment(
        launch.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=ExperimentEnqueueFence.create(gates=(), folds=folds),
    )


def _open(
    data_root: Path,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
]:
    database = ResearchExperimentDatabase(data_root)
    database.initialize()
    return (
        database,
        SQLiteExperimentReader(database),
        SQLiteExperimentWriter(database),
    )


def _coordinator(
    database: ResearchExperimentDatabase,
    *,
    owner: str,
    clock: datetime,
    lease_duration: timedelta = timedelta(minutes=5),
    checkpoints: set[str] | None = None,
) -> ExperimentExecutionCoordinator:
    available = set() if checkpoints is None else checkpoints
    return ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(
            SQLiteExperimentReader(database),
            SQLiteExperimentWriter(database),
        ),
        first_attempt_factory=_AttemptLineageFactory(),
        owner_token=owner,
        lease_duration=lease_duration,
        clock=lambda: clock,
        checkpoint_available=available.__contains__,
        checkpoint_resumable=available.__contains__,
    )


def _attempts(
    reader: SQLiteExperimentReader,
    experiment_id: ExperimentId,
) -> tuple[AttemptView, ...]:
    return reader.list_experiment_attempts(experiment_id)


@dataclass(frozen=True, slots=True)
class _ArtifactProof:
    artifact_id: str
    relative_path: str
    payload: dict[str, object]
    published: ArtifactRecord
    pinned: ArtifactRecord


def _publish_checkpoint_artifact(
    database: ResearchExperimentDatabase,
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    attempt: AttemptView,
    checkpoint_run_id: BacktestRunId,
    lease: SchedulerLease,
) -> _ArtifactProof:
    fold_key = attempt.spec.fold_key
    artifact_id = f"artifact-task22-{attempt.spec.attempt_id}"
    relative_path = (
        f"experiments/{fold_key.experiment_id}/"
        f"candidates/{fold_key.candidate_id}/folds/{fold_key.fold_id}/"
        f"attempts/{attempt.spec.attempt_id}/checkpoint-lineage.json"
    )
    payload: dict[str, object] = {
        "experiment_id": str(fold_key.experiment_id),
        "candidate_id": str(fold_key.candidate_id),
        "fold_id": str(fold_key.fold_id),
        "attempt_id": str(attempt.spec.attempt_id),
        "checkpoint_ref": str(checkpoint_run_id),
        "reproduction_fingerprint": str(attempt.spec.reproduction_fingerprint),
    }
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    published = service.publish_indexed_json(
        ArtifactPublicationSpec(
            artifact_id=artifact_id,
            experiment_id=fold_key.experiment_id,
            candidate_id=fold_key.candidate_id,
            fold_id=fold_key.fold_id,
            attempt_id=attempt.spec.attempt_id,
            artifact_kind="checkpoint_lineage",
            relative_path=relative_path,
            reproduction_fingerprint=attempt.spec.reproduction_fingerprint,
            audit={
                **payload,
                "run_id": str(checkpoint_run_id),
                "created_at": (NOW + timedelta(seconds=2)).isoformat(),
            },
            created_at=NOW + timedelta(seconds=2),
        ),
        payload,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1_500_000,
    )
    pinned = service.pin_indexed_artifact(
        published.artifact_id,
        expected_revision=published.revision,
        pinned_at=NOW + timedelta(seconds=2),
    )
    assert pinned.is_pinned is True
    assert service.read_indexed_json(published.artifact_id) == payload
    return _ArtifactProof(artifact_id, relative_path, payload, published, pinned)


def _assert_reopened_artifact(
    database: ResearchExperimentDatabase,
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    attempt: AttemptView,
    proof: _ArtifactProof,
) -> ArtifactRecord:
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    indexed_by_id = reader.get_artifact(proof.artifact_id)
    indexed_by_path = reader.get_artifact_by_relative_path(proof.relative_path)
    assert indexed_by_id == indexed_by_path == proof.pinned
    assert indexed_by_id is not None
    assert indexed_by_id.experiment_id == attempt.spec.fold_key.experiment_id
    assert indexed_by_id.candidate_id == attempt.spec.fold_key.candidate_id
    assert indexed_by_id.fold_id == attempt.spec.fold_key.fold_id
    assert indexed_by_id.attempt_id == attempt.spec.attempt_id
    assert (
        indexed_by_id.reproduction_fingerprint == attempt.spec.reproduction_fingerprint
    )
    assert indexed_by_id.content_hash == proof.published.content_hash
    assert indexed_by_id.relative_path == proof.relative_path
    assert service.read_indexed_json(proof.artifact_id) == proof.payload
    verified_bytes = service.read_indexed_artifact_bytes(proof.artifact_id)
    assert hashlib.sha256(verified_bytes).hexdigest() == str(
        proof.published.content_hash
    )
    return indexed_by_id


def test_128_candidate_real_preflight_launches_at_registered_run_ceiling(
    tmp_path: Path,
) -> None:
    database, reader, writer = _open(tmp_path)
    base = golden_support.build_planning_request()
    matrix = CandidateMatrixSpec(
        baseline=base.matrix_spec.baseline,
        axes=(ParameterAxis("research.rank_window", tuple(range(127))),),
        candidate_limit=128,
    )
    family = declare_trial_family(
        experiment_id=base.experiment_id,
        matrix_spec=matrix,
        family_id=base.promotion_objective.trial_family.family_id,
    )
    request = replace(
        base,
        matrix_spec=matrix,
        promotion_objective=replace(
            base.promotion_objective,
            baseline_candidate_id=family.current_members[0].candidate_id,
            trial_family=family,
        ),
        budget=ExperimentBudgetSpec(
            candidate_limit=128,
            fold_run_limit=385,
            trading_session_limit=1_000_000,
            disk_byte_limit=100_000_000,
        ),
        worker_count=4,
    )
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=golden_support.PlanningCertificationProbe(),
        executor_probe=golden_support.PlanningExecutorProbe(),
        authority_probe=golden_support.PlanningAuthorityProbe(),
    )

    try:
        report = process.preflight(request)
        assert report.status is ExperimentPreflightStatus.READY
        assert report.candidate_count == 128
        assert report.budget_run_count == 385
        assert report.planned_fold_count == 512
        assert report.plan_hash is not None

        receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)

        launch = reader.get_launch_spec(ExperimentId(request.experiment_id))
        assert launch is not None
        assert receipt.candidate_count == len(launch.candidates) == 128
        assert receipt.fold_count == len(reader.list_folds(launch.experiment_id)) == 512
        assert launch.worker_count == 4
        assert launch.budget.candidate_limit == 128
        assert launch.budget.fold_run_limit == 385
    finally:
        database.close_all()


@pytest.mark.parametrize("worker_count", [2, 4])
def test_sqlite_tick_dispatches_exact_capacity_and_excludes_second_owner(
    tmp_path: Path,
    worker_count: int,
) -> None:
    database, reader, writer = _open(tmp_path)
    launch = _launch(
        f"experiment-task22-capacity-{worker_count}",
        worker_count=worker_count,
        candidate_count=6,
    )
    _persist_enqueued(writer, launch)
    owner = _coordinator(
        database,
        owner=f"capacity-owner-{worker_count}",
        clock=NOW + timedelta(seconds=1),
    )
    contender = _coordinator(
        database,
        owner=f"capacity-contender-{worker_count}",
        clock=NOW + timedelta(seconds=2),
    )

    first = owner.tick(occurred_at=NOW + timedelta(seconds=1))
    repeated = owner.tick(occurred_at=NOW + timedelta(seconds=2))
    blocked = contender.tick(occurred_at=NOW + timedelta(seconds=2))

    attempts = _attempts(reader, launch.experiment_id)
    running_folds = tuple(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.projection.status is ExperimentStatus.RUNNING
    )
    assert first.state is SchedulerTickState.DISPATCHED
    assert len(first.dispatches) == worker_count
    assert repeated.state is SchedulerTickState.WAITING
    assert repeated.dispatches == ()
    assert blocked.state is SchedulerTickState.LEASE_BUSY
    assert len(attempts) == len(running_folds) == worker_count
    assert len({attempt.spec.attempt_id for attempt in attempts}) == worker_count
    assert len({attempt.spec.fold_key for attempt in attempts}) == worker_count
    database.close_all()


def test_two_queued_experiments_enter_singleton_slot_only_in_queue_order(
    tmp_path: Path,
) -> None:
    database, reader, writer = _open(tmp_path)
    queue_head = _launch(
        "experiment-task22-queue-head",
        worker_count=2,
        candidate_count=1,
    )
    successor = _launch(
        "experiment-task22-queue-successor",
        worker_count=2,
        candidate_count=1,
    )
    _persist_enqueued(writer, queue_head)
    _persist_enqueued(writer, successor)
    original = _coordinator(
        database,
        owner="queue-head-owner",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
    )
    blocked_owner = _coordinator(
        database,
        owner="queue-successor-contender",
        clock=NOW + timedelta(seconds=2),
    )

    head_dispatch = original.tick(occurred_at=NOW + timedelta(seconds=1))
    blocked = blocked_owner.tick(occurred_at=NOW + timedelta(seconds=2))

    assert head_dispatch.experiment_id == queue_head.experiment_id
    assert blocked.state is SchedulerTickState.LEASE_BUSY
    assert _attempts(reader, successor.experiment_id) == ()

    replacement = _coordinator(
        database,
        owner="expired-head-replacement",
        clock=NOW + timedelta(seconds=10),
    )
    reclaimed = replacement.tick(occurred_at=NOW + timedelta(seconds=10))

    assert reclaimed.experiment_id == queue_head.experiment_id
    assert reclaimed.state is SchedulerTickState.DISPATCHED
    assert _attempts(reader, successor.experiment_id) == ()

    head_projection = reader.get_experiment_projection(queue_head.experiment_id)
    assert head_projection is not None
    replacement.cancel(
        experiment_id=str(queue_head.experiment_id),
        expected_revision=head_projection.revision,
        occurred_at=NOW + timedelta(seconds=11),
    )
    drained = replacement.tick(occurred_at=NOW + timedelta(seconds=12))
    terminal = reader.get_experiment_projection(queue_head.experiment_id)
    assert terminal is not None
    assert drained.experiment_id == queue_head.experiment_id
    assert terminal.record.status is ExperimentStatus.CANCELLED
    assert _attempts(reader, successor.experiment_id) == ()

    handed_off = replacement.tick(occurred_at=NOW + timedelta(seconds=13))

    assert handed_off.state is SchedulerTickState.DISPATCHED
    assert handed_off.experiment_id == successor.experiment_id
    assert len(_attempts(reader, successor.experiment_id)) == 1
    assert reader.get_scheduler_slot().experiment_id == successor.experiment_id
    database.close_all()


def test_reopen_reclaims_expired_lease_and_preserves_checkpoint_lineage(
    tmp_path: Path,
) -> None:
    database, reader, writer = _open(tmp_path)
    launch = _launch(
        "experiment-task22-reopen",
        worker_count=2,
        candidate_count=2,
    )
    _persist_enqueued(writer, launch)
    checkpoints: set[str] = set()
    original = _coordinator(
        database,
        owner="reopen-owner-a",
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
        checkpoints=checkpoints,
    )
    first = original.tick(occurred_at=NOW + timedelta(seconds=1))
    checkpointed = original.start_attempt(
        first.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    checkpoint_run_id = checkpointed.projection.backtest_run_id
    assert checkpoint_run_id is not None
    checkpoints.add(str(checkpoint_run_id))
    original.record_checkpoint(
        checkpointed.spec.attempt_id,
        CheckpointRef(str(checkpoint_run_id)),
        occurred_at=NOW + timedelta(seconds=2),
    )
    original_lease = original.renew_lease()
    artifact_proof = _publish_checkpoint_artifact(
        database,
        reader,
        writer,
        checkpointed,
        checkpoint_run_id,
        original_lease,
    )
    parent_by_id = {
        attempt.spec.attempt_id: attempt
        for attempt in _attempts(reader, launch.experiment_id)
    }
    database.close_all()

    reopened, durable_reader, durable_writer = _open(tmp_path)
    durable_artifact = _assert_reopened_artifact(
        reopened,
        durable_reader,
        durable_writer,
        checkpointed,
        artifact_proof,
    )
    recovered = _coordinator(
        reopened,
        owner="reopen-owner-b",
        clock=NOW + timedelta(seconds=10),
        checkpoints=checkpoints,
    ).tick(occurred_at=NOW + timedelta(seconds=10))

    assert recovered.state is SchedulerTickState.DISPATCHED
    assert len(recovered.dispatches) == 2
    for dispatch in recovered.dispatches:
        successor = dispatch.attempt
        assert successor.spec.parent_attempt_id in parent_by_id
        parent = parent_by_id[successor.spec.parent_attempt_id]
        assert successor.spec.ordinal == parent.spec.ordinal + 1
        assert (
            successor.spec.reproduction_fingerprint
            == parent.spec.reproduction_fingerprint
        )
        expected_resume = (
            checkpoint_run_id
            if parent.spec.attempt_id == checkpointed.spec.attempt_id
            else None
        )
        assert successor.spec.resume_from_run_id == expected_resume
        if expected_resume is not None:
            assert (
                successor.spec.reproduction_fingerprint
                == durable_artifact.reproduction_fingerprint
            )
    durable_attempts = _attempts(durable_reader, launch.experiment_id)
    assert len(durable_attempts) == 4
    assert (
        sum(
            attempt.projection.status
            in (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)
            for attempt in durable_attempts
        )
        == 2
    )
    with pytest.raises(ExperimentLeaseLostError):
        durable_writer.renew_lease(
            original_lease.fence,
            now_epoch_us=NOW_US + 11_000_000,
            new_lease_until_epoch_us=NOW_US + 20_000_000,
        )
    reopened.close_all()


def test_pause_resume_retains_queue_and_never_duplicates_a_fold_claim(
    tmp_path: Path,
) -> None:
    database, reader, writer = _open(tmp_path)
    launch = _launch(
        "experiment-task22-pause-resume",
        worker_count=2,
        candidate_count=3,
    )
    _persist_enqueued(writer, launch)
    coordinator = _coordinator(
        database,
        owner="pause-resume-owner",
        clock=NOW + timedelta(seconds=1),
    )
    initial = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    parents = {
        dispatch.attempt.spec.attempt_id: dispatch.attempt
        for dispatch in initial.dispatches
    }
    projection = reader.get_experiment_projection(launch.experiment_id)
    assert projection is not None
    coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=projection.revision,
        occurred_at=NOW + timedelta(seconds=2),
    )

    drained = coordinator.tick(occurred_at=NOW + timedelta(seconds=3))
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    assert drained.state is SchedulerTickState.WAITING
    assert paused.record.status is ExperimentStatus.PAUSED
    assert len(_attempts(reader, launch.experiment_id)) == 2

    coordinator.resume(
        experiment_id=str(launch.experiment_id),
        expected_revision=paused.revision,
        occurred_at=NOW + timedelta(seconds=4),
    )
    resumed = coordinator.tick(occurred_at=NOW + timedelta(seconds=5))
    repeated = coordinator.tick(occurred_at=NOW + timedelta(seconds=6))

    assert resumed.state is SchedulerTickState.DISPATCHED
    assert len(resumed.dispatches) == 2
    for dispatch in resumed.dispatches:
        successor = dispatch.attempt
        assert successor.spec.parent_attempt_id in parents
        parent = parents[successor.spec.parent_attempt_id]
        assert successor.spec.resume_from_run_id is None
        assert (
            successor.spec.reproduction_fingerprint
            == parent.spec.reproduction_fingerprint
        )
    attempts = _attempts(reader, launch.experiment_id)
    exploration = tuple(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.EXPLORATION
    )
    assert repeated.state is SchedulerTickState.WAITING
    assert len(attempts) == 4
    assert len({attempt.spec.attempt_id for attempt in attempts}) == 4
    assert (
        sum(fold.projection.status is ExperimentStatus.RUNNING for fold in exploration)
        == 2
    )
    assert (
        sum(fold.projection.status is ExperimentStatus.QUEUED for fold in exploration)
        == 1
    )
    database.close_all()
