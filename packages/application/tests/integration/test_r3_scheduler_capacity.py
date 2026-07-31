"""Acceptance for bounded, durable R3 scheduler capacity and recovery."""

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
    LeaseFence,
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
    MetricEvidenceLineage,
    ObjectiveMetric,
    PromotionObjective,
    ResearchMetricValue,
    TrialOutcome,
    TrialStatus,
    build_trial_ledger,
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
from ditto_application.processes.experiments._selection_evidence_artifact import (
    PublishedSelectionEvidence,
    SelectionEvidencePublisher,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentDispatch,
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
    ExperimentSchedulerSnapshot,
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
    ResearchExecutionDirective,
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
                "fixture_contract": "scheduler_capacity_attempt_lineage_v1",
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
        strategy_version=StrategyVersion("strategy@scheduler-capacity"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-scheduler-capacity"),
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
                f"scheduler-capacity-family-{experiment_id}",
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


def _minimal_preselection_folds_per_candidate(
    spec: ExperimentLaunchSpec,
) -> tuple[FoldPersistenceSpec, ...]:
    """Build the smallest real protocol that reaches candidate selection."""
    folds: list[FoldPersistenceSpec] = []
    for candidate in spec.candidates:
        folds.extend(
            (
                FoldPersistenceSpec.create(
                    FoldKey(
                        spec.experiment_id,
                        candidate.candidate_id,
                        FoldId(f"fold-{candidate.ordinal}-exploration"),
                    ),
                    1,
                    FoldRole.EXPLORATION,
                    None,
                    DateWindow(date(2025, 1, 1), date(2025, 1, 31)),
                    2,
                    1,
                ),
                FoldPersistenceSpec.create(
                    FoldKey(
                        spec.experiment_id,
                        candidate.candidate_id,
                        FoldId(f"fold-{candidate.ordinal}-walk-forward"),
                    ),
                    2,
                    FoldRole.WALK_FORWARD,
                    DateWindow(date(2020, 1, 1), date(2024, 12, 31)),
                    DateWindow(date(2025, 2, 1), date(2025, 2, 28)),
                    2,
                    1,
                ),
            )
        )
    return tuple(folds)


def _persist_enqueued(
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    *,
    folds: tuple[FoldPersistenceSpec, ...] | None = None,
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
    persisted_folds = _folds(launch) if folds is None else folds
    for fold in persisted_folds:
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
        launch_fence=ExperimentEnqueueFence.create(gates=(), folds=persisted_folds),
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
    selection_evidence_publisher: SelectionEvidencePublisher | None = None,
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
        selection_evidence_publisher=selection_evidence_publisher,
    )


class _SelectionEvidencePublisherProbe:
    """Make reaching candidate-selection observable without widening Task 10."""

    def __init__(self, launch: ExperimentLaunchSpec) -> None:
        self.calls = 0
        lineage = MetricEvidenceLineage(
            ("scheduler-capacity://selection-probe",),
            (ContentHash("6" * 64),),
        )
        ledger = build_trial_ledger(
            launch.promotion_objective,
            tuple(
                TrialOutcome(
                    trial=launch.promotion_objective.trial_family.current_members[
                        candidate.ordinal - 1
                    ],
                    status=TrialStatus.COMPLETED,
                    metrics={
                        ResearchMetricId.NET_RETURN: ResearchMetricValue(
                            ResearchMetricId.NET_RETURN,
                            float(candidate.ordinal),
                        )
                    },
                    holdout_metrics={},
                    source_projection_hash=ContentHash("7" * 64),
                    metric_evidence={ResearchMetricId.NET_RETURN: lineage},
                )
                for candidate in launch.candidates
            ),
        )
        self.evidence = PublishedSelectionEvidence(
            ArtifactRecord(
                artifact_id=f"selection-evidence-{ledger.content_hash}",
                experiment_id=launch.experiment_id,
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                artifact_kind="selection_evidence",
                relative_path=(
                    f"experiments/{launch.experiment_id}/selection-evidence.json"
                ),
                content_hash=ledger.content_hash,
                schema_hash=ContentHash("8" * 64),
                row_count=1,
                byte_size=1,
                reproduction_fingerprint=ContentHash("9" * 64),
                manifest={},
                is_pinned=False,
                pinned_at=None,
                created_at=NOW,
                revision=0,
            ),
            ledger,
        )

    def publish_selection_evidence(
        self,
        _snapshot: ExperimentSchedulerSnapshot,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> PublishedSelectionEvidence:
        assert lease_fence.owner_token
        assert now_epoch_us > 0
        self.calls += 1
        return self.evidence


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
    artifact_id = f"artifact-scheduler-capacity-{attempt.spec.attempt_id}"
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
        f"experiment-scheduler-capacity-{worker_count}",
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
        "experiment-scheduler-capacity-queue-head",
        worker_count=2,
        candidate_count=1,
    )
    successor = _launch(
        "experiment-scheduler-capacity-queue-successor",
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
        "experiment-scheduler-capacity-reopen",
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
        "experiment-scheduler-capacity-pause-resume",
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


@dataclass(frozen=True, slots=True)
class _InterruptedCapacityRun:
    launch: ExperimentLaunchSpec
    queued_successor: ExperimentLaunchSpec
    launch_folds: tuple[FoldPersistenceSpec, ...]
    checkpointed: AttemptView
    checkpoint_run_id: BacktestRunId
    artifact_proof: _ArtifactProof
    original_lease: SchedulerLease
    paused_revision: int
    first_attempt_ids: frozenset[AttemptId]
    first_claim_generations: frozenset[tuple[FoldKey, int]]
    checkpoints: set[str]
    original_owner: str


@dataclass(frozen=True, slots=True)
class _ResumedCapacityRun:
    database: ResearchExperimentDatabase
    reader: SQLiteExperimentReader
    writer: SQLiteExperimentWriter
    coordinator: ExperimentExecutionCoordinator
    durable_artifact: ArtifactRecord
    selection_probe: _SelectionEvidencePublisherProbe
    replacement_owner: str


def _prepare_interrupted_capacity_run(
    data_root: Path,
    worker_count: int,
) -> _InterruptedCapacityRun:
    database, reader, writer = _open(data_root)
    try:
        return _prepare_interrupted_capacity_run_open(
            database,
            reader,
            writer,
            worker_count,
        )
    finally:
        database.close_all()


def _prepare_interrupted_capacity_run_open(
    database: ResearchExperimentDatabase,
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    worker_count: int,
) -> _InterruptedCapacityRun:
    launch = _launch(
        f"experiment-task10-restart-{worker_count}",
        worker_count=worker_count,
        candidate_count=128,
    )
    successor = _launch(
        f"experiment-task10-second-{worker_count}",
        worker_count=worker_count,
        candidate_count=1,
    )
    launch_folds = _minimal_preselection_folds_per_candidate(launch)
    _persist_enqueued(writer, launch, folds=launch_folds)
    _persist_enqueued(
        writer,
        successor,
        folds=_minimal_preselection_folds_per_candidate(successor),
    )
    checkpoints: set[str] = set()
    original_owner = f"task10-owner-before-restart-{worker_count}"
    coordinator = _coordinator(
        database,
        owner=original_owner,
        clock=NOW + timedelta(seconds=1),
        lease_duration=timedelta(seconds=2),
        checkpoints=checkpoints,
    )
    first = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    assert first.state is SchedulerTickState.DISPATCHED
    assert len(first.dispatches) == worker_count
    assert _attempts(reader, successor.experiment_id) == ()
    first_attempt_ids = frozenset(
        dispatch.attempt.spec.attempt_id for dispatch in first.dispatches
    )
    first_generations = frozenset(
        (dispatch.fold.spec.key, dispatch.attempt.spec.ordinal)
        for dispatch in first.dispatches
    )
    assert len(first_attempt_ids) == len(first_generations) == worker_count
    checkpointed = coordinator.start_attempt(
        first.dispatches[0],
        occurred_at=NOW + timedelta(seconds=2),
    ).attempt
    run_id = checkpointed.projection.backtest_run_id
    assert run_id is not None
    checkpoints.add(str(run_id))
    coordinator.record_checkpoint(
        checkpointed.spec.attempt_id,
        CheckpointRef(str(run_id)),
        occurred_at=NOW + timedelta(seconds=2),
    )
    original_lease = coordinator.renew_lease()
    proof = _publish_checkpoint_artifact(
        database,
        reader,
        writer,
        checkpointed,
        run_id,
        original_lease,
    )
    running = reader.get_experiment_projection(launch.experiment_id)
    assert running is not None
    coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=running.revision,
        occurred_at=NOW + timedelta(seconds=3),
    )
    coordinator.tick(occurred_at=NOW + timedelta(seconds=4))
    coordinator.cooperative_stop_attempt(
        checkpointed.spec.attempt_id,
        ResearchExecutionDirective.PAUSE,
        occurred_at=NOW + timedelta(seconds=5),
    )
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    _assert_paused_capacity_state(reader, launch, worker_count)
    return _InterruptedCapacityRun(
        launch,
        successor,
        launch_folds,
        checkpointed,
        run_id,
        proof,
        original_lease,
        paused.revision,
        first_attempt_ids,
        first_generations,
        checkpoints,
        original_owner,
    )


def _assert_paused_capacity_state(
    reader: SQLiteExperimentReader,
    launch: ExperimentLaunchSpec,
    worker_count: int,
) -> None:
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    assert paused.record.status is ExperimentStatus.PAUSED
    attempts = _attempts(reader, launch.experiment_id)
    assert len(attempts) == worker_count
    assert all(
        attempt.projection.status is ExperimentStatus.CANCELLED for attempt in attempts
    )
    assert all(
        fold.projection.status is ExperimentStatus.QUEUED
        for fold in reader.list_folds(launch.experiment_id)
    )


def _resume_capacity_run(
    data_root: Path,
    interrupted: _InterruptedCapacityRun,
    worker_count: int,
) -> _ResumedCapacityRun:
    database, reader, writer = _open(data_root)
    try:
        return _resume_capacity_run_open(
            database,
            reader,
            writer,
            interrupted,
            worker_count,
        )
    except BaseException:
        database.close_all()
        raise


def _resume_capacity_run_open(
    database: ResearchExperimentDatabase,
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    interrupted: _InterruptedCapacityRun,
    worker_count: int,
) -> _ResumedCapacityRun:
    artifact = _assert_reopened_artifact(
        database,
        reader,
        writer,
        interrupted.checkpointed,
        interrupted.artifact_proof,
    )
    replacement_owner = f"task10-owner-after-restart-{worker_count}"
    probe = _SelectionEvidencePublisherProbe(interrupted.launch)
    coordinator = _coordinator(
        database,
        owner=replacement_owner,
        clock=NOW + timedelta(seconds=10),
        lease_duration=timedelta(minutes=5),
        checkpoints=interrupted.checkpoints,
        selection_evidence_publisher=probe,
    )
    coordinator.resume(
        experiment_id=str(interrupted.launch.experiment_id),
        expected_revision=interrupted.paused_revision,
        occurred_at=NOW + timedelta(seconds=10),
    )
    return _ResumedCapacityRun(
        database,
        reader,
        writer,
        coordinator,
        artifact,
        probe,
        replacement_owner,
    )


def _drain_capacity_run(
    resumed: _ResumedCapacityRun,
    interrupted: _InterruptedCapacityRun,
    worker_count: int,
) -> int:
    seen_attempt_ids = set(interrupted.first_attempt_ids)
    seen_generations = set(interrupted.first_claim_generations)
    max_live = 0
    tick_offset = 11
    for _ in range(140):
        result = resumed.coordinator.tick(
            occurred_at=NOW + timedelta(seconds=tick_offset)
        )
        tick_offset += 1
        if result.state is SchedulerTickState.CANDIDATE_SELECTION:
            assert resumed.selection_probe.calls == 1
            return max_live
        if result.state is SchedulerTickState.WAITING:
            continue
        assert result.state is SchedulerTickState.DISPATCHED
        assert 1 <= len(result.dispatches) <= worker_count
        assert result.experiment_id == interrupted.launch.experiment_id
        assert (
            _attempts(resumed.reader, interrupted.queued_successor.experiment_id) == ()
        )
        _assert_new_claim_batch(result.dispatches, seen_attempt_ids, seen_generations)
        for dispatch in result.dispatches:
            resumed.coordinator.start_attempt(
                dispatch,
                occurred_at=NOW + timedelta(seconds=tick_offset),
            )
            tick_offset += 1
        live = _live_attempts(resumed.reader, interrupted.launch.experiment_id)
        max_live = max(max_live, len(live))
        assert len(live) <= worker_count
        assert len({attempt.spec.fold_key for attempt in live}) == len(live)
        for dispatch in result.dispatches:
            resumed.coordinator.complete_attempt(
                dispatch.attempt.spec.attempt_id,
                occurred_at=NOW + timedelta(seconds=tick_offset),
            )
            tick_offset += 1
    pytest.fail("literal 128-candidate scheduler did not reach selection")


def _assert_new_claim_batch(
    dispatches: tuple[ExperimentDispatch, ...],
    seen_attempt_ids: set[AttemptId],
    seen_generations: set[tuple[FoldKey, int]],
) -> None:
    attempt_ids = {dispatch.attempt.spec.attempt_id for dispatch in dispatches}
    fold_keys = {dispatch.fold.spec.key for dispatch in dispatches}
    generations = {
        (
            dispatch.fold.spec.key,
            dispatch.attempt.spec.ordinal,
        )
        for dispatch in dispatches
    }
    assert len(attempt_ids) == len(fold_keys) == len(dispatches)
    assert seen_attempt_ids.isdisjoint(attempt_ids)
    assert seen_generations.isdisjoint(generations)
    seen_attempt_ids.update(attempt_ids)
    seen_generations.update(generations)


def _live_attempts(
    reader: SQLiteExperimentReader,
    experiment_id: ExperimentId,
) -> tuple[AttemptView, ...]:
    return tuple(
        attempt
        for attempt in _attempts(reader, experiment_id)
        if attempt.projection.status
        in (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)
    )


def _assert_completed_capacity_run(
    resumed: _ResumedCapacityRun,
    interrupted: _InterruptedCapacityRun,
    worker_count: int,
    max_live: int,
) -> None:
    attempts = _attempts(resumed.reader, interrupted.launch.experiment_id)
    completed = tuple(
        attempt
        for attempt in attempts
        if attempt.projection.status is ExperimentStatus.COMPLETED
    )
    cancelled = tuple(
        attempt
        for attempt in attempts
        if attempt.projection.status is ExperimentStatus.CANCELLED
    )
    folds = resumed.reader.list_folds(interrupted.launch.experiment_id)
    assert max_live == worker_count
    assert len(interrupted.launch.candidates) == 128
    assert len({item.candidate_id for item in interrupted.launch.candidates}) == 128
    assert len(folds) == len(completed) == len(interrupted.launch_folds) == 256
    assert len(cancelled) == worker_count
    assert len(attempts) == len(interrupted.launch_folds) + worker_count
    assert all(fold.projection.status is ExperimentStatus.COMPLETED for fold in folds)
    assert {item.spec.fold_key.candidate_id for item in completed} == {
        item.candidate_id for item in interrupted.launch.candidates
    }
    assert not _live_attempts(resumed.reader, interrupted.launch.experiment_id)
    successors = tuple(
        attempt
        for attempt in attempts
        if attempt.spec.parent_attempt_id == interrupted.checkpointed.spec.attempt_id
    )
    assert len(successors) == 1
    assert successors[0].spec.resume_from_run_id == interrupted.checkpoint_run_id
    assert (
        successors[0].spec.reproduction_fingerprint
        == resumed.durable_artifact.reproduction_fingerprint
    )
    slot = resumed.reader.get_scheduler_slot()
    assert slot.experiment_id == interrupted.launch.experiment_id
    assert slot.owner_token is not None
    assert not slot.owner_token.startswith(f"{interrupted.original_owner}:")
    assert slot.owner_token.startswith(f"{resumed.replacement_owner}:")
    assert slot.lease_until_epoch_us is not None
    assert slot.lease_until_epoch_us > NOW_US + 10_000_000
    with pytest.raises(ExperimentLeaseLostError):
        resumed.writer.renew_lease(
            interrupted.original_lease.fence,
            now_epoch_us=NOW_US + 11_000_000,
            new_lease_until_epoch_us=NOW_US + 20_000_000,
        )
    assert _attempts(resumed.reader, interrupted.queued_successor.experiment_id) == ()


@pytest.mark.parametrize("worker_count", [2, 4])
def test_128_candidates_survive_restart_without_duplicate_claims(
    tmp_path: Path,
    worker_count: int,
) -> None:
    """Prove the literal Task 10 ceiling across pause, restart, and reclaim."""
    interrupted = _prepare_interrupted_capacity_run(tmp_path, worker_count)
    resumed = _resume_capacity_run(tmp_path, interrupted, worker_count)
    try:
        max_live = _drain_capacity_run(resumed, interrupted, worker_count)
        _assert_completed_capacity_run(resumed, interrupted, worker_count, max_live)
    finally:
        resumed.database.close_all()
