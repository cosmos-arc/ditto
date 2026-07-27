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
    ResearchMetricValue,
)
from ditto_analysis.experiments.evidence import ReviewPacket
from ditto_analysis.experiments.gates import GateLayer, GateOutcome
from ditto_analysis.experiments.trial_ledger import (
    MetricEvidenceLineage,
    TrialLedger,
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
) -> WalkForwardEvidenceAssembler:
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
    return WalkForwardEvidenceAssembler(
        report_reader=adapter,
        semantics_resolver=resolver,
    )


def _store(
    tmp_path: Path,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
    ExperimentLaunchSpec,
    WalkForwardEvidenceAssembler,
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
    assembler = _publish_walk_forward_reports(
        tmp_path,
        database,
        reader,
        writer,
        launch,
        lease,
        resolver,
    )
    return database, reader, writer, launch, assembler


def _selection_ledger(launch: ExperimentLaunchSpec) -> TrialLedger:
    lineage = MetricEvidenceLineage(
        ("comparison://holdout-integration",),
        (ContentHash("6" * 64),),
    )
    outcomes = []
    for candidate in launch.candidates:
        trial = launch.promotion_objective.trial_family.current_members[
            candidate.ordinal - 1
        ]
        outcomes.append(
            TrialOutcome(
                trial=trial,
                status=TrialStatus.COMPLETED,
                metrics={
                    ResearchMetricId.NET_RETURN: ResearchMetricValue(
                        ResearchMetricId.NET_RETURN,
                        float(candidate.ordinal),
                    ),
                    ResearchMetricId.SHARPE_RATIO: ResearchMetricValue(
                        ResearchMetricId.SHARPE_RATIO,
                        float(candidate.ordinal),
                    ),
                    ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
                        ResearchMetricId.MAX_DRAWDOWN,
                        -float(candidate.ordinal),
                    ),
                },
                holdout_metrics={},
                source_projection_hash=ContentHash("7" * 64),
                metric_evidence={
                    ResearchMetricId.NET_RETURN: lineage,
                    ResearchMetricId.SHARPE_RATIO: lineage,
                    ResearchMetricId.MAX_DRAWDOWN: lineage,
                },
            )
        )
    return build_trial_ledger(launch.promotion_objective, tuple(outcomes))


class _SelectionProvider:
    def __init__(self, launch: ExperimentLaunchSpec) -> None:
        self.ledger = _selection_ledger(launch)

    def load_selection_evidence(self, _experiment_id: ExperimentId) -> TrialLedger:
        return self.ledger


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
) -> ClaimHoldoutCandidateRequest:
    selected = next(
        candidate for candidate in launch.candidates if not candidate.is_baseline
    )
    return ClaimHoldoutCandidateRequest(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(selected.candidate_id),
        expected_revision=4,
        expected_selection_evidence_hash=str(ledger.content_hash),
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=ApplicationSelectionReason(
            "objective_review",
            "Candidate won the registered objective review.",
        ),
        occurred_at=NOW,
    )


def _coordinator_with_collector(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    assembler: WalkForwardEvidenceAssembler,
) -> tuple[
    ExperimentExecutionCoordinator,
    ExperimentSchedulerStore,
    ExperimentEvidenceCollector,
    _SelectionProvider,
]:
    """Construct a coordinator that has a real evidence collector wired in.

    The first tick is asserted to land at ``CANDIDATE_SELECTION``: the collector
    is only reachable once the scheduler drives the experiment forward to the
    EVIDENCE stage, so it must not affect earlier ticks.
    """
    store = ExperimentSchedulerStore(reader, writer)
    provider = _SelectionProvider(launch)
    collector = ExperimentEvidenceCollector(
        scheduler_store=store,
        reader=reader,
        writer=writer,
        walk_forward_assembler=assembler,
    )
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_Factory(),
        selection_evidence_provider=provider,
        owner_token="r3-evidence-closure-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
        evidence_collector=collector,
    )
    assert (
        coordinator.tick(occurred_at=NOW).state
        is SchedulerTickState.CANDIDATE_SELECTION
    )
    return coordinator, store, collector, provider


def test_r3_evidence_closure_drives_review_packet_and_completed_status(
    tmp_path: Path,
) -> None:
    """Drive one experiment tick from EVIDENCE to a published packet + COMPLETED."""
    database, reader, writer, launch, assembler = _store(tmp_path)
    coordinator, store, _collector, provider = _coordinator_with_collector(
        reader,
        writer,
        launch,
        assembler,
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
    coordinator.claim_holdout_candidate(
        _application_request(launch, provider.ledger),
    )
    dispatch = coordinator.tick(occurred_at=NOW + timedelta(seconds=1)).dispatches[0]
    coordinator.start_attempt(dispatch, occurred_at=NOW + timedelta(seconds=2))
    coordinator.complete_attempt(
        dispatch.attempt.spec.attempt_id,
        occurred_at=NOW + timedelta(seconds=3),
    )

    # The next tick drives the HOLDOUT fold completion -> stage advance to
    # EVIDENCE -> collector.publish_review_packet -> transition to COMPLETED.
    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))

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
    )

    database.close_all()


def _assert_packet_shape(
    packet: ReviewPacket,
    launch: ExperimentLaunchSpec,
    *,
    expected_comparison_hash: ContentHash,
    expected_fold_ids: tuple[str, ...],
    expected_attempt_ids: tuple[str, ...],
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
    # tmp_path fixture. ``cost_assumptions`` and ``trial_declaration`` retain
    # their explicitly interim C2b projections; PASS here does not claim those
    # later closure slices are complete.
    assert hard_gates["r2_live_gate"].outcome is GateOutcome.NOT_EVALUATED
    for rule_id, gate in hard_gates.items():
        if rule_id == "r2_live_gate":
            assert gate.outcome is GateOutcome.NOT_EVALUATED
        else:
            assert gate.outcome is GateOutcome.PASS
    assert hard_gates["artifact_completeness"].outcome is GateOutcome.PASS
    assert hard_gates["cost_assumptions"].outcome is GateOutcome.PASS
    assert hard_gates["trial_declaration"].outcome is GateOutcome.PASS

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
    assert packet.selection_evidence_artifact_id is None
    assert packet.candidate_rationale
    assert packet.candidate_rationale == packet.candidate_rationale.strip()
