"""R3 research/governance combined backup and restore acceptance."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import orjson
import pytest
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
    ContentHash,
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
    SchedulerLease,
    SnapshotId,
    TrialFamilyDeclaration,
    TrialKind,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments import (
    StrategyVersion as ResearchStrategyVersion,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_analysis.experiments.gates import GateEvaluation, GateLayer, GateOutcome
from ditto_analysis.experiments.persistence import (
    DateWindow,
    HoldoutClaimRecord,
    LeaseFence,
)
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
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.processes.experiments._selection_evidence_artifact import (
    PublishedSelectionEvidence,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
)
from ditto_application.processes.experiments.holdout import (
    HoldoutSelectionReason as ApplicationHoldoutSelectionReason,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
)
from ditto_apps.scripts.r3_research_backup import (
    R3ResearchBackupError,
    create_r3_research_backup,
    inspect_r3_research_sources,
    restore_r3_research_backup,
    verify_r3_research_backup,
    verify_restored_r3_research_backup,
)
from ditto_apps.scripts.r3_research_backup import (
    main as backup_main,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    StrategyActivePointer,
    StrategyVersion,
)
from ditto_strategy.governance.service import (
    GovernanceService,
    PublishReviewedActivationRequest,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)

NOW = datetime(2026, 7, 28, 4, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)
RESEARCH_USER_VERSION = 2
RESEARCH_SCHEMA_ROW_COUNT = 95
RESEARCH_SCHEMA_FINGERPRINT = (
    "7b4a6d03f4ba879ca54fd47220b7d28728bcb58c87cdca3cdfe27a5466cd51e0"
)
EXPERIMENT_ID = ExperimentId("r3-backup-experiment")
HOLDOUT_WINDOW = DateWindow(date(2026, 3, 1), date(2026, 3, 31))
RESEARCH_CYCLE = ResearchCycleIdentity(
    "cycle-r3-backup",
    canonical_research_cycle_hash(
        strategy_family_id="stock-selection",
        certified_data_cutoff=HOLDOUT_WINDOW.end,
        oos_window=HOLDOUT_WINDOW,
    ),
)
CLAIM_ID = "holdout:" + str(
    canonical_payload(
        {
            "schema_version": 1,
            "research_cycle_id": RESEARCH_CYCLE.cycle_id,
            "research_cycle_hash": str(RESEARCH_CYCLE.cycle_hash),
        }
    ).content_hash
)


def _validation_plan() -> dict[str, object]:
    return {
        "eligibility": "promotion_eligible",
        "reason_codes": [],
        "coverage_policy": {
            "policy_id": "r3-backup",
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
                "test_window": {"start": "2026-01-01", "end": "2026-01-31"},
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
                "start": HOLDOUT_WINDOW.start.isoformat(),
                "end": HOLDOUT_WINDOW.end.isoformat(),
            },
            "purge_sessions": 2,
            "embargo_sessions": 1,
        },
    }


def _launch() -> ExperimentLaunchSpec:
    candidate = CandidateSpec(
        candidate_id=CandidateId("candidate-1"),
        ordinal=1,
        is_baseline=True,
        parameters={"lookback": 20},
    )
    return ExperimentLaunchSpec(
        experiment_id=EXPERIMENT_ID,
        strategy_version=ResearchStrategyVersion("stock-selection@1"),
        strategy_spec_hash=ContentHash("1" * 64),
        snapshot_id=SnapshotId("snapshot-r3-backup"),
        candidates=(candidate,),
        execution_bindings=(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash("2" * 64),
            ),
        ),
        promotion_objective=PromotionObjective(
            primary=ObjectiveMetric(
                ResearchMetricId.NET_RETURN,
                ResearchMetricDirection.MAXIMIZE,
            ),
            hard_constraints=(),
            tie_break_order=(),
            baseline_candidate_id=candidate.candidate_id,
            economic_rationale="Preserve net return evidence across recovery.",
            trial_family=TrialFamilyDeclaration(
                "r3-backup-family",
                (
                    LogicalTrialIdentity(
                        EXPERIMENT_ID,
                        candidate.candidate_id,
                        candidate.ordinal,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    ),
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec(
            protocol_id="r3-backup-holdout",
            protocol_version=1,
            protocol_hash=canonical_payload(_validation_plan()).content_hash,
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(candidate_limit=1, fold_run_limit=3),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _seed_governance(
    data_root: Path,
    *,
    sqlite_path: Path | None = None,
) -> tuple[StrategyActivePointer, tuple[tuple[object, ...], ...]]:
    metadata_database = sqlite_path or _metadata_database(data_root)
    metadata_database.parent.mkdir(parents=True, exist_ok=True)
    pool = SQLitePool(str(metadata_database))
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    service = GovernanceService(store)
    store.insert_version(
        StrategyVersion(
            strategy_id="stock-selection",
            version=1,
            parent_version=None,
            schema_version=GOVERNANCE_SCHEMA_VERSION,
            spec_hash="4" * 64,
            created_at=NOW.isoformat(),
        )
    )
    service.submit_review(
        "stock-selection",
        1,
        event_id="decision-submit",
        actor="reviewer",
        reason="ready for review",
        decided_at=NOW.isoformat(),
    )
    service.approve(
        "stock-selection",
        1,
        event_id="decision-approve",
        actor="reviewer",
        reason="evidence accepted",
        decided_at=(NOW + timedelta(seconds=1)).isoformat(),
    )
    pointer = service.publish_reviewed_and_activate(
        PublishReviewedActivationRequest(
            strategy_id="stock-selection",
            version=1,
            publish_event_id="decision-publish",
            activate_event_id="activation-publish",
            actor="publisher",
            reason="promotion gates passed",
            decided_at=(NOW + timedelta(seconds=2)).isoformat(),
        )
    )
    decisions = _decision_history(metadata_database)
    pool.close_all()
    return pointer, decisions


def _metadata_database(data_root: Path) -> Path:
    return data_root / "metadata" / "metadata.sqlite"


def _seed_holdout(
    database: ResearchExperimentDatabase,
    writer: SQLiteExperimentWriter,
) -> HoldoutClaimRecord:
    del database
    launch, _lease = _persist_candidate_selection(writer)
    provider = _SelectionEvidenceProvider(launch)
    clock_value = [NOW + timedelta(minutes=2)]

    def advancing_clock() -> datetime:
        value = clock_value[0]
        clock_value[0] = value + timedelta(microseconds=1)
        return value

    coordinator = ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(writer._reader, writer),
        first_attempt_factory=_FirstAttemptFactory(),
        owner_token="r3-backup-coordinator",
        lease_duration=timedelta(minutes=5),
        selection_evidence_provider=provider,
        selection_evidence_publisher=provider,
        clock=advancing_clock,
    )
    assert (
        coordinator.tick(occurred_at=NOW + timedelta(minutes=2)).state
        is SchedulerTickState.CANDIDATE_SELECTION
    )
    receipt = coordinator.claim_holdout_candidate(
        ClaimHoldoutCandidateRequest(
            experiment_id=str(EXPERIMENT_ID),
            candidate_id="candidate-1",
            expected_revision=4,
            expected_selection_evidence_hash=str(provider.ledger.content_hash),
            operator_confirmation="operator approved immutable selection evidence",
            selection_reason=ApplicationHoldoutSelectionReason(
                "objective_review",
                "Candidate won the registered objective review.",
            ),
            occurred_at=NOW + timedelta(minutes=2, seconds=1),
        )
    )
    claim = writer._reader.get_holdout_claim(receipt.claim_id)
    projection = writer._reader.get_experiment_projection(EXPERIMENT_ID)
    assert claim is not None
    assert projection is not None
    assert receipt.experiment_revision == 5
    assert projection.record.stage is ExperimentStage.HOLDOUT
    assert projection.revision == 5
    assert any(
        event.reason_code == "scheduler_stage_complete"
        and event.stage is ExperimentStage.CANDIDATE_SELECTION
        for event in writer._reader.list_status_events(EXPERIMENT_ID)
    )
    assert claim.claim_id == CLAIM_ID
    return claim


_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"
_GATE_RULES = ("matrix", "executor", "authority", "history", "certification", "budget")


def _folds(launch: ExperimentLaunchSpec) -> tuple[FoldPersistenceSpec, ...]:
    candidate = launch.candidates[0]
    train = DateWindow(date(2020, 1, 1), date(2025, 12, 31))
    definitions = (
        (
            1,
            FoldRole.EXPLORATION,
            None,
            DateWindow(date(2026, 1, 1), date(2026, 1, 31)),
        ),
        (
            2,
            FoldRole.WALK_FORWARD,
            train,
            DateWindow(date(2026, 2, 1), date(2026, 2, 28)),
        ),
        (3, FoldRole.HOLDOUT, train, HOLDOUT_WINDOW),
    )
    return tuple(
        FoldPersistenceSpec.create(
            key=FoldKey(
                launch.experiment_id,
                candidate.candidate_id,
                FoldId(f"fold-{role.value}"),
            ),
            ordinal=ordinal,
            fold_role=role,
            train_window=train_window,
            test_window=test_window,
            purge_sessions=2,
            embargo_sessions=1,
        )
        for ordinal, role, train_window, test_window in definitions
    )


def _snapshot_evidence(launch: ExperimentLaunchSpec) -> dict[str, object]:
    return {
        "snapshot_id": str(launch.snapshot_id),
        "dataset_id": "r3-backup-dataset",
        "manifest_hash": "5" * 64,
        "source_snapshot_ids": ["provider-snapshot-r3-backup"],
        "snapshot_start": "2020-01-01",
        "snapshot_end": HOLDOUT_WINDOW.end.isoformat(),
        "known_at_policy": "sample_time",
        "builder_version": "r3-backup-builder-v1",
    }


def _preflight_gates(
    launch: ExperimentLaunchSpec,
) -> tuple[GateEvaluationRecord, ...]:
    certification_observed = {
        "ready": True,
        "profile": "r3-a-share-certified-research-v1",
        "dataset_ids": ["r3-backup-dataset"],
        "report_ids": ["r3-backup-certification"],
        "reason_codes": [],
        "snapshot_evidence": _snapshot_evidence(launch),
        "snapshot_evidence_valid": True,
    }
    certification_policy = {
        "profile": "r3-a-share-certified-research-v1",
        "required_from": "2020-01-01",
        "required_to": HOLDOUT_WINDOW.end.isoformat(),
        "requirements": [],
        "snapshot_identity": {
            "snapshot_id": str(launch.snapshot_id),
            "manifest_hash": "5" * 64,
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
    launch: ExperimentLaunchSpec,
    folds: tuple[FoldPersistenceSpec, ...],
    gates: tuple[GateEvaluationRecord, ...],
) -> dict[str, object]:
    snapshot = _snapshot_evidence(launch)
    validation = _validation_plan()
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
        "baseline_ref": "baseline://r3-backup",
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
            "manifest_hash": "5" * 64,
        },
    }
    certification = {
        "ready": True,
        "profile": "r3-a-share-certified-research-v1",
        "required_from": "2020-01-01",
        "required_to": HOLDOUT_WINDOW.end.isoformat(),
        "dataset_ids": ["r3-backup-dataset"],
        "report_ids": ["r3-backup-certification"],
        "reason_codes": [],
        "snapshot_evidence": snapshot,
    }
    preflight = {
        "schema_version": 1,
        "policy_version": _PREFLIGHT_POLICY_VERSION,
        "status": "ready",
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
            "plan": validation,
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
            "research_cycle_id": RESEARCH_CYCLE.cycle_id,
            "research_cycle_hash": str(RESEARCH_CYCLE.cycle_hash),
            "strategy_id": "stock-selection",
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
        "research_cycle_id": RESEARCH_CYCLE.cycle_id,
        "research_cycle_hash": str(RESEARCH_CYCLE.cycle_hash),
        "request_hash": "1" * 64,
        "snapshot_evidence": snapshot,
        "dataset_requirements": [],
        "validation": validation,
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
    return {
        "plan_hash": str(canonical_payload(plan_preimage).content_hash),
        "plan_preimage": plan_preimage,
        "preflight": preflight,
        "preflight_hash": str(preflight_hash),
    }


def _complete_fold(
    writer: SQLiteExperimentWriter,
    fold: FoldView,
    lease: SchedulerLease,
) -> None:
    attempt_id = AttemptId(f"attempt-{fold.spec.key.fold_id}")
    spec = AttemptPersistenceSpec(
        attempt_id=attempt_id,
        fold_key=fold.spec.key,
        ordinal=1,
        parent_attempt_id=None,
        resume_from_run_id=None,
        reproduction_fingerprint=ContentHash("7" * 64),
        created_at=NOW,
    )
    initial = AttemptProjection(
        attempt_id=attempt_id,
        status=ExperimentStatus.QUEUED,
        backtest_run_id=None,
        checkpoint_ref=None,
        failure_code=None,
        created_at=NOW,
        updated_at=NOW,
        revision=0,
    )
    fold_projection, attempt = writer.claim_fold_and_add_attempt(
        fold.spec.key,
        spec,
        initial,
        expected_fold_revision=fold.projection.revision,
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
        expected_revision=attempt.revision,
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
        fold.spec.key,
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
) -> tuple[ExperimentLaunchSpec, SchedulerLease]:
    launch = _launch()
    writer.create_experiment(
        RESEARCH_CYCLE,
        launch,
        ExperimentRecord(
            experiment_id=EXPERIMENT_ID,
            status=ExperimentStatus.DRAFT,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=NOW,
        ),
    )
    folds = _folds(launch)
    gates = _preflight_gates(launch)
    for gate in gates:
        writer.add_gate_evaluation(gate)
    for fold in folds:
        writer.add_fold(
            fold,
            FoldProjection(
                key=fold.key,
                status=ExperimentStatus.QUEUED,
                claim_owner_token=None,
                created_at=NOW,
                updated_at=NOW,
                revision=0,
            ),
        )
    writer.enqueue_experiment(
        launch.experiment_id,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail=_preflight_detail(launch, folds, gates),
        launch_fence=ExperimentEnqueueFence.create(gates=gates, folds=folds),
    )
    slot = writer._reader.get_scheduler_slot()
    lease = writer.try_claim_lease(
        launch.experiment_id,
        "r3-backup-seed-owner",
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
    views = writer._reader.list_folds(launch.experiment_id)
    _complete_fold(
        writer,
        next(item for item in views if item.spec.fold_role is FoldRole.EXPLORATION),
        lease,
    )
    writer.advance_experiment_stage(
        launch.experiment_id,
        target_stage=ExperimentStage.WALK_FORWARD,
        expected_revision=2,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "exploration"},
    )
    _complete_fold(
        writer,
        next(item for item in views if item.spec.fold_role is FoldRole.WALK_FORWARD),
        lease,
    )
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


class _FirstAttemptFactory:
    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        attempt_id = AttemptId(f"holdout-attempt-{fold.spec.key.candidate_id}")
        return FirstAttempt(
            AttemptPersistenceSpec(
                attempt_id=attempt_id,
                fold_key=fold.spec.key,
                ordinal=1,
                parent_attempt_id=None,
                resume_from_run_id=None,
                reproduction_fingerprint=ContentHash("7" * 64),
                created_at=occurred_at,
            ),
            AttemptProjection(
                attempt_id=attempt_id,
                status=ExperimentStatus.QUEUED,
                backtest_run_id=None,
                checkpoint_ref=None,
                failure_code=None,
                created_at=occurred_at,
                updated_at=occurred_at,
                revision=0,
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
        del fold, parent, resume_from_run_id, occurred_at
        raise AssertionError("backup fixture never retries holdout work")


def _selection_ledger(launch: ExperimentLaunchSpec) -> TrialLedger:
    trial = launch.promotion_objective.trial_family.current_members[0]
    return build_trial_ledger(
        launch.promotion_objective,
        (
            TrialOutcome(
                trial=trial,
                status=TrialStatus.COMPLETED,
                metrics={
                    ResearchMetricId.NET_RETURN: ResearchMetricValue(
                        ResearchMetricId.NET_RETURN,
                        1.0,
                    )
                },
                holdout_metrics={},
                source_projection_hash=ContentHash("c" * 64),
                metric_evidence={
                    ResearchMetricId.NET_RETURN: MetricEvidenceLineage(
                        ("comparison://r3-backup",),
                        (ContentHash("d" * 64),),
                    )
                },
            ),
        ),
    )


class _SelectionEvidenceProvider:
    def __init__(self, launch: ExperimentLaunchSpec) -> None:
        self.ledger = _selection_ledger(launch)

    def read_selection_evidence(
        self,
        experiment_id: ExperimentId,
        _expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        return PublishedSelectionEvidence(
            ArtifactRecord(
                artifact_id=f"selection-evidence-{self.ledger.content_hash}",
                experiment_id=experiment_id,
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                artifact_kind="selection_evidence",
                relative_path=f"experiments/{experiment_id}/selection-evidence.json",
                content_hash=self.ledger.content_hash,
                schema_hash=ContentHash("e" * 64),
                row_count=1,
                byte_size=1,
                reproduction_fingerprint=ContentHash("f" * 64),
                manifest={},
                is_pinned=False,
                pinned_at=None,
                created_at=NOW,
                revision=0,
            ),
            self.ledger,
        )

    def publish_selection_evidence(
        self,
        _snapshot: object,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> None:
        del lease_fence, now_epoch_us


def _review_packet() -> ReviewPacket:
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id=str(EXPERIMENT_ID),
            candidate_id="candidate-1",
            fold_ids=("fold-holdout",),
            attempt_ids=("attempt-holdout",),
        ),
        spec_hash=ContentHash("1" * 64),
        resolved_spec_hash=ContentHash("6" * 64),
        parameter_hash=_launch().candidates[0].parameter_hash,
        snapshot_hash=ContentHash("8" * 64),
        registry_hash=ContentHash("9" * 64),
        objective_payload_hash=ContentHash("a" * 64),
        gate_evaluations=(
            GateEvaluation(
                rule_id="holdout_claim",
                layer=GateLayer.HARD,
                outcome=GateOutcome.PASS,
                observed={"claim_id": CLAIM_ID},
                policy={"required": True},
            ),
        ),
        comparison_payload_hash=ContentHash("b" * 64),
        r1_impact_payload_hash=ContentHash("c" * 64),
        selection_evidence_artifact_id=None,
        holdout_claim_id=CLAIM_ID,
        candidate_rationale="Selected by the registered objective after costs.",
    )


def _seed_research(
    data_root: Path,
) -> tuple[HoldoutClaimRecord, ReviewPacket, str, bytes]:
    database = ResearchExperimentDatabase(data_root)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    claim = _seed_holdout(database, writer)
    packet = _review_packet()
    record = writer.publish_review_packet(
        packet,
        lease_fence=_review_fence(),
        now_epoch_us=NOW_US,
        created_at=NOW,
    )
    service = ResearchArtifactService(
        artifact_root=database.artifact_root,
        artifact_reader=reader,
        artifact_writer=writer,
    )
    pinned = record
    payload = service.read_indexed_artifact_bytes(pinned.artifact_id)
    assert pinned.is_pinned is True
    database.close_all()
    return claim, packet, pinned.artifact_id, payload


def _review_fence() -> LeaseFence:
    return LeaseFence(
        experiment_id=EXPERIMENT_ID,
        owner_token="promotion-owner",
        revision=0,
        lease_until_epoch_us=NOW_US + 1,
    )


def _decision_history(database: Path) -> tuple[tuple[object, ...], ...]:
    with sqlite3.connect(database) as connection:
        return tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT event_id, strategy_id, version, decision, actor, reason,
                       decided_at
                FROM strategy_decision_event
                ORDER BY rowid
                """
            )
        )


@pytest.mark.integration
def test_r3_dry_run_reads_committed_research_wal_pins(tmp_path: Path) -> None:
    data_root = tmp_path / "wal-source"
    data_root.mkdir()
    _seed_governance(data_root)
    _claim, _packet, artifact_id, _payload = _seed_research(data_root)
    research_database = data_root / "research" / "research.sqlite"
    live = ResearchExperimentDatabase(data_root)
    live.get_connection().execute("PRAGMA wal_autocheckpoint=0")
    SQLiteExperimentWriter(live).add_gate_evaluation(
        GateEvaluationRecord(
            evaluation_id=f"{EXPERIMENT_ID}:post-claim:backup-ready",
            experiment_id=EXPERIMENT_ID,
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            rule_id="backup_ready",
            policy_version="r3-backup-v1",
            layer="hard",
            outcome="pass",
            observed={"ready": True},
            policy={"required": True},
            artifact_id=None,
            evaluated_at=NOW + timedelta(minutes=3),
        )
    )
    assert research_database.with_name("research.sqlite-wal").is_file()

    report = inspect_r3_research_sources(
        data_root=data_root,
        sqlite_path=_metadata_database(data_root),
    )

    assert report.research.table_row_counts["gate_evaluation"] == 7
    assert report.pinned_artifacts[0].artifact_id == artifact_id
    assert report.schemas.research.user_version == RESEARCH_USER_VERSION
    live.close_all()


def _assert_manifest(
    manifest_bytes: bytes,
    *,
    packet: ReviewPacket,
    artifact_id: str,
    artifact_payload: bytes,
) -> None:
    manifest = orjson.loads(manifest_bytes)
    assert manifest_bytes == orjson.dumps(manifest, option=orjson.OPT_SORT_KEYS)
    assert manifest["schema"] == "ditto.r3-research-backup"
    assert manifest["version"] == 1
    assert manifest["schemas"]["governance"] == {
        "application_id": 0,
        "required_tables": [
            "strategy_activation_event",
            "strategy_active_pointer",
            "strategy_decision_event",
            "strategy_version",
            "strategy_version_state",
        ],
        "required_triggers": [],
        "schema_fingerprint": (
            "31fae35fab8c77daa028b31e5e2c3c8d9d706f0fff11d50eb7860e04da529b90"
        ),
        "schema_row_count": 5,
        "user_version": 0,
    }
    assert manifest["schemas"]["research"]["application_id"] == 1_146_376_755
    assert manifest["schemas"]["research"]["user_version"] == (RESEARCH_USER_VERSION)
    assert manifest["schemas"]["research"]["schema_fingerprint"] == (
        RESEARCH_SCHEMA_FINGERPRINT
    )
    assert manifest["schemas"]["research"]["schema_row_count"] == (
        RESEARCH_SCHEMA_ROW_COUNT
    )
    assert manifest["domain"]["active_strategies"][0]["strategy_id"] == (
        "stock-selection"
    )
    assert len(manifest["domain"]["decision_history"]) == 3
    assert manifest["domain"]["holdout_claims"][0]["claim_id"] == CLAIM_ID
    assert manifest["domain"]["pinned_review_packets"][0]["artifact_id"] == artifact_id
    assert manifest["metadata"]["integrity_check"] == "ok"
    assert manifest["research"]["integrity_check"] == "ok"
    assert manifest["artifacts"]["file_count"] == 2
    assert manifest["pinned_artifacts"] == [
        {
            "artifact_id": artifact_id,
            "artifact_kind": "review_packet",
            "byte_size": len(artifact_payload),
            "content_hash": f"sha256:{packet.bundle_hash}",
            "relative_path": (f"experiments/{EXPERIMENT_ID}/review-packet.json"),
            "reproduction_fingerprint": str(packet.bundle_hash),
        }
    ]


@pytest.mark.integration
def test_r3_backup_restore_preserves_governance_holdout_and_pinned_packet(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    pointer, decisions = _seed_governance(source_root)
    claim, packet, artifact_id, artifact_payload = _seed_research(source_root)
    backup_root = tmp_path / "backups" / "r3-20260728"

    backup = create_r3_research_backup(
        data_root=source_root,
        backup_root=backup_root,
        sqlite_path=_metadata_database(source_root),
    )

    _assert_manifest(
        backup.manifest_path.read_bytes(),
        packet=packet,
        artifact_id=artifact_id,
        artifact_payload=artifact_payload,
    )

    (source_root / "metadata" / "metadata.sqlite").unlink()
    (source_root / "research" / "research.sqlite").unlink()
    packet_path = (
        source_root
        / "research"
        / "artifacts"
        / (f"experiments/{EXPERIMENT_ID}/review-packet.json")
    )
    packet_path.write_bytes(b'{"tampered":true}')
    restored_root = tmp_path / "restored"

    restored = restore_r3_research_backup(
        backup_root=backup_root,
        destination_root=restored_root,
    )
    verified_restore = verify_restored_r3_research_backup(
        backup_root=backup_root,
        destination_root=restored_root,
        sqlite_path=_metadata_database(restored_root),
    )

    assert restored.metadata_database == (
        restored_root / "metadata" / "metadata.sqlite"
    )
    assert verified_restore.domain == restored.domain
    assert restored.metadata_database.is_file()
    assert not (restored_root / "metadata.sqlite").exists()
    restored_pool = SQLitePool(str(restored.metadata_database))
    restored_governance = SQLiteStrategyGovernanceStore(restored_pool)
    assert restored_governance.get_active_pointer("stock-selection") == pointer
    assert _decision_history(restored.metadata_database) == decisions
    restored_pool.close_all()

    restored_database = ResearchExperimentDatabase(restored_root)
    restored_reader = SQLiteExperimentReader(restored_database)
    restored_writer = SQLiteExperimentWriter(restored_database)
    restored_artifacts = ResearchArtifactService(
        artifact_root=restored_database.artifact_root,
        artifact_reader=restored_reader,
        artifact_writer=restored_writer,
    )
    assert restored_reader.get_holdout_claim(CLAIM_ID) == claim
    restored_record = restored_reader.get_artifact(artifact_id)
    assert restored_record is not None
    assert restored_record.is_pinned is True
    assert str(restored_record.content_hash) == str(packet.bundle_hash)
    assert str(restored_record.reproduction_fingerprint) == str(packet.bundle_hash)
    assert restored_artifacts.read_indexed_artifact_bytes(artifact_id) == (
        artifact_payload
    )
    assert restored_reader.get_review_packet(str(packet.bundle_hash)) == packet
    restored_database.close_all()


@pytest.mark.integration
def test_r3_backup_honors_sqlite_path_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    stale_canonical = _metadata_database(source_root)
    stale_canonical.parent.mkdir()
    with sqlite3.connect(stale_canonical) as connection:
        connection.execute("CREATE TABLE stale_metadata(value TEXT)")
        connection.commit()
    override = tmp_path / "metadata-override" / "runtime.sqlite"
    _seed_governance(source_root, sqlite_path=override)
    _seed_research(source_root)
    monkeypatch.setenv("SQLITE_PATH", str(override))

    backup = create_r3_research_backup(
        data_root=source_root,
        backup_root=tmp_path / "backup",
    )

    assert "strategy_active_pointer" in backup.metadata.table_row_counts
    assert "stale_metadata" not in backup.metadata.table_row_counts
    assert backup.domain.active_strategies[0].strategy_id == "stock-selection"


@pytest.mark.integration
@pytest.mark.parametrize(
    "mutation",
    [
        "governance_application_id",
        "governance_missing_table",
        "research_application_id",
        "research_missing_trigger",
        "research_extra_table",
    ],
)
def test_r3_backup_rejects_noncanonical_schemas(
    tmp_path: Path,
    mutation: str,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _seed_governance(source_root)
    _seed_research(source_root)
    metadata = _metadata_database(source_root)
    research = source_root / "research" / "research.sqlite"
    target = metadata if mutation.startswith("governance") else research
    with sqlite3.connect(target) as connection:
        if mutation.endswith("application_id"):
            connection.execute("PRAGMA application_id=42")
        elif mutation == "governance_missing_table":
            connection.execute("DROP TABLE strategy_decision_event")
        elif mutation == "research_missing_trigger":
            connection.execute("DROP TRIGGER trg_holdout_claim_no_delete")
        else:
            connection.execute("CREATE TABLE schema_tamper(value TEXT)")
        connection.commit()
    backup_root = tmp_path / "rejected-backup"

    with pytest.raises(R3ResearchBackupError, match="combined R3 backup failed"):
        create_r3_research_backup(
            data_root=source_root,
            backup_root=backup_root,
            sqlite_path=metadata,
        )

    assert not backup_root.exists()


@pytest.mark.integration
def test_r3_verify_restored_rejects_domain_drift(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _seed_governance(source_root)
    _seed_research(source_root)
    backup_root = tmp_path / "backup"
    create_r3_research_backup(
        data_root=source_root,
        backup_root=backup_root,
        sqlite_path=_metadata_database(source_root),
    )
    restored_root = tmp_path / "restored"
    restore_r3_research_backup(
        backup_root=backup_root,
        destination_root=restored_root,
    )
    with sqlite3.connect(_metadata_database(restored_root)) as connection:
        connection.execute(
            "UPDATE strategy_decision_event SET actor='tampered' "
            "WHERE event_id='decision-approve'"
        )
        connection.commit()

    with pytest.raises(
        R3ResearchBackupError,
        match="restored R3 verification failed",
    ):
        verify_restored_r3_research_backup(
            backup_root=backup_root,
            destination_root=restored_root,
            sqlite_path=_metadata_database(restored_root),
        )


@pytest.mark.integration
def test_r3_verify_restored_cli_reopens_domain_services(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _seed_governance(source_root)
    _seed_research(source_root)
    backup_root = tmp_path / "backup"
    create_r3_research_backup(
        data_root=source_root,
        backup_root=backup_root,
        sqlite_path=_metadata_database(source_root),
    )
    restored_root = tmp_path / "restored"
    restore_r3_research_backup(
        backup_root=backup_root,
        destination_root=restored_root,
    )

    exit_code = backup_main(
        [
            "verify-restored",
            "--backup-root",
            str(backup_root),
            "--destination-root",
            str(restored_root),
            "--sqlite-path",
            str(_metadata_database(restored_root)),
        ]
    )

    assert exit_code == 0
    output = orjson.loads(capsys.readouterr().out)
    assert output["destination_root"] == str(restored_root)
    assert output["domain"]["holdout_claims"][0]["claim_id"] == CLAIM_ID


@pytest.mark.integration
def test_r3_create_and_restore_reject_dangling_root_symlinks(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _seed_governance(source_root)
    _seed_research(source_root)
    dangling_backup = tmp_path / "dangling-backup"
    missing_backup_target = tmp_path / "missing-backup-target"
    dangling_backup.symlink_to(missing_backup_target, target_is_directory=True)

    with pytest.raises(
        R3ResearchBackupError,
        match="backup root cannot be a symbolic link",
    ):
        create_r3_research_backup(
            data_root=source_root,
            backup_root=dangling_backup,
            sqlite_path=_metadata_database(source_root),
        )
    assert not missing_backup_target.exists()

    backup_root = tmp_path / "backup"
    create_r3_research_backup(
        data_root=source_root,
        backup_root=backup_root,
        sqlite_path=_metadata_database(source_root),
    )
    dangling_destination = tmp_path / "dangling-destination"
    missing_destination_target = tmp_path / "missing-destination-target"
    dangling_destination.symlink_to(
        missing_destination_target,
        target_is_directory=True,
    )

    with pytest.raises(
        R3ResearchBackupError,
        match="restore destination cannot be a symbolic link",
    ):
        restore_r3_research_backup(
            backup_root=backup_root,
            destination_root=dangling_destination,
        )
    assert not missing_destination_target.exists()


@pytest.mark.integration
def test_r3_backup_restore_refuses_overwrite_and_cleans_only_new_partial_units(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _seed_governance(source_root)
    _seed_research(source_root)
    existing_backup = tmp_path / "existing-backup"
    existing_backup.mkdir()
    sentinel = existing_backup / "sentinel"
    sentinel.write_bytes(b"prior-evidence")

    with pytest.raises(R3ResearchBackupError, match="backup root already exists"):
        create_r3_research_backup(
            data_root=source_root,
            backup_root=existing_backup,
            sqlite_path=_metadata_database(source_root),
        )
    assert sentinel.read_bytes() == b"prior-evidence"

    contained_backup = source_root / "nested-backup"
    with pytest.raises(
        R3ResearchBackupError,
        match="backup root must be outside source data root",
    ):
        create_r3_research_backup(
            data_root=source_root,
            backup_root=contained_backup,
            sqlite_path=_metadata_database(source_root),
        )
    assert not contained_backup.exists()

    partial_root = tmp_path / "partial-backup"
    artifacts = source_root / "research" / "artifacts"
    renamed_artifacts = source_root / "research" / "artifacts-unavailable"
    artifacts.rename(renamed_artifacts)
    with pytest.raises(R3ResearchBackupError, match="R3 source inspection failed"):
        inspect_r3_research_sources(
            data_root=source_root,
            sqlite_path=_metadata_database(source_root),
        )
    with pytest.raises(R3ResearchBackupError, match="combined R3 backup failed"):
        create_r3_research_backup(
            data_root=source_root,
            backup_root=partial_root,
            sqlite_path=_metadata_database(source_root),
        )
    assert not partial_root.exists()
    renamed_artifacts.rename(artifacts)

    backup_root = tmp_path / "verified-backup"
    create_r3_research_backup(
        data_root=source_root,
        backup_root=backup_root,
        sqlite_path=_metadata_database(source_root),
    )
    contained_restore = backup_root / "nested-restore"
    with pytest.raises(
        R3ResearchBackupError,
        match="restore destination must be outside backup root",
    ):
        restore_r3_research_backup(
            backup_root=backup_root,
            destination_root=contained_restore,
        )
    assert not contained_restore.exists()

    existing_restore = tmp_path / "existing-restore"
    existing_restore.mkdir()
    restore_sentinel = existing_restore / "sentinel"
    restore_sentinel.write_bytes(b"do-not-overwrite")
    with pytest.raises(
        R3ResearchBackupError,
        match="restore destination already exists",
    ):
        restore_r3_research_backup(
            backup_root=backup_root,
            destination_root=existing_restore,
        )
    assert restore_sentinel.read_bytes() == b"do-not-overwrite"

    backed_packet = next((backup_root / "artifacts").rglob("review-packet.json"))
    backed_packet.write_bytes(b'{"tampered":true}')
    failed_restore = tmp_path / "failed-restore"
    with pytest.raises(R3ResearchBackupError, match="backup does not match manifest"):
        restore_r3_research_backup(
            backup_root=backup_root,
            destination_root=failed_restore,
        )
    assert not failed_restore.exists()
    assert backup_root.exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    "entry_name",
    ["metadata.sqlite", "research.sqlite", "manifest.json", "artifacts"],
)
def test_r3_backup_layout_rejects_external_symlinks(
    tmp_path: Path,
    entry_name: str,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _seed_governance(source_root)
    _seed_research(source_root)
    backup_root = tmp_path / "backup"
    create_r3_research_backup(
        data_root=source_root,
        backup_root=backup_root,
        sqlite_path=_metadata_database(source_root),
    )
    alias = tmp_path / "backup-alias"
    alias.symlink_to(backup_root, target_is_directory=True)

    with pytest.raises(
        R3ResearchBackupError,
        match="backup layout cannot contain symbolic links",
    ):
        verify_r3_research_backup(backup_root=alias)

    entry = backup_root / entry_name
    external = tmp_path / f"external-{entry_name}"
    entry.rename(external)
    entry.symlink_to(external, target_is_directory=external.is_dir())
    with pytest.raises(
        R3ResearchBackupError,
        match="backup layout cannot contain symbolic links",
    ):
        verify_r3_research_backup(backup_root=backup_root)
