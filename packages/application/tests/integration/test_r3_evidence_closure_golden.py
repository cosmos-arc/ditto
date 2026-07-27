"""Deterministic R3 evidence-collection closure golden test.

This integration test exercises the full Task 1-4 R3 closure seam against a
fresh ``tmp_path`` SQLite research database:

* The durable :class:`ExperimentExecutionCoordinator` is constructed with a
  real :class:`ExperimentEvidenceCollector` injected (the existing holdout
  integration tests pass ``evidence_collector=None`` and so never close the
  EVIDENCE branch).
* The fixture drives one experiment tick through PREFLIGHT, EXPLORATION,
  WALK_FORWARD, CANDIDATE_SELECTION, HOLDOUT, and finally EVIDENCE.
* At EVIDENCE the coordinator must invoke the collector, which reconstructs the
  persisted preflight, reads four indexed walk-forward reports, assembles real
  comparison metrics, evaluates the eleven hard gates, freezes the immutable
  :class:`ReviewPacket`, publishes it through the durable writer protocol, and
  finally transitions the experiment to ``COMPLETED``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    ContentHash,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentStage,
    ExperimentStatus,
    FoldPersistenceSpec,
    FoldRole,
    FoldView,
    ResearchMetricId,
)
from ditto_analysis.experiments.evidence import ReviewPacket
from ditto_analysis.experiments.gates import GateLayer, GateOutcome
from ditto_analysis.experiments.trial_ledger import TrialLedger
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.builders.research_artifact_loader import (
    IndexedBacktestReportArtifactAdapter,
)
from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
)
from ditto_application.processes.experiments._selection_evidence_artifact import (
    DurableSelectionEvidenceService,
    PublishedSelectionEvidence,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.evidence_collector import (
    ExperimentEvidenceCollector,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
)
from ditto_application.processes.experiments.holdout import (
    HoldoutSelectionReason as ApplicationSelectionReason,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
    reconstruct_preflight_report,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
)
from ditto_backtest.statistics import (
    BacktestReport,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
)
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)

NOW = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)

_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"
_GATE_RULES = ("matrix", "executor", "authority", "history", "certification", "budget")
_HARD_GATE_RULE_IDS = (
    "certified_snapshot",
    "ninety_six_month_protocol",
    "pit_known_at",
    "split_purge_embargo",
    "reproduction_fingerprint",
    "cost_assumptions",
    "baseline_declared",
    "trial_declaration",
    "holdout_claim",
    "artifact_completeness",
    "r2_live_gate",
)
_REPORT_NAVS = {
    (True, 2): (102.0, 101.0),
    (True, 3): (101.0, 104.0),
    (False, 2): (110.0, 105.0),
    (False, 3): (106.0, 112.0),
}


def _complete_fold(
    writer: SQLiteExperimentWriter,
    fold: FoldPersistenceSpec | FoldView,
    lease: Any,
    *,
    fingerprint: str = "8" * 64,
) -> None:
    view = fold if isinstance(fold, FoldView) else writer._reader.get_fold(fold.key)
    assert view is not None
    attempt_id = AttemptId(
        "attempt-complete-"
        f"{view.spec.key.experiment_id}-"
        f"{view.spec.key.candidate_id}-"
        f"{view.spec.key.fold_id}"
    )
    attempt_spec = AttemptPersistenceSpec(
        attempt_id,
        view.spec.key,
        1,
        None,
        None,
        ContentHash(fingerprint),
        NOW,
    )
    initial = AttemptProjection(
        attempt_id,
        ExperimentStatus.QUEUED,
        None,
        None,
        None,
        NOW,
        NOW,
        0,
    )
    fold_projection, attempt_projection = writer.claim_fold_and_add_attempt(
        view.spec.key,
        attempt_spec,
        initial,
        expected_fold_revision=view.projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
    )
    running = writer.transition_attempt(
        attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId(f"run-{attempt_id}"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=attempt_projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="first_attempt_started",
        detail={},
    )
    writer.transition_attempt(
        attempt_id,
        target_status=ExperimentStatus.COMPLETED,
        backtest_run_id=running.backtest_run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
        reason_code="first_attempt_completed",
        detail={},
    )
    writer.transition_fold(
        view.spec.key,
        target_status=ExperimentStatus.COMPLETED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=fold_projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 7,
        occurred_at=NOW,
        reason_code="fold_completed",
        detail={},
    )


def _backtest_report(
    attempt: AttemptView,
    fold: FoldView,
    navs: tuple[float, float],
) -> BacktestReport:
    run_id = attempt.projection.backtest_run_id
    assert run_id is not None
    return BacktestReport(
        run_id=str(run_id),
        period=(
            fold.spec.test_window.start.isoformat(),
            fold.spec.test_window.end.isoformat(),
        ),
        initial_cash=100.0,
        final_nav=navs[-1],
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=empty_aggregated_trade_statistics(),
        alpha_stats=empty_alpha_statistics(),
        nav_series=(
            (fold.spec.test_window.start.isoformat(), navs[0]),
            (fold.spec.test_window.end.isoformat(), navs[1]),
        ),
        trade_log=(),
        fill_log=(),
    )


def _report_identity(
    fold: FoldView,
    attempt: AttemptView,
) -> BacktestReportArtifactIdentity:
    run_id = attempt.projection.backtest_run_id
    assert run_id is not None
    return BacktestReportArtifactIdentity(
        experiment_id=fold.spec.key.experiment_id,
        candidate_id=fold.spec.key.candidate_id,
        fold_id=fold.spec.key.fold_id,
        attempt_id=attempt.spec.attempt_id,
        attempt_created_at=attempt.spec.created_at,
        run_id=run_id,
        test_window=fold.spec.test_window,
        reproduction_fingerprint=attempt.spec.reproduction_fingerprint,
    )


def _advance_to_candidate_selection(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    resolver: Any,
) -> Any:
    slot = reader.get_scheduler_slot()
    lease = writer.try_claim_lease(
        launch.experiment_id,
        "r3-evidence-golden-owner",
        expected_revision=slot.revision,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 60_000_000,
    )
    assert lease is not None
    writer.transition_scheduled_experiment(
        launch.experiment_id,
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
        occurred_at=NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="scheduler_dispatch",
        detail={},
    )
    folds = reader.list_folds(launch.experiment_id)
    for fold in folds:
        if fold.spec.fold_role is FoldRole.EXPLORATION:
            _complete_fold(writer, fold, lease)
    projection = writer.advance_experiment_stage(
        launch.experiment_id,
        target_stage=ExperimentStage.WALK_FORWARD,
        expected_revision=2,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "exploration"},
    )
    assert projection.revision == 3
    candidates = {candidate.candidate_id: candidate for candidate in launch.candidates}
    for fold in folds:
        if fold.spec.fold_role is not FoldRole.WALK_FORWARD:
            continue
        candidate = candidates[fold.spec.key.candidate_id]
        fingerprint = (
            str(resolver.resolve(fold).reproduction_fingerprint)
            if candidate.is_baseline
            else "8" * 64
        )
        _complete_fold(writer, fold, lease, fingerprint=fingerprint)
    return lease


def _publish_walk_forward_reports(
    tmp_path: Path,
    database: ResearchExperimentDatabase,
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    lease: Any,
    resolver: Any,
) -> tuple[WalkForwardEvidenceAssembler, ResearchArtifactService]:
    service = ResearchArtifactService(
        artifact_root=tmp_path / "legacy",
        indexed_artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    adapter = IndexedBacktestReportArtifactAdapter(
        artifact_service=service,
        artifact_index_reader=reader,
    )
    candidates = {candidate.candidate_id: candidate for candidate in launch.candidates}
    for fold in reader.list_folds(launch.experiment_id):
        if fold.spec.fold_role is not FoldRole.WALK_FORWARD:
            continue
        attempts = reader.list_attempts(fold.spec.key)
        assert len(attempts) == 1
        attempt = attempts[0]
        candidate = candidates[fold.spec.key.candidate_id]
        navs = _REPORT_NAVS[(candidate.is_baseline, fold.spec.ordinal)]
        adapter.publish(
            _report_identity(fold, attempt),
            BacktestReportEvidence.from_report(
                _backtest_report(attempt, fold, navs),
            ),
            lease_fence=lease.fence,
            now_epoch_us=NOW_US + 8,
        )
    projection = writer.advance_experiment_stage(
        launch.experiment_id,
        target_stage=ExperimentStage.CANDIDATE_SELECTION,
        expected_revision=3,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 9,
        occurred_at=NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "walk_forward"},
    )
    assert projection.revision == 4
    return (
        WalkForwardEvidenceAssembler(
            report_reader=adapter,
            semantics_resolver=resolver,
        ),
        service,
    )


def _store(
    tmp_path: Path,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
    ExperimentLaunchSpec,
    WalkForwardEvidenceAssembler,
    ResearchArtifactService,
]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=golden_support.PlanningCertificationProbe(),
        executor_probe=golden_support.PlanningExecutorProbe(),
        authority_probe=golden_support.PlanningAuthorityProbe(),
    )
    request = golden_support.build_planning_request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    assert report.eligible_month_count == 96
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    launch = reader.get_launch_spec(ExperimentId(request.experiment_id))
    assert launch is not None
    resolver = golden_support.build_baseline_semantics_resolver(
        launch,
        reader.list_folds(launch.experiment_id),
    )
    lease = _advance_to_candidate_selection(reader, writer, launch, resolver)
    assembler, artifact_service = _publish_walk_forward_reports(
        tmp_path,
        database,
        reader,
        writer,
        launch,
        lease,
        resolver,
    )
    return database, reader, writer, launch, assembler, artifact_service


class _Factory:
    def __init__(self, fingerprint: str = "4" * 64) -> None:
        self.fingerprint = fingerprint

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        attempt_id = AttemptId(f"attempt-{fold.spec.key.candidate_id}")
        return FirstAttempt(
            AttemptPersistenceSpec(
                attempt_id,
                fold.spec.key,
                1,
                None,
                None,
                ContentHash(self.fingerprint),
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

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt:
        ordinal = parent.spec.ordinal + 1
        attempt_id = AttemptId(f"attempt-{fold.spec.key.candidate_id}-retry-{ordinal}")
        return QueuedAttempt(
            AttemptPersistenceSpec(
                attempt_id,
                fold.spec.key,
                ordinal,
                parent.spec.attempt_id,
                resume_from_run_id,
                parent.spec.reproduction_fingerprint,
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


def _application_request(
    launch: ExperimentLaunchSpec,
    ledger: TrialLedger,
    *,
    expected_revision: int = 4,
    occurred_at: datetime = NOW,
) -> ClaimHoldoutCandidateRequest:
    selected = next(
        candidate for candidate in launch.candidates if not candidate.is_baseline
    )
    return ClaimHoldoutCandidateRequest(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(selected.candidate_id),
        expected_revision=expected_revision,
        expected_selection_evidence_hash=str(ledger.content_hash),
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=ApplicationSelectionReason(
            "objective_review",
            "Candidate won the registered objective review.",
        ),
        occurred_at=occurred_at,
    )


def _coordinator_with_collector(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    assembler: WalkForwardEvidenceAssembler,
    artifact_service: ResearchArtifactService,
) -> tuple[
    ExperimentExecutionCoordinator,
    ExperimentSchedulerStore,
    ExperimentEvidenceCollector,
    PublishedSelectionEvidence,
]:
    """Construct a coordinator that has a real evidence collector wired in.

    The first tick is asserted to land at ``CANDIDATE_SELECTION``: the collector
    is only reachable once the scheduler drives the experiment forward to the
    EVIDENCE stage, so it must not affect earlier ticks.
    """
    store = ExperimentSchedulerStore(reader, writer)
    selection_service = DurableSelectionEvidenceService(
        scheduler_store=store,
        reader=reader,
        artifact_service=artifact_service,
        walk_forward_assembler=assembler,
    )
    collector = ExperimentEvidenceCollector(
        scheduler_store=store,
        reader=reader,
        writer=writer,
        walk_forward_assembler=assembler,
        selection_evidence_reader=selection_service,
    )
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_Factory(),
        selection_evidence_provider=selection_service,
        owner_token="r3-evidence-closure-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
        evidence_collector=collector,
        selection_evidence_publisher=selection_service,
    )
    assert (
        coordinator.tick(occurred_at=NOW).state
        is SchedulerTickState.CANDIDATE_SELECTION
    )
    selection_record = reader.get_artifact_by_relative_path(
        f"experiments/{launch.experiment_id}/selection-evidence.json"
    )
    assert selection_record is not None
    published = selection_service.read_selection_evidence(
        launch.experiment_id,
        selection_record.content_hash,
    )
    return coordinator, store, collector, published


def _assert_durable_selection_replay(
    *,
    database: ResearchExperimentDatabase,
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    assembler: WalkForwardEvidenceAssembler,
    artifact_service: ResearchArtifactService,
    coordinator: ExperimentExecutionCoordinator,
    selection: PublishedSelectionEvidence,
) -> None:
    assert (
        database.get_connection()
        .execute(
            "SELECT COUNT(*) FROM research_artifact "
            "WHERE artifact_kind='selection_evidence'"
        )
        .fetchone()[0]
        == 1
    )
    selection_events = tuple(
        event
        for event in reader.list_status_events(launch.experiment_id)
        if (
            event.reason_code == "scheduler_stage_complete"
            and event.stage is ExperimentStage.CANDIDATE_SELECTION
            and event.detail == {"completed_stage": "walk_forward"}
        )
    )
    assert len(selection_events) == 1
    selection_event = selection_events[0]
    assert selection.record.created_at == selection_event.occurred_at
    selection_audit = selection.record.manifest["audit"]
    assert isinstance(selection_audit, dict)
    assert selection_audit["selection_stage_event_id"] == selection_event.event_id
    assert (
        selection_audit["selection_stage_subject_revision"]
        == selection_event.subject_revision
    )
    assert (
        selection_audit["declared_trial_count"] == selection.ledger.declared_trial_count
    )
    assert (
        selection_audit["observed_trial_count"] == selection.ledger.observed_trial_count
    )

    selection_bytes = artifact_service.read_indexed_artifact_bytes(
        selection.record.artifact_id
    )
    pause = coordinator.pause(
        experiment_id=str(launch.experiment_id),
        expected_revision=selection_event.subject_revision,
        occurred_at=NOW + timedelta(seconds=10),
    )
    paused_tick = coordinator.tick(occurred_at=NOW + timedelta(seconds=11))
    paused = reader.get_experiment_projection(launch.experiment_id)
    assert paused is not None
    assert pause.status == ExperimentStatus.PAUSE_REQUESTED.value
    assert paused_tick.state is SchedulerTickState.WAITING
    assert paused.record.status is ExperimentStatus.PAUSED
    resume = coordinator.resume(
        experiment_id=str(launch.experiment_id),
        expected_revision=paused.revision,
        occurred_at=NOW + timedelta(seconds=20),
    )
    assert resume.status == ExperimentStatus.QUEUED.value
    assert (
        coordinator.tick(occurred_at=NOW + timedelta(seconds=30)).state
        is SchedulerTickState.CANDIDATE_SELECTION
    )
    restarted = DurableSelectionEvidenceService(
        scheduler_store=ExperimentSchedulerStore(reader, writer),
        reader=reader,
        artifact_service=artifact_service,
        walk_forward_assembler=assembler,
    )
    replayed = restarted.read_selection_evidence(
        launch.experiment_id,
        selection.record.content_hash,
    )
    assert replayed == selection
    assert (
        artifact_service.read_indexed_artifact_bytes(selection.record.artifact_id)
        == selection_bytes
    )
    assert (
        database.get_connection()
        .execute(
            "SELECT COUNT(*) FROM research_artifact "
            "WHERE artifact_kind='selection_evidence'"
        )
        .fetchone()[0]
        == 1
    )


def test_r3_evidence_closure_drives_review_packet_and_completed_status(
    tmp_path: Path,
) -> None:
    """Drive one experiment tick from EVIDENCE to a published packet + COMPLETED."""
    database, reader, writer, launch, assembler, artifact_service = _store(tmp_path)
    coordinator, store, _collector, selection = _coordinator_with_collector(
        reader,
        writer,
        launch,
        assembler,
        artifact_service,
    )
    _assert_durable_selection_replay(
        database=database,
        reader=reader,
        writer=writer,
        launch=launch,
        assembler=assembler,
        artifact_service=artifact_service,
        coordinator=coordinator,
        selection=selection,
    )
    events = tuple(
        event
        for event in reader.list_status_events(launch.experiment_id)
        if event.reason_code == "preflight_passed"
    )
    assert len(events) == 1
    preflight = reconstruct_preflight_report(events[0].detail)
    assert preflight.eligible_month_count == 96
    collected = assembler.assemble(
        store.load_snapshot(launch.experiment_id),
        project_snapshot_manifest(events[0].detail),
    )
    assert len(collected.source_rows) == 4
    assert collected.missing_artifact_refs == ()
    assert (
        database.get_connection()
        .execute(
            "SELECT COUNT(*) FROM research_artifact "
            "WHERE artifact_kind='backtest_report_evidence'"
        )
        .fetchone()[0]
        == 4
    )
    topology_by_candidate = {
        candidate.candidate_id: tuple(
            (row.fold_ordinal, row.fold_id)
            for row in collected.source_rows
            if row.candidate_id == candidate.candidate_id
        )
        for candidate in launch.candidates
    }
    assert all(len(topology) == 2 for topology in topology_by_candidate.values())
    assert len(set(topology_by_candidate.values())) == 1
    selected = next(
        candidate for candidate in launch.candidates if not candidate.is_baseline
    )
    selected_evidence = next(
        candidate
        for candidate in collected.aggregation.candidates
        if candidate.candidate_id == selected.candidate_id
    )
    selected_rows = tuple(
        row
        for row in collected.source_rows
        if row.candidate_id == selected.candidate_id
    )
    assert len(selected_rows) == 2
    expected_fold_ids = tuple(str(row.fold_id) for row in selected_rows)
    expected_attempt_ids = tuple(str(row.attempt_id) for row in selected_rows)

    # Holdout claim moves the experiment into HOLDOUT stage under the selected
    # candidate; the subsequent tick dispatches the one QUEUED holdout fold.
    selection_projection = store.load_snapshot(launch.experiment_id).projection
    coordinator.claim_holdout_candidate(
        _application_request(
            launch,
            selection.ledger,
            expected_revision=selection_projection.revision,
            occurred_at=NOW + timedelta(seconds=40),
        ),
    )
    dispatch = coordinator.tick(occurred_at=NOW + timedelta(seconds=41)).dispatches[0]
    coordinator.start_attempt(dispatch, occurred_at=NOW + timedelta(seconds=42))
    coordinator.complete_attempt(
        dispatch.attempt.spec.attempt_id,
        occurred_at=NOW + timedelta(seconds=43),
    )

    # The next tick drives the HOLDOUT fold completion -> stage advance to
    # EVIDENCE -> collector.publish_review_packet -> transition to COMPLETED.
    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=44))

    # Reload the persisted snapshot for stage/status assertions.
    refreshed = store.load_snapshot(launch.experiment_id)

    # Locate the persisted packet by querying the artifact index. The publish
    # path writes one row into ``research_artifact`` keyed by ``bundle_hash``;
    # the reader can then reload the immutable payload via ``get_review_packet``.
    row = (
        database.get_connection()
        .execute(
            "SELECT reproduction_fingerprint FROM research_artifact "
            "WHERE artifact_kind='review_packet'"
        )
        .fetchone()
    )
    assert row is not None
    bundle_hash = row["reproduction_fingerprint"]
    persisted_packet = reader.get_review_packet(bundle_hash)

    assert result.state is SchedulerTickState.COMPLETED
    assert refreshed.projection.record.status is ExperimentStatus.COMPLETED
    assert refreshed.projection.record.stage is ExperimentStage.EVIDENCE

    assert persisted_packet is not None
    assert str(persisted_packet.bundle_hash) == bundle_hash
    _assert_packet_shape(
        persisted_packet,
        launch,
        expected_comparison_hash=selected_evidence.content_hash,
        expected_fold_ids=expected_fold_ids,
        expected_attempt_ids=expected_attempt_ids,
        expected_selection_artifact_id=selection.record.artifact_id,
        expected_trial_count=selection.ledger.observed_trial_count,
        expected_declared_trial_count=selection.ledger.declared_trial_count,
    )

    database.close_all()


def _assert_packet_shape(
    packet: ReviewPacket,
    launch: ExperimentLaunchSpec,
    *,
    expected_comparison_hash: ContentHash,
    expected_fold_ids: tuple[str, ...],
    expected_attempt_ids: tuple[str, ...],
    expected_selection_artifact_id: str,
    expected_trial_count: int,
    expected_declared_trial_count: int,
) -> None:
    """Assert real metric, artifact, and lineage evidence in the frozen packet."""
    gate_by_rule = {entry.rule_id: entry for entry in packet.gate_evaluations}
    hard_gates = {
        rule_id: gate
        for rule_id, gate in gate_by_rule.items()
        if gate.layer is GateLayer.HARD
    }
    assert set(hard_gates) == set(_HARD_GATE_RULE_IDS)
    # Live R2 evidence is intentionally not inferred from this deterministic
    # tmp_path fixture. ``cost_assumptions`` retains its explicitly interim
    # projection; PASS here does not claim that later closure slice is complete.
    assert hard_gates["r2_live_gate"].outcome is GateOutcome.NOT_EVALUATED
    for rule_id, gate in hard_gates.items():
        if rule_id == "r2_live_gate":
            assert gate.outcome is GateOutcome.NOT_EVALUATED
        else:
            assert gate.outcome is GateOutcome.PASS
    assert hard_gates["artifact_completeness"].outcome is GateOutcome.PASS
    assert hard_gates["cost_assumptions"].outcome is GateOutcome.PASS
    assert hard_gates["trial_declaration"].outcome is GateOutcome.PASS
    assert hard_gates["trial_declaration"].observed == {
        "trial_count": expected_trial_count,
        "expected": expected_declared_trial_count,
    }

    selected = next(
        candidate for candidate in launch.candidates if not candidate.is_baseline
    )
    assert packet.lineage.experiment_id == str(launch.experiment_id)
    assert packet.lineage.candidate_id == str(selected.candidate_id)
    assert packet.lineage.fold_ids == expected_fold_ids
    assert packet.lineage.attempt_ids == expected_attempt_ids
    assert len(set(packet.lineage.fold_ids)) == 2
    assert len(set(packet.lineage.attempt_ids)) == 2

    primary = gate_by_rule["primary_objective_metric"]
    sharpe = gate_by_rule[f"objective_constraint:{ResearchMetricId.SHARPE_RATIO.value}"]
    assert primary.layer is GateLayer.EVIDENCE
    assert primary.outcome is GateOutcome.PASS
    assert primary.observed == pytest.approx(17.6)
    assert sharpe.layer is GateLayer.EVIDENCE
    assert sharpe.outcome is not GateOutcome.NOT_EVALUATED
    assert sharpe.observed is not None

    assert packet.comparison_payload_hash == expected_comparison_hash
    assert packet.r1_impact_payload_hash is None
    assert packet.selection_evidence_artifact_id == expected_selection_artifact_id
    assert packet.candidate_rationale
    assert packet.candidate_rationale == packet.candidate_rationale.strip()
