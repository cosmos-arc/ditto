"""Deterministic R3 evidence-collection closure golden test.

This integration test exercises the full Task 1-4 R3 closure seam against a
fresh ``tmp_path`` SQLite research database:

* The durable :class:`ExperimentExecutionCoordinator` is constructed with a
  real :class:`ExperimentEvidenceCollector` injected (the existing holdout
  integration tests pass ``evidence_collector=None`` and so never close the
  EVIDENCE branch).
* The fixture drives one experiment tick through PREFLIGHT, EXPLORATION,
  WALK_FORWARD, CANDIDATE_SELECTION, HOLDOUT, and finally EVIDENCE.
* At EVIDENCE the coordinator must invoke the collector, which assembles the
  eleven-field hard-gate view, evaluates the eleven hard gates, freezes the
  immutable :class:`ReviewPacket`, publishes it through the durable writer
  protocol, and finally transitions the experiment to ``COMPLETED``.

V1 simplifications (accepted by the user) hold: ``metric_values={}`` leaves the
evidence gates ``NOT_EVALUATED``, ``comparison_payload_hash`` is ``None``, and
``r2_live_gate`` is pinned to ``NOT_EVALUATED``. The assertions therefore
verify closure and objective gate projection rather than full statistical
evidence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
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
    GateEvaluationRecord,
    LogicalTrialIdentity,
    ResearchCycleIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.evidence import ReviewPacket
from ditto_analysis.experiments.gates import GateLayer, GateOutcome
from ditto_analysis.experiments.preflight_authority import (
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments.trial_ledger import (
    MetricEvidenceLineage,
    ObjectiveMetric,
    PromotionObjective,
    TrialLedger,
    TrialOutcome,
    TrialStatus,
    build_trial_ledger,
)
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
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
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
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


def _candidate(ordinal: int) -> CandidateSpec:
    return CandidateSpec(
        CandidateId(f"candidate-{ordinal}"),
        ordinal,
        ordinal == 1,
        {"lookback": ordinal * 20},
    )


def _validation_plan(
    holdout_window: DateWindow,
    *,
    eligibility: str = "promotion_eligible",
) -> dict[str, object]:
    return {
        "eligibility": eligibility,
        "reason_codes": [],
        "coverage_policy": {
            "policy_id": "holdout-integration",
            "version": 1,
            "min_eligible_instrument_count": 1,
            "min_coverage_ratio_bps": 10_000,
            "evaluator_hash": "6" * 64,
        },
        "calendar_complete_month_count": 96,
        "eligible_months": [],
        "isolation_width_sessions": 3,
        "folds": [
            {
                "ordinal": 1,
                "role": "exploration",
                "train_window": None,
                "test_window": {"start": "2026-01-01", "end": "2026-01-28"},
                "purge_sessions": 2,
                "embargo_sessions": 1,
            },
            {
                "ordinal": 2,
                "role": "walk_forward",
                "train_window": {"start": "2020-01-01", "end": "2025-12-31"},
                "test_window": {"start": "2026-02-01", "end": "2026-02-28"},
                "purge_sessions": 2,
                "embargo_sessions": 1,
            },
        ],
        "reserved_holdout": {
            "train_window": {"start": "2020-01-01", "end": "2025-12-31"},
            "test_window": {
                "start": holdout_window.start.isoformat(),
                "end": holdout_window.end.isoformat(),
            },
            "purge_sessions": 2,
            "embargo_sessions": 1,
        },
    }


def _launch(
    experiment_id: str,
    *,
    snapshot_id: str = "snapshot-holdout-integration",
    holdout_window: DateWindow | None = None,
    eligibility: str = "promotion_eligible",
) -> ExperimentLaunchSpec:
    actual_holdout = holdout_window or DateWindow(date(2026, 3, 1), date(2026, 3, 28))
    candidates = (_candidate(1), _candidate(2))
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId(experiment_id),
        strategy_version=StrategyVersion("strategy@1"),
        strategy_spec_hash=ContentHash("1" * 64),
        snapshot_id=SnapshotId(snapshot_id),
        candidates=candidates,
        execution_bindings=tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(f"{candidate.ordinal + 32:064x}"),
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
            "Choose a candidate only after registered evidence review.",
            TrialFamilyDeclaration(
                "holdout-integration-family",
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
        fold_protocol=FoldProtocolSpec(
            "holdout-v1",
            1,
            canonical_payload(
                _validation_plan(actual_holdout, eligibility=eligibility)
            ).content_hash,
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _folds(
    launch: ExperimentLaunchSpec,
    *,
    holdout_window: DateWindow | None = None,
) -> tuple[FoldPersistenceSpec, ...]:
    actual_holdout = holdout_window or DateWindow(date(2026, 3, 1), date(2026, 3, 28))

    def fold_spec(
        candidate: CandidateSpec,
        ordinal: int,
        role: FoldRole,
    ) -> FoldPersistenceSpec:
        key = FoldKey(
            launch.experiment_id,
            candidate.candidate_id,
            FoldId(f"fold-{candidate.ordinal}-{ordinal}"),
        )
        return FoldPersistenceSpec.create(
            key,
            ordinal,
            role,
            None
            if role is FoldRole.EXPLORATION
            else DateWindow(date(2020, 1, 1), date(2025, 12, 31)),
            (
                actual_holdout
                if role is FoldRole.HOLDOUT
                else DateWindow(date(2026, ordinal, 1), date(2026, ordinal, 28))
            ),
            2,
            1,
        )

    return tuple(
        fold_spec(candidate, ordinal, role)
        for candidate in launch.candidates
        for ordinal, role in (
            (1, FoldRole.EXPLORATION),
            (2, FoldRole.WALK_FORWARD),
        )
    ) + tuple(
        fold_spec(candidate, 3, FoldRole.HOLDOUT) for candidate in launch.candidates
    )


def _snapshot_evidence(
    launch: ExperimentLaunchSpec,
    manifest_hash: str,
    certified_cutoff: date,
) -> dict[str, object]:
    return {
        "snapshot_id": str(launch.snapshot_id),
        "dataset_id": "holdout-integration-dataset",
        "manifest_hash": manifest_hash,
        "source_snapshot_ids": ["provider-snapshot-holdout-integration"],
        "snapshot_start": "2020-01-01",
        "snapshot_end": certified_cutoff.isoformat(),
        "known_at_policy": "sample_time",
        "builder_version": "holdout-integration-builder-v1",
    }


def _gates(
    launch: ExperimentLaunchSpec,
    *,
    snapshot_manifest_hash: str,
    certified_cutoff: date,
    holdout_window: DateWindow,
) -> tuple[GateEvaluationRecord, ...]:
    snapshot = _snapshot_evidence(launch, snapshot_manifest_hash, certified_cutoff)
    certification_observed = {
        "ready": True,
        "profile": "r3-a-share-certified-research-v1",
        "dataset_ids": ["holdout-integration-dataset"],
        "report_ids": ["holdout-integration-certification"],
        "reason_codes": [],
        "snapshot_evidence": snapshot,
        "snapshot_evidence_valid": True,
    }
    certification_policy = {
        "profile": "r3-a-share-certified-research-v1",
        "required_from": "2020-01-01",
        "required_to": holdout_window.end.isoformat(),
        "requirements": [],
        "snapshot_identity": {
            "snapshot_id": str(launch.snapshot_id),
            "manifest_hash": snapshot_manifest_hash,
        },
    }
    return tuple(
        GateEvaluationRecord(
            evaluation_id=f"{launch.experiment_id}:preflight:{index}:{rule_id}",
            experiment_id=launch.experiment_id,
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            rule_id=rule_id,
            policy_version=_PREFLIGHT_POLICY_VERSION,
            layer="hard",
            outcome="pass",
            observed=certification_observed if rule_id == "certification" else {},
            policy=certification_policy if rule_id == "certification" else {},
            artifact_id=None,
            evaluated_at=NOW,
        )
        for index, rule_id in enumerate(_GATE_RULES, start=1)
    )


def _preflight_detail(
    *,
    launch: ExperimentLaunchSpec,
    cycle: ResearchCycleIdentity,
    folds: tuple[FoldPersistenceSpec, ...],
    gates: tuple[GateEvaluationRecord, ...],
    snapshot_manifest_hash: str,
    certified_cutoff: date,
    holdout_window: DateWindow,
    status: str,
    eligibility: str,
) -> dict[str, object]:
    snapshot = _snapshot_evidence(launch, snapshot_manifest_hash, certified_cutoff)
    validation_plan = _validation_plan(holdout_window, eligibility=eligibility)
    checks = [
        {
            "rule_id": gate.rule_id,
            "outcome": gate.outcome,
            "code": None,
            "reason": None,
            "remediation": None,
            "observed": gate.observed,
            "policy": gate.policy,
        }
        for gate in gates
    ]
    executor = {
        "node_registry_manifest_hash": "7" * 64,
        "factor_registry_manifest_hash": "8" * 64,
        "factor_binding_hashes": [],
        "baseline_ref": "baseline://holdout-integration",
        "baseline_descriptor_hash": "9" * 64,
        "baseline_registry_manifest_hash": "a" * 64,
        "baseline_exact_strategy_hash": None,
        "baseline_runtime": None,
        "candidates": [],
    }
    authority = {
        "payload_hash": "b" * 64,
        "runtime_evidence_hash": "c" * 64,
        "universe_membership_hash": "d" * 64,
        "membership_projection_hash": "e" * 64,
        "requires_pit_universe": True,
        "dataset_bindings": [],
        "snapshot_identity": {
            "snapshot_id": str(launch.snapshot_id),
            "manifest_hash": snapshot_manifest_hash,
        },
    }
    certification = {
        "ready": status in {"ready", "research_only"},
        "profile": "r3-a-share-certified-research-v1",
        "required_from": "2020-01-01",
        "required_to": holdout_window.end.isoformat(),
        "dataset_ids": ["holdout-integration-dataset"],
        "report_ids": ["holdout-integration-certification"],
        "reason_codes": [],
        "snapshot_evidence": snapshot,
    }
    preflight = {
        "schema_version": 1,
        "policy_version": _PREFLIGHT_POLICY_VERSION,
        "status": status,
        "checks": checks,
        "counts": {
            "candidate_count": len(launch.candidates),
            "planned_fold_count": len(folds),
            "budget_run_count": len(folds),
            "estimated_trading_sessions": 1,
            "estimated_disk_bytes": 1,
            "eligible_month_count": 96,
            "isolation_width_sessions": 3,
        },
        "validation": {
            "protocol": {},
            "plan": validation_plan,
            "fold_protocol": {
                "protocol_id": launch.fold_protocol.protocol_id,
                "protocol_version": launch.fold_protocol.protocol_version,
                "protocol_hash": str(launch.fold_protocol.protocol_hash),
            },
        },
        "work": {"plan_hash": "f" * 64},
        "executor": executor,
        "authority": authority,
        "identities": {
            "request_hash": "1" * 64,
            "research_cycle_id": cycle.cycle_id,
            "research_cycle_hash": str(cycle.cycle_hash),
            "strategy_id": "strategy",
            "strategy_version": 1,
            "snapshot_identity": authority["snapshot_identity"],
            "dataset_requirements": [],
            "certification": certification,
        },
    }
    preflight_hash = canonical_payload(preflight).content_hash
    plan_preimage = {
        "schema_version": 1,
        "launch_spec_hash": str(encode_launch_spec(launch).content_hash),
        "gate_payload_hashes": [str(gate.payload_hash) for gate in gates],
        "fold_payload_hashes": [str(fold.payload_hash) for fold in folds],
        "research_cycle_id": cycle.cycle_id,
        "research_cycle_hash": str(cycle.cycle_hash),
        "request_hash": "1" * 64,
        "snapshot_evidence": snapshot,
        "dataset_requirements": [],
        "validation": validation_plan,
        "validation_authority": {
            key: authority[key]
            for key in (
                "payload_hash",
                "runtime_evidence_hash",
                "universe_membership_hash",
                "membership_projection_hash",
                "requires_pit_universe",
                "dataset_bindings",
            )
        },
        "work_plan_hash": "f" * 64,
        "node_registry_manifest_hash": executor["node_registry_manifest_hash"],
        "factor_registry_manifest_hash": executor["factor_registry_manifest_hash"],
        "factor_binding_hashes": executor["factor_binding_hashes"],
        "baseline_ref": executor["baseline_ref"],
        "baseline_descriptor_hash": executor["baseline_descriptor_hash"],
        "baseline_registry_manifest_hash": executor["baseline_registry_manifest_hash"],
        "baseline_exact_strategy_hash": executor["baseline_exact_strategy_hash"],
        "baseline_runtime": executor["baseline_runtime"],
        "executor_candidates": executor["candidates"],
        "certification": {
            key: certification[key]
            for key in (
                "profile",
                "required_from",
                "required_to",
                "report_ids",
                "reason_codes",
            )
        },
        "preflight_hash": str(preflight_hash),
    }
    plan_hash = canonical_payload(plan_preimage).content_hash
    return {
        "plan_hash": str(plan_hash),
        "plan_preimage": plan_preimage,
        "preflight": preflight,
        "preflight_hash": str(preflight_hash),
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
        f"attempt-complete-{view.spec.key.experiment_id}-{view.spec.key.fold_id}"
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


def _persist_candidate_selection(
    writer: SQLiteExperimentWriter,
    database: ResearchExperimentDatabase,
    *,
    experiment_id: str = "experiment-1",
    cycle_id: str = "cycle-shared",
    snapshot_id: str = "snapshot-holdout-integration",
    snapshot_manifest_hash: str = "5" * 64,
    certified_cutoff: date | None = None,
    holdout_window: DateWindow | None = None,
    preflight_status: str | None = "ready",
    preflight_eligibility: str | None = None,
) -> tuple[ExperimentLaunchSpec, Any]:
    actual_holdout = holdout_window or DateWindow(date(2026, 3, 1), date(2026, 3, 28))
    actual_cutoff = certified_cutoff or actual_holdout.end
    actual_eligibility = preflight_eligibility or (
        "research_only" if preflight_status == "research_only" else "promotion_eligible"
    )
    launch = _launch(
        experiment_id,
        snapshot_id=snapshot_id,
        holdout_window=actual_holdout,
        eligibility=actual_eligibility,
    )
    derived_cycle_hash = canonical_research_cycle_hash(
        strategy_family_id="strategy",
        certified_data_cutoff=actual_cutoff,
        oos_window=actual_holdout,
    )
    cycle = ResearchCycleIdentity(cycle_id, derived_cycle_hash)
    writer.create_experiment(
        cycle,
        launch,
        ExperimentRecord(
            launch.experiment_id,
            ExperimentStatus.DRAFT,
            ExperimentDesiredState.RUN,
            ExperimentStage.PREFLIGHT,
            NOW,
        ),
    )
    folds = _folds(launch, holdout_window=actual_holdout)
    gates = _gates(
        launch,
        snapshot_manifest_hash=snapshot_manifest_hash,
        certified_cutoff=actual_cutoff,
        holdout_window=actual_holdout,
    )
    for gate in gates:
        writer.add_gate_evaluation(gate)
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
        detail=(
            {}
            if preflight_status is None
            else _preflight_detail(
                launch=launch,
                cycle=cycle,
                folds=folds,
                gates=gates,
                snapshot_manifest_hash=snapshot_manifest_hash,
                certified_cutoff=actual_cutoff,
                holdout_window=actual_holdout,
                status=preflight_status,
                eligibility=actual_eligibility,
            )
        ),
        launch_fence=ExperimentEnqueueFence.create(gates=gates, folds=folds),
    )
    slot = writer._reader.get_scheduler_slot()
    lease = writer.try_claim_lease(
        launch.experiment_id,
        f"owner-{experiment_id}",
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
    for fold in folds:
        if fold.fold_role is FoldRole.EXPLORATION:
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
    for fold in folds:
        if fold.fold_role is FoldRole.WALK_FORWARD:
            _complete_fold(writer, fold, lease)
    projection = writer.advance_experiment_stage(
        launch.experiment_id,
        target_stage=ExperimentStage.CANDIDATE_SELECTION,
        expected_revision=3,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "walk_forward"},
    )
    assert projection.revision == 4
    return launch, lease


def _store(
    tmp_path: Path,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
    ExperimentLaunchSpec,
    Any,
]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    launch, lease = _persist_candidate_selection(writer, database)
    assert lease is not None
    return database, reader, writer, launch, lease


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
                    )
                },
                holdout_metrics={},
                source_projection_hash=ContentHash("7" * 64),
                metric_evidence={ResearchMetricId.NET_RETURN: lineage},
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


def _application_request(ledger: TrialLedger) -> ClaimHoldoutCandidateRequest:
    return ClaimHoldoutCandidateRequest(
        experiment_id="experiment-1",
        candidate_id="candidate-2",
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
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, store, _collector, provider = _coordinator_with_collector(
        reader, writer, launch
    )

    # Holdout claim moves the experiment into HOLDOUT stage under the selected
    # candidate; the subsequent tick dispatches the one QUEUED holdout fold.
    coordinator.claim_holdout_candidate(_application_request(provider.ledger))
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
    _assert_packet_shape(persisted_packet, launch)

    database.close_all()


def _assert_packet_shape(packet: ReviewPacket, launch: ExperimentLaunchSpec) -> None:
    """Assert the V1 hard-gate and lineage shape projected from the fixture."""
    gate_by_rule = {entry.rule_id: entry for entry in packet.gate_evaluations}
    # Eleven hard gates (objective evidence gates are NOT_EVALUATED in V1
    # because metric_values is empty; they ride on the same tuple but are
    # layered under GateLayer.EVIDENCE rather than GateLayer.HARD).
    hard_gates = {
        rule_id: gate
        for rule_id, gate in gate_by_rule.items()
        if gate.layer is GateLayer.HARD
    }
    assert set(hard_gates) == set(_HARD_GATE_RULE_IDS)
    # r2_live_gate is pinned to NOT_EVALUATED (V1: no live evidence wiring).
    assert hard_gates["r2_live_gate"].outcome is GateOutcome.NOT_EVALUATED
    # Every hard gate must carry an explicit satisfied translation: PASS or
    # FAIL for the ten objective gates, NOT_EVALUATED only for r2_live_gate.
    for rule_id, gate in hard_gates.items():
        if rule_id == "r2_live_gate":
            assert gate.outcome is GateOutcome.NOT_EVALUATED
        else:
            assert gate.outcome in {GateOutcome.PASS, GateOutcome.FAIL}

    # Lineage must carry the experiment, the selected candidate, and non-empty
    # fold/attempt identity tuples.
    assert packet.lineage.experiment_id == str(launch.experiment_id)
    assert packet.lineage.candidate_id == "candidate-2"
    assert packet.lineage.fold_ids
    assert packet.lineage.attempt_ids

    # V1 placeholders hold as designed (Task 3b will replace them).
    assert packet.comparison_payload_hash is None
    assert packet.r1_impact_payload_hash is None
    assert packet.selection_evidence_artifact_id is None
    assert packet.candidate_rationale
    assert packet.candidate_rationale == packet.candidate_rationale.strip()
