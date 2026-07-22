"""Fresh-``tmp_path`` integration for the atomic R3 holdout claim authority."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest
from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
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
    ExperimentFailureCode,
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
from ditto_application.commands.experiments import (
    ClaimHoldoutCandidateCommand,
    ClaimHoldoutCandidateHandler,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
)

NOW = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)


def _holdout_api() -> SimpleNamespace:
    from ditto_analysis.experiments.holdout import (
        HoldoutClaimAuthorityCommand,
        HoldoutSelectionReason,
    )
    from ditto_application.processes.experiments.holdout import (
        ClaimHoldoutCandidateRequest,
    )
    from ditto_application.processes.experiments.holdout import (
        HoldoutSelectionReason as ApplicationSelectionReason,
    )

    return SimpleNamespace(
        HoldoutClaimAuthorityCommand=HoldoutClaimAuthorityCommand,
        HoldoutSelectionReason=HoldoutSelectionReason,
        ClaimHoldoutCandidateRequest=ClaimHoldoutCandidateRequest,
        ApplicationSelectionReason=ApplicationSelectionReason,
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
    folds: list[FoldPersistenceSpec] = []
    for candidate in launch.candidates:
        for ordinal, role in (
            (1, FoldRole.EXPLORATION),
            (2, FoldRole.WALK_FORWARD),
            (3, FoldRole.HOLDOUT),
        ):
            key = FoldKey(
                launch.experiment_id,
                candidate.candidate_id,
                FoldId(f"fold-{candidate.ordinal}-{ordinal}"),
            )
            folds.append(
                FoldPersistenceSpec.create(
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
            )
    return tuple(folds)


_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"
_GATE_RULES = ("matrix", "executor", "authority", "history", "certification", "budget")


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
    snapshot = _snapshot_evidence(
        launch,
        snapshot_manifest_hash,
        certified_cutoff,
    )
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


def _persist_candidate_selection(
    writer: SQLiteExperimentWriter,
    database: ResearchExperimentDatabase,
    *,
    experiment_id: str = "experiment-1",
    cycle_id: str = "cycle-shared",
    cycle_hash: str | None = None,
    snapshot_id: str = "snapshot-holdout-integration",
    snapshot_manifest_hash: str = "5" * 64,
    certified_cutoff: date | None = None,
    holdout_window: DateWindow | None = None,
    fail_walk_forward_candidate_id: str | None = None,
    acquire_lease: bool = True,
    preflight_status: str | None = "ready",
    preflight_eligibility: str | None = None,
) -> tuple[ExperimentLaunchSpec, Any | None]:
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
    cycle = ResearchCycleIdentity(
        cycle_id,
        derived_cycle_hash if cycle_hash is None else ContentHash(cycle_hash),
    )
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
    if not acquire_lease:
        return launch, None
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
            if str(fold.key.candidate_id) == fail_walk_forward_candidate_id:
                _fail_fold(writer, fold, lease)
            else:
                _complete_fold(writer, fold, lease)
    if fail_walk_forward_candidate_id is not None:
        return launch, lease
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


def _fail_fold(
    writer: SQLiteExperimentWriter,
    fold: FoldPersistenceSpec | FoldView,
    lease: Any,
) -> None:
    view = fold if isinstance(fold, FoldView) else writer._reader.get_fold(fold.key)
    assert view is not None
    attempt_id = AttemptId(
        f"attempt-failed-{view.spec.key.experiment_id}-{view.spec.key.fold_id}"
    )
    attempt_spec = AttemptPersistenceSpec(
        attempt_id,
        view.spec.key,
        1,
        None,
        None,
        ContentHash("8" * 64),
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
        target_status=ExperimentStatus.FAILED,
        backtest_run_id=running.backtest_run_id,
        checkpoint_ref=None,
        failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        expected_revision=running.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 6,
        occurred_at=NOW,
        reason_code="candidate_attempt_failed",
        detail={},
    )
    writer.transition_fold(
        view.spec.key,
        target_status=ExperimentStatus.FAILED,
        claim_owner_token=None,
        failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        expected_revision=fold_projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 7,
        occurred_at=NOW,
        reason_code="candidate_fold_failed",
        detail={},
    )


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


def _command(
    *,
    experiment_id: str = "experiment-1",
    candidate_id: str = "candidate-2",
    expected_revision: int = 4,
    fingerprint: str = "4" * 64,
    evidence_hash: str = "5" * 64,
    occurred_at: datetime = NOW,
) -> Any:
    api = _holdout_api()
    return api.HoldoutClaimAuthorityCommand(
        experiment_id=ExperimentId(experiment_id),
        candidate_id=CandidateId(candidate_id),
        expected_revision=expected_revision,
        expected_selection_evidence_hash=ContentHash(evidence_hash),
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=api.HoldoutSelectionReason(
            "objective_review",
            "Candidate won the registered objective review.",
        ),
        resolved_reproduction_fingerprint=ContentHash(fingerprint),
        occurred_at=occurred_at,
    )


def _claim(
    writer: SQLiteExperimentWriter,
    lease: Any,
    command: Any | None = None,
) -> Any:
    return writer.claim_holdout_candidate(
        command or _command(),
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 1,
    )


def _finish_claimed_experiment(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    lease: Any,
) -> None:
    selected = next(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and fold.projection.status is ExperimentStatus.QUEUED
    )
    _complete_fold(writer, selected, lease, fingerprint="4" * 64)
    writer.advance_experiment_stage(
        launch.experiment_id,
        target_stage=ExperimentStage.EVIDENCE,
        expected_revision=5,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 8,
        occurred_at=NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "holdout"},
    )
    writer.transition_scheduled_experiment(
        launch.experiment_id,
        target_status=ExperimentStatus.COMPLETED,
        target_stage=ExperimentStage.EVIDENCE,
        failure_code=None,
        expected_revision=6,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 9,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="terminal_test",
        detail={},
    )
    writer.release_lease(lease.fence, now_epoch_us=NOW_US + 10)


def test_atomic_claim_commits_claim_stage_event_and_unselected_cancellation(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    before_events = len(reader.list_status_events(launch.experiment_id))

    receipt = _claim(writer, lease)

    projection = reader.get_experiment_projection(launch.experiment_id)
    claim = reader.get_holdout_claim_for_experiment(launch.experiment_id)
    holdout = tuple(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
    )
    assert projection is not None
    assert projection.record.stage is ExperimentStage.HOLDOUT
    assert projection.revision == 5
    assert claim == receipt.claim
    assert receipt.experiment_revision == 5
    assert claim.fold_key.candidate_id == CandidateId("candidate-2")
    assert claim.resolved_spec_hash == launch.execution_bindings[1].resolved_spec_hash
    assert claim.parameters_hash == launch.candidates[1].parameter_hash
    assert claim.snapshot_id == launch.snapshot_id
    assert claim.window == holdout[1].spec.test_window
    assert claim.reproduction_fingerprint == ContentHash("4" * 64)
    assert [fold.projection.status for fold in holdout] == [
        ExperimentStatus.CANCELLED,
        ExperimentStatus.QUEUED,
    ]
    assert len(reader.list_status_events(launch.experiment_id)) == before_events + 2
    database.close_all()


def test_exact_and_terminal_replay_return_original_receipt_without_writes(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    command = _command()
    first = _claim(writer, lease, command)
    selected = next(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and fold.spec.key.candidate_id == CandidateId("candidate-2")
    )
    _complete_fold(writer, selected, lease, fingerprint="4" * 64)
    writer.advance_experiment_stage(
        launch.experiment_id,
        target_stage=ExperimentStage.EVIDENCE,
        expected_revision=5,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 8,
        occurred_at=NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "holdout"},
    )
    writer.transition_scheduled_experiment(
        launch.experiment_id,
        target_status=ExperimentStatus.COMPLETED,
        target_stage=ExperimentStage.EVIDENCE,
        failure_code=None,
        expected_revision=6,
        lease_fence=lease.fence,
        now_epoch_us=NOW_US + 9,
        occurred_at=NOW,
        attempt_started=True,
        precondition_repairable=False,
        reason_code="terminal_test",
        detail={},
    )
    connection = database.get_connection()
    before = connection.total_changes

    replay = writer.claim_holdout_candidate(
        replace(command, resolved_reproduction_fingerprint=None),
        lease_fence=None,
        now_epoch_us=None,
    )

    assert replay == first
    assert connection.total_changes == before
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 1
    database.close_all()


def test_exact_replay_preserves_microsecond_edge_timestamp(tmp_path: Path) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    edge_time = datetime(2500, 1, 1, 0, 0, 0, 1, tzinfo=UTC)
    command = _command(occurred_at=edge_time)

    first = _claim(writer, lease, command)
    connection = database.get_connection()
    before_replay = connection.total_changes
    replay = writer.claim_holdout_candidate(
        replace(command, resolved_reproduction_fingerprint=None),
        lease_fence=None,
        now_epoch_us=None,
    )
    persisted = reader.get_holdout_claim_for_experiment(launch.experiment_id)
    claim_events = tuple(
        event
        for event in reader.list_status_events(launch.experiment_id)
        if event.reason_code
        in {"holdout_candidate_claimed", "holdout_candidate_not_selected"}
    )

    assert replay == first
    assert persisted is not None
    assert persisted.claimed_at == edge_time
    assert all(event.occurred_at == edge_time for event in claim_events)
    assert connection.total_changes == before_replay
    database.close_all()


@pytest.mark.parametrize("tamper", ["missing", "drifted"])
def test_exact_replay_rejects_missing_or_drifted_unselected_fold_event(
    tmp_path: Path,
    tamper: str,
) -> None:
    database, _reader, writer, _launch_one, lease = _store(tmp_path)
    command = _command()
    _claim(writer, lease, command)
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT event_id FROM experiment_status_event
        WHERE experiment_id='experiment-1' AND subject_type='fold'
          AND reason_code='holdout_candidate_not_selected'
        """
    ).fetchone()
    assert event is not None
    if tamper == "missing":
        connection.execute("DROP TRIGGER trg_experiment_status_event_no_delete")
        connection.execute(
            "DELETE FROM experiment_status_event WHERE event_id=?",
            (event["event_id"],),
        )
    else:
        connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
        connection.execute(
            "UPDATE experiment_status_event SET reason_code=? WHERE event_id=?",
            ("candidate_isolated_after_failure", event["event_id"]),
        )
    connection.commit()
    before_replay = connection.total_changes

    with pytest.raises(ExperimentIntegrityError):
        writer.claim_holdout_candidate(
            replace(command, resolved_reproduction_fingerprint=None),
            lease_fence=None,
            now_epoch_us=None,
        )

    assert connection.total_changes == before_replay
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 1
    database.close_all()


def test_scheduler_snapshot_rejects_canonically_rehashed_claim_event_drift(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    _claim(writer, lease)
    connection = database.get_connection()
    drifted = canonical_payload({"claim_id": "wrong-claim"})
    connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
    connection.execute(
        """
        UPDATE experiment_status_event SET detail_json=?, detail_hash=?
        WHERE experiment_id=? AND subject_type='experiment'
          AND reason_code='holdout_candidate_claimed'
        """,
        (
            drifted.json_bytes.decode("utf-8"),
            str(drifted.content_hash),
            str(launch.experiment_id),
        ),
    )
    connection.commit()

    with pytest.raises(AppProcessError) as exc_info:
        ExperimentSchedulerStore(reader, writer).load_snapshot(launch.experiment_id)

    assert exc_info.value.details["reason"] == "holdout_claim_event_drift"
    database.close_all()


@pytest.mark.parametrize("identity_column", ["claim_id", "logical_run_id"])
def test_claim_reader_rejects_derived_identity_drift(
    tmp_path: Path,
    identity_column: str,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    receipt = _claim(writer, lease)
    connection = database.get_connection()
    drifted_value = f"drifted-{identity_column}"
    drifted_claim = replace(receipt.claim, **{identity_column: drifted_value})
    connection.execute("DROP TRIGGER trg_holdout_claim_no_update")
    connection.execute(
        f"""UPDATE holdout_claim
        SET {identity_column}=?, claim_payload_hash=? WHERE experiment_id=?""",
        (
            drifted_value,
            str(drifted_claim.claim_payload_hash),
            str(launch.experiment_id),
        ),
    )
    connection.commit()

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        reader.get_holdout_claim_for_experiment(launch.experiment_id)

    assert (
        exc_info.value.details["reason_code"] == "holdout_claim_derived_identity_drift"
    )
    database.close_all()


def test_conflicting_candidate_and_clone_in_same_cycle_fail_closed(
    tmp_path: Path,
) -> None:
    database, _reader, writer, _launch_one, lease = _store(tmp_path)
    first = _claim(writer, lease)
    _persist_candidate_selection(
        writer,
        database,
        experiment_id="experiment-clone",
        acquire_lease=False,
    )

    with pytest.raises(ExperimentConflictError):
        _claim(writer, lease, _command(candidate_id="candidate-1"))
    with pytest.raises(ExperimentConflictError):
        _claim(
            writer,
            lease,
            _command(experiment_id="experiment-clone", candidate_id="candidate-2"),
        )

    assert first.claim.fold_key.experiment_id == ExperimentId("experiment-1")
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


def test_renamed_cycle_clone_with_same_authority_returns_original_claim(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch_one, lease = _store(tmp_path)
    original = _claim(writer, lease)
    _finish_claimed_experiment(reader, writer, launch_one, lease)
    _clone, clone_lease = _persist_candidate_selection(
        writer,
        database,
        experiment_id="experiment-renamed-cycle",
        cycle_id="cycle-renamed",
    )
    assert clone_lease is not None

    with pytest.raises(ExperimentConflictError) as exc_info:
        _claim(
            writer,
            clone_lease,
            _command(experiment_id="experiment-renamed-cycle"),
        )

    assert exc_info.value.details["claim_id"] == original.claim.claim_id
    assert exc_info.value.details["experiment_id"] == "experiment-1"
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


def test_snapshot_label_change_without_later_cutoff_cannot_reset_holdout(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch_one, lease = _store(tmp_path)
    original = _claim(writer, lease)
    _finish_claimed_experiment(reader, writer, launch_one, lease)
    _clone, clone_lease = _persist_candidate_selection(
        writer,
        database,
        experiment_id="experiment-snapshot-label-clone",
        cycle_id="cycle-snapshot-label-clone",
        snapshot_id="snapshot-label-only-changed",
    )
    assert clone_lease is not None

    with pytest.raises(ExperimentConflictError) as exc_info:
        _claim(
            writer,
            clone_lease,
            _command(experiment_id="experiment-snapshot-label-clone"),
        )

    assert exc_info.value.details["claim_id"] == original.claim.claim_id
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


def test_later_certified_cutoff_and_new_oos_allows_next_cycle(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch_one, lease = _store(tmp_path)
    first = _claim(writer, lease)
    _finish_claimed_experiment(reader, writer, launch_one, lease)
    later_window = DateWindow(date(2026, 5, 1), date(2026, 5, 31))
    launch_two, later_lease = _persist_candidate_selection(
        writer,
        database,
        experiment_id="experiment-later-oos",
        cycle_id="cycle-later-oos",
        snapshot_id="snapshot-later-oos",
        snapshot_manifest_hash="6" * 64,
        certified_cutoff=date(2026, 5, 31),
        holdout_window=later_window,
    )
    assert later_lease is not None

    second = _claim(
        writer,
        later_lease,
        _command(experiment_id=str(launch_two.experiment_id)),
    )

    assert second.claim.claim_id != first.claim.claim_id
    assert second.claim.window == later_window
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 2
    )
    database.close_all()


def test_noncanonical_cycle_hash_cannot_consume_first_holdout(tmp_path: Path) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    writer = SQLiteExperimentWriter(database)
    _launch_one, lease = _persist_candidate_selection(
        writer,
        database,
        cycle_hash="a" * 64,
    )
    assert lease is not None

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        _claim(writer, lease)

    assert (
        exc_info.value.details["reason_code"] == "holdout_preflight_authority_invalid"
    )
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 0
    )
    database.close_all()


def test_concurrent_same_request_replays_one_claim(tmp_path: Path) -> None:
    database, _reader, writer, _launch_one, lease = _store(tmp_path)
    barrier = Barrier(2)

    def run() -> Any:
        barrier.wait()
        return _claim(writer, lease)

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = tuple(executor.map(lambda _item: run(), range(2)))

    assert receipts[0] == receipts[1]
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


def test_concurrent_different_candidates_has_one_winner(tmp_path: Path) -> None:
    database, _reader, writer, _launch_one, lease = _store(tmp_path)
    barrier = Barrier(2)

    def run(candidate_id: str) -> object:
        barrier.wait()
        try:
            return _claim(writer, lease, _command(candidate_id=candidate_id))
        except ExperimentConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(run, ("candidate-1", "candidate-2")))

    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, ExperimentConflictError) for item in outcomes) == 1
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


@pytest.mark.parametrize(
    ("target_status", "target_desired_state", "reason_code"),
    [
        (
            ExperimentStatus.PAUSE_REQUESTED,
            ExperimentDesiredState.PAUSE,
            "operator_pause",
        ),
        (
            ExperimentStatus.CANCEL_REQUESTED,
            ExperimentDesiredState.CANCEL,
            "operator_cancel",
        ),
    ],
)
def test_claim_serializes_with_concurrent_pause_or_cancel(
    tmp_path: Path,
    target_status: ExperimentStatus,
    target_desired_state: ExperimentDesiredState,
    reason_code: str,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    barrier = Barrier(2)

    def claim() -> object:
        barrier.wait()
        try:
            return _claim(writer, lease)
        except (ExperimentConflictError, ExperimentSpecError) as exc:
            return exc

    def control() -> object:
        barrier.wait()
        try:
            return writer.transition_experiment(
                launch.experiment_id,
                target_status=target_status,
                target_desired_state=target_desired_state,
                target_stage=ExperimentStage.CANDIDATE_SELECTION,
                failure_code=None,
                expected_revision=4,
                occurred_at=NOW + timedelta(seconds=1),
                attempt_started=False,
                precondition_repairable=False,
                reason_code=reason_code,
                detail={},
            )
        except (ExperimentConflictError, ExperimentSpecError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        claim_future = executor.submit(claim)
        control_future = executor.submit(control)
        claim_outcome = claim_future.result()
        control_outcome = control_future.result()

    claim_won = not isinstance(claim_outcome, Exception)
    control_won = not isinstance(control_outcome, Exception)
    assert claim_won is not control_won
    projection = reader.get_experiment_projection(launch.experiment_id)
    assert projection is not None
    if claim_won:
        assert projection.record.stage is ExperimentStage.HOLDOUT
        assert projection.record.status is ExperimentStatus.RUNNING
        assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is not None
    else:
        assert projection.record.stage is ExperimentStage.CANDIDATE_SELECTION
        assert projection.record.status is target_status
        assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is None
    database.close_all()


def test_stale_revision_lease_and_pause_cancel_state_reject_without_claim(
    tmp_path: Path,
) -> None:
    database, _reader, writer, launch, lease = _store(tmp_path)

    with pytest.raises(ExperimentConflictError):
        _claim(writer, lease, _command(expected_revision=3))
    renewed = writer.renew_lease(
        lease.fence,
        now_epoch_us=NOW_US + 2,
        new_lease_until_epoch_us=NOW_US + 120_000_000,
    )
    with pytest.raises(ExperimentLeaseLostError):
        _claim(writer, lease)

    writer.transition_experiment(
        launch.experiment_id,
        target_status=ExperimentStatus.PAUSE_REQUESTED,
        target_desired_state=ExperimentDesiredState.PAUSE,
        target_stage=ExperimentStage.CANDIDATE_SELECTION,
        failure_code=None,
        expected_revision=4,
        occurred_at=NOW + timedelta(seconds=1),
        attempt_started=False,
        precondition_repairable=False,
        reason_code="operator_pause",
        detail={},
    )
    with pytest.raises(ExperimentSpecError):
        writer.claim_holdout_candidate(
            _command(expected_revision=5),
            lease_fence=renewed.fence,
            now_epoch_us=NOW_US + 3,
        )
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 0
    )
    database.close_all()


def test_live_child_rejects_claim_without_consuming_holdout(tmp_path: Path) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    selected = next(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and fold.spec.key.candidate_id == CandidateId("candidate-2")
    )
    connection = database.get_connection()
    # Simulate a legacy/out-of-band live child only in this disposable tmp_path DB.
    connection.execute(
        """
        INSERT INTO experiment_attempt(
            attempt_id, experiment_id, candidate_id, fold_id, ordinal,
            parent_attempt_id, status, backtest_run_id, resume_from_run_id,
            checkpoint_ref, reproduction_fingerprint, failure_code,
            created_at_epoch_us, updated_at_epoch_us, revision
        ) VALUES (?, ?, ?, ?, 1, NULL, 'queued', NULL, NULL, NULL, ?, NULL, ?, ?, 0)
        """,
        (
            "attempt-injected-live-holdout",
            str(selected.spec.key.experiment_id),
            str(selected.spec.key.candidate_id),
            str(selected.spec.key.fold_id),
            "4" * 64,
            NOW_US,
            NOW_US,
        ),
    )
    connection.commit()

    with pytest.raises(ExperimentSpecError) as exc_info:
        _claim(writer, lease)

    assert exc_info.value.details["reason_code"] == "holdout_live_work_exists"
    assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is None
    projection = reader.get_experiment_projection(launch.experiment_id)
    assert projection is not None
    assert projection.record.stage is ExperimentStage.CANDIDATE_SELECTION
    database.close_all()


@pytest.mark.parametrize(
    "preflight_state",
    ["research_only", "missing", "tampered", "metadata_tampered"],
)
def test_research_only_missing_or_tampered_preflight_cannot_consume_holdout(
    tmp_path: Path,
    preflight_state: str,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    writer = SQLiteExperimentWriter(database)
    launch, lease = _persist_candidate_selection(
        writer,
        database,
        preflight_status=(
            "ready"
            if preflight_state in {"tampered", "metadata_tampered"}
            else None
            if preflight_state == "missing"
            else "research_only"
        ),
    )
    assert lease is not None
    connection = database.get_connection()
    if preflight_state == "tampered":
        # Simulate out-of-band corruption only in this disposable tmp_path DB.
        connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
        connection.execute(
            """
            UPDATE experiment_status_event SET detail_json=?
            WHERE experiment_id=? AND reason_code='preflight_passed'
            """,
            ('{"preflight":{"status":"research_only"}}', str(launch.experiment_id)),
        )
    elif preflight_state == "metadata_tampered":
        connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
        connection.execute(
            """
            UPDATE experiment_status_event SET desired_state='pause'
            WHERE experiment_id=? AND reason_code='preflight_passed'
            """,
            (str(launch.experiment_id),),
        )
    connection.commit()

    with pytest.raises((ExperimentSpecError, ExperimentPersistenceError)):
        _claim(writer, lease)

    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    assert (
        connection.execute(
            "SELECT stage FROM experiment WHERE experiment_id=?",
            (str(launch.experiment_id),),
        ).fetchone()[0]
        == "candidate_selection"
    )
    database.close_all()


def test_canonically_rehashed_preflight_payload_tamper_cannot_consume_holdout(
    tmp_path: Path,
) -> None:
    database, _reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT detail_json FROM experiment_status_event
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert event is not None
    detail = json.loads(event["detail_json"])
    detail["preflight"]["tampered"] = True
    replacement = canonical_payload(detail)
    connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
    connection.execute(
        """
        UPDATE experiment_status_event SET detail_json=?, detail_hash=?
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (
            replacement.json_bytes.decode("utf-8"),
            str(replacement.content_hash),
            str(launch.experiment_id),
        ),
    )
    connection.commit()

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        _claim(writer, lease)

    assert (
        exc_info.value.details["reason_code"] == "holdout_preflight_authority_invalid"
    )
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    database.close_all()


def _rewrite_preflight_event(
    connection: Any,
    experiment_id: ExperimentId,
    detail: dict[str, object],
) -> None:
    preflight = detail["preflight"]
    plan = detail["plan_preimage"]
    assert isinstance(preflight, dict)
    assert isinstance(plan, dict)
    preflight_hash = canonical_payload(preflight).content_hash
    detail["preflight_hash"] = str(preflight_hash)
    plan["preflight_hash"] = str(preflight_hash)
    detail["plan_hash"] = str(canonical_payload(plan).content_hash)
    replacement = canonical_payload(detail)
    connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
    connection.execute(
        """
        UPDATE experiment_status_event SET detail_json=?, detail_hash=?
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (
            replacement.json_bytes.decode("utf-8"),
            str(replacement.content_hash),
            str(experiment_id),
        ),
    )
    connection.commit()


def test_rehashed_research_only_status_cannot_impersonate_ready(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    writer = SQLiteExperimentWriter(database)
    launch, lease = _persist_candidate_selection(
        writer,
        database,
        preflight_status="research_only",
        preflight_eligibility="research_only",
    )
    assert lease is not None
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT detail_json FROM experiment_status_event
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert event is not None
    detail = json.loads(event["detail_json"])
    detail["preflight"]["status"] = "ready"
    _rewrite_preflight_event(connection, launch.experiment_id, detail)

    with pytest.raises(ExperimentIntegrityError):
        _claim(writer, lease)

    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    database.close_all()


def test_rehashed_incomplete_hard_gate_set_cannot_consume_holdout(
    tmp_path: Path,
) -> None:
    database, _reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT detail_json FROM experiment_status_event
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert event is not None
    detail = json.loads(event["detail_json"])
    checks = detail["preflight"]["checks"]
    certification_index = next(
        index
        for index, check in enumerate(checks)
        if check["rule_id"] == "certification"
    )
    holdout_window = DateWindow(date(2026, 3, 1), date(2026, 3, 28))
    certification_gate = replace(
        _gates(
            launch,
            snapshot_manifest_hash="5" * 64,
            certified_cutoff=holdout_window.end,
            holdout_window=holdout_window,
        )[certification_index],
        evaluation_id=f"{launch.experiment_id}:preflight:1:certification",
    )
    detail["preflight"]["checks"] = [checks[certification_index]]
    detail["plan_preimage"]["gate_payload_hashes"] = [
        str(certification_gate.payload_hash)
    ]
    connection.execute("DROP TRIGGER trg_gate_evaluation_no_update")
    connection.execute("DROP TRIGGER trg_gate_evaluation_no_delete")
    connection.execute(
        """
        DELETE FROM gate_evaluation
        WHERE experiment_id=? AND rule_id<>'certification'
        """,
        (str(launch.experiment_id),),
    )
    connection.execute(
        """
        UPDATE gate_evaluation SET evaluation_id=?, payload_hash=?
        WHERE experiment_id=? AND rule_id='certification'
        """,
        (
            certification_gate.evaluation_id,
            str(certification_gate.payload_hash),
            str(launch.experiment_id),
        ),
    )
    connection.commit()
    _rewrite_preflight_event(connection, launch.experiment_id, detail)

    with pytest.raises(ExperimentIntegrityError):
        _claim(writer, lease)

    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    database.close_all()


def test_rehashed_non_holdout_fold_semantic_drift_cannot_consume_holdout(
    tmp_path: Path,
) -> None:
    database, _reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT detail_json FROM experiment_status_event
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert event is not None
    detail = json.loads(event["detail_json"])
    target = connection.execute(
        """
        SELECT * FROM experiment_fold
        WHERE experiment_id=? AND candidate_id='candidate-1'
          AND fold_role='exploration'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert target is not None
    drifted = FoldPersistenceSpec.create(
        key=FoldKey(
            launch.experiment_id,
            CandidateId(target["candidate_id"]),
            FoldId(target["fold_id"]),
        ),
        ordinal=target["ordinal"],
        fold_role=FoldRole.EXPLORATION,
        train_window=None,
        test_window=DateWindow(date(2026, 1, 2), date(2026, 1, 28)),
        purge_sessions=target["purge_sessions"],
        embargo_sessions=target["embargo_sessions"],
    )
    ordered_rows = connection.execute(
        """
        SELECT candidate_id, ordinal, fold_id FROM experiment_fold
        WHERE experiment_id=? ORDER BY candidate_id, ordinal, fold_id
        """,
        (str(launch.experiment_id),),
    ).fetchall()
    target_index = next(
        index
        for index, row in enumerate(ordered_rows)
        if row["candidate_id"] == target["candidate_id"]
        and row["fold_id"] == target["fold_id"]
    )
    detail["plan_preimage"]["fold_payload_hashes"][target_index] = str(
        drifted.payload_hash
    )
    connection.execute("DROP TRIGGER trg_experiment_fold_guard_update")
    connection.execute(
        """
        UPDATE experiment_fold
        SET test_start=?, fold_spec_json=?, fold_spec_hash=?
        WHERE experiment_id=? AND candidate_id=? AND fold_id=?
        """,
        (
            drifted.test_window.start.isoformat(),
            drifted.canonical_payload.decode("utf-8"),
            str(drifted.payload_hash),
            str(launch.experiment_id),
            target["candidate_id"],
            target["fold_id"],
        ),
    )
    connection.commit()
    _rewrite_preflight_event(connection, launch.experiment_id, detail)

    with pytest.raises(ExperimentIntegrityError):
        _claim(writer, lease)

    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    database.close_all()


@pytest.mark.parametrize("rewrite_check", [False, True])
def test_rehashed_snapshot_manifest_substitution_cannot_consume_holdout(
    tmp_path: Path,
    rewrite_check: bool,
) -> None:
    database, _reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT detail_json FROM experiment_status_event
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert event is not None
    detail = json.loads(event["detail_json"])
    preflight = detail["preflight"]
    plan = detail["plan_preimage"]
    replacement_manifest = "0" * 64
    preflight["identities"]["snapshot_identity"]["manifest_hash"] = replacement_manifest
    preflight["authority"]["snapshot_identity"]["manifest_hash"] = replacement_manifest
    preflight["identities"]["certification"]["snapshot_evidence"]["manifest_hash"] = (
        replacement_manifest
    )
    plan["snapshot_evidence"]["manifest_hash"] = replacement_manifest
    if rewrite_check:
        certification_check = next(
            check
            for check in preflight["checks"]
            if check["rule_id"] == "certification"
        )
        certification_check["observed"]["snapshot_evidence"]["manifest_hash"] = (
            replacement_manifest
        )
        certification_check["policy"]["snapshot_identity"]["manifest_hash"] = (
            replacement_manifest
        )
    _rewrite_preflight_event(connection, launch.experiment_id, detail)

    with pytest.raises(ExperimentIntegrityError):
        _claim(writer, lease)

    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    database.close_all()


@pytest.mark.parametrize("drift", ["launch", "fold", "gate", "cycle", "snapshot"])
def test_structurally_valid_preflight_linkage_drift_cannot_consume_holdout(
    tmp_path: Path,
    drift: str,
) -> None:
    database, _reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    event = connection.execute(
        """
        SELECT detail_json FROM experiment_status_event
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (str(launch.experiment_id),),
    ).fetchone()
    assert event is not None
    detail = json.loads(event["detail_json"])
    preflight = detail["preflight"]
    plan = detail["plan_preimage"]
    if drift == "launch":
        plan["launch_spec_hash"] = "0" * 64
    elif drift == "fold":
        plan["fold_payload_hashes"][0] = "0" * 64
    elif drift == "gate":
        plan["gate_payload_hashes"][0] = "0" * 64
    elif drift == "cycle":
        preflight["identities"]["research_cycle_id"] = "cycle-linkage-drift"
        plan["research_cycle_id"] = "cycle-linkage-drift"
    else:
        replacement_snapshot_id = "snapshot-linkage-drift"
        preflight["identities"]["snapshot_identity"]["snapshot_id"] = (
            replacement_snapshot_id
        )
        preflight["authority"]["snapshot_identity"]["snapshot_id"] = (
            replacement_snapshot_id
        )
        preflight["identities"]["certification"]["snapshot_evidence"]["snapshot_id"] = (
            replacement_snapshot_id
        )
        plan["snapshot_evidence"]["snapshot_id"] = replacement_snapshot_id
    preflight_hash = canonical_payload(preflight).content_hash
    detail["preflight_hash"] = str(preflight_hash)
    plan["preflight_hash"] = str(preflight_hash)
    detail["plan_hash"] = str(canonical_payload(plan).content_hash)
    replacement = canonical_payload(detail)
    connection.execute("DROP TRIGGER trg_experiment_status_event_no_update")
    connection.execute(
        """
        UPDATE experiment_status_event SET detail_json=?, detail_hash=?
        WHERE experiment_id=? AND reason_code='preflight_passed'
        """,
        (
            replacement.json_bytes.decode("utf-8"),
            str(replacement.content_hash),
            str(launch.experiment_id),
        ),
    )
    connection.commit()

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        _claim(writer, lease)

    assert (
        exc_info.value.details["reason_code"] == "holdout_preflight_authority_invalid"
    )
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0
    database.close_all()


@pytest.mark.parametrize(
    "failure_point",
    ["stage_cas", "experiment_event", "unselected_fold_event"],
)
def test_failure_after_insert_rolls_back_every_claim_side_effect(
    tmp_path: Path,
    failure_point: str,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    if failure_point == "stage_cas":
        connection.execute(
            """
            CREATE TRIGGER abort_holdout_stage
            BEFORE UPDATE OF stage ON experiment
            WHEN NEW.stage='holdout'
            BEGIN SELECT RAISE(ABORT, 'injected stage failure'); END
            """
        )
    elif failure_point == "experiment_event":
        connection.execute(
            """
            CREATE TRIGGER abort_holdout_event
            BEFORE INSERT ON experiment_status_event
            WHEN NEW.stage='holdout'
            BEGIN SELECT RAISE(ABORT, 'injected event failure'); END
            """
        )
    else:
        connection.execute(
            """
            CREATE TRIGGER abort_unselected_holdout_event
            BEFORE INSERT ON experiment_status_event
            WHEN NEW.subject_type='fold'
             AND NEW.reason_code='holdout_candidate_not_selected'
            BEGIN SELECT RAISE(ABORT, 'injected cancellation event failure'); END
            """
        )
    connection.commit()
    before_events = len(reader.list_status_events(launch.experiment_id))

    with pytest.raises(ExperimentPersistenceError):
        _claim(writer, lease)

    projection = reader.get_experiment_projection(launch.experiment_id)
    assert projection is not None
    assert projection.record.stage is ExperimentStage.CANDIDATE_SELECTION
    assert projection.revision == 4
    assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is None
    assert len(reader.list_status_events(launch.experiment_id)) == before_events
    assert all(
        fold.projection.status is ExperimentStatus.QUEUED
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
    )
    database.close_all()


def test_unexpected_python_failure_rolls_back_every_claim_side_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    before_events = len(reader.list_status_events(launch.experiment_id))

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected Python failure")

    monkeypatch.setattr(SQLiteExperimentWriter, "_cancel_unselected", explode)

    with pytest.raises(RuntimeError, match="injected Python failure"):
        _claim(writer, lease)

    assert not connection.in_transaction
    assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is None
    projection = reader.get_experiment_projection(launch.experiment_id)
    assert projection is not None
    assert projection.record.stage is ExperimentStage.CANDIDATE_SELECTION
    assert projection.revision == 4
    assert len(reader.list_status_events(launch.experiment_id)) == before_events
    database.close_all()


@pytest.mark.parametrize("drift", ["missing", "duplicate"])
def test_claim_rejects_holdout_fold_cardinality_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    database, reader, writer, launch, lease = _store(tmp_path)
    connection = database.get_connection()
    unselected = next(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and fold.spec.key.candidate_id == CandidateId("candidate-1")
    )
    if drift == "missing":
        connection.execute("DROP TRIGGER trg_experiment_status_event_no_delete")
        connection.execute("DROP TRIGGER trg_experiment_fold_no_delete")
        connection.execute(
            """
            DELETE FROM experiment_status_event
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            """,
            (
                str(unselected.spec.key.experiment_id),
                str(unselected.spec.key.candidate_id),
                str(unselected.spec.key.fold_id),
            ),
        )
        connection.execute(
            """
            DELETE FROM experiment_fold
            WHERE experiment_id=? AND candidate_id=? AND fold_id=?
            """,
            (
                str(unselected.spec.key.experiment_id),
                str(unselected.spec.key.candidate_id),
                str(unselected.spec.key.fold_id),
            ),
        )
    else:
        train_window = unselected.spec.train_window
        assert train_window is not None
        key = FoldKey(
            launch.experiment_id,
            CandidateId("candidate-1"),
            FoldId("fold-1-extra-holdout"),
        )
        extra = FoldPersistenceSpec.create(
            key,
            4,
            FoldRole.HOLDOUT,
            train_window,
            unselected.spec.test_window,
            unselected.spec.purge_sessions,
            unselected.spec.embargo_sessions,
        )
        connection.execute(
            """
            INSERT INTO experiment_fold(
                experiment_id, candidate_id, fold_id, ordinal, fold_role,
                train_start, train_end, test_start, test_end, purge_sessions,
                embargo_sessions, fold_spec_json, fold_spec_hash, status,
                claim_owner_token, created_at_epoch_us, updated_at_epoch_us, revision
            ) VALUES (?, ?, ?, ?, 'holdout', ?, ?, ?, ?, ?, ?, ?, ?, 'queued',
                      NULL, ?, ?, 0)
            """,
            (
                str(key.experiment_id),
                str(key.candidate_id),
                str(key.fold_id),
                extra.ordinal,
                train_window.start.isoformat(),
                train_window.end.isoformat(),
                extra.test_window.start.isoformat(),
                extra.test_window.end.isoformat(),
                extra.purge_sessions,
                extra.embargo_sessions,
                extra.canonical_payload.decode("utf-8"),
                str(extra.payload_hash),
                NOW_US,
                NOW_US,
            ),
        )
    connection.commit()

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        _claim(writer, lease)

    assert exc_info.value.details["reason_code"] == "holdout_fold_cardinality_drift"
    assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is None
    database.close_all()


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


def _selection_ledger(
    launch: ExperimentLaunchSpec,
    *,
    failed_candidate_ids: frozenset[str] = frozenset(),
) -> TrialLedger:
    lineage = MetricEvidenceLineage(
        ("comparison://holdout-integration",),
        (ContentHash("6" * 64),),
    )
    outcomes = []
    for candidate in launch.candidates:
        trial = launch.promotion_objective.trial_family.current_members[
            candidate.ordinal - 1
        ]
        if str(candidate.candidate_id) in failed_candidate_ids:
            outcomes.append(
                TrialOutcome(
                    trial=trial,
                    status=TrialStatus.FAILED,
                    metrics={},
                    holdout_metrics={},
                    source_projection_hash=ContentHash("7" * 64),
                    failure_reason="candidate_failed",
                )
            )
        else:
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
    def __init__(
        self,
        launch: ExperimentLaunchSpec,
        *,
        failed_candidate_ids: frozenset[str] = frozenset(),
    ) -> None:
        self.ledger = _selection_ledger(
            launch,
            failed_candidate_ids=failed_candidate_ids,
        )

    def load_selection_evidence(self, _experiment_id: ExperimentId) -> TrialLedger:
        return self.ledger


def _application_request(ledger: TrialLedger) -> Any:
    api = _holdout_api()
    return api.ClaimHoldoutCandidateRequest(
        experiment_id="experiment-1",
        candidate_id="candidate-2",
        expected_revision=4,
        expected_selection_evidence_hash=str(ledger.content_hash),
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=api.ApplicationSelectionReason(
            "objective_review",
            "Candidate won the registered objective review.",
        ),
        occurred_at=NOW,
    )


def _owned_coordinator(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    *,
    factory: _Factory | None = None,
) -> tuple[
    ExperimentExecutionCoordinator,
    ExperimentSchedulerStore,
    _SelectionProvider,
]:
    store = ExperimentSchedulerStore(reader, writer)
    provider = _SelectionProvider(launch)
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=factory or _Factory(),
        selection_evidence_provider=provider,
        owner_token="holdout-acceptance-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
    )
    assert (
        coordinator.tick(occurred_at=NOW).state
        is SchedulerTickState.CANDIDATE_SELECTION
    )
    return coordinator, store, provider


def test_failed_candidate_isolation_preserves_remaining_holdout_claim_lifecycle(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    launch, lease = _persist_candidate_selection(
        writer,
        database,
        fail_walk_forward_candidate_id="candidate-2",
    )
    assert lease is not None
    provider = _SelectionProvider(
        launch,
        failed_candidate_ids=frozenset({"candidate-2"}),
    )
    coordinator = ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(reader, writer),
        first_attempt_factory=_Factory(),
        selection_evidence_provider=provider,
        owner_token="holdout-isolation-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
    )

    advanced = coordinator.tick(occurred_at=NOW + timedelta(minutes=2))
    failed_request = replace(
        _application_request(provider.ledger),
        occurred_at=NOW + timedelta(minutes=2, seconds=1),
    )
    with pytest.raises(AppProcessError):
        coordinator.claim_holdout_candidate(failed_request)
    receipt = coordinator.claim_holdout_candidate(
        replace(failed_request, candidate_id="candidate-1")
    )
    dispatched = coordinator.tick(occurred_at=NOW + timedelta(minutes=2, seconds=2))

    failed_holdout = next(
        fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and fold.spec.key.candidate_id == CandidateId("candidate-2")
    )
    isolation_events = tuple(
        event
        for event in reader.list_status_events(launch.experiment_id)
        if event.reason_code == "candidate_isolated_after_failure"
        and event.fold_id == failed_holdout.spec.key.fold_id
    )
    assert advanced.state is SchedulerTickState.CANDIDATE_SELECTION
    assert receipt.candidate_id == "candidate-1"
    assert failed_holdout.projection.status is ExperimentStatus.CANCELLED
    assert len(isolation_events) == 1
    assert dispatched.state is SchedulerTickState.DISPATCHED
    assert len(dispatched.dispatches) == 1
    assert dispatched.dispatches[0].fold.spec.key.candidate_id == CandidateId(
        "candidate-1"
    )
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


class _FailOnceNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime]] = []

    def notify_scheduler(
        self,
        *,
        experiment_id: str,
        action: str,
        occurred_at: datetime,
    ) -> None:
        self.calls.append((experiment_id, action, occurred_at))
        if len(self.calls) == 1:
            raise RuntimeError("injected scheduler wake failure")


def test_real_handler_replays_committed_claim_and_renotifies_after_failure(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, _store_facade, provider = _owned_coordinator(reader, writer, launch)
    notifier = _FailOnceNotifier()
    handler = ClaimHoldoutCandidateHandler(process=coordinator, notifier=notifier)
    command = ClaimHoldoutCandidateCommand(_application_request(provider.ledger))

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(command)

    connection = database.get_connection()
    assert exc_info.value.details["claim_id"].startswith("holdout:")
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 1
    before_replay = connection.total_changes

    receipt = handler.handle(command)

    assert receipt.claim_id == exc_info.value.details["claim_id"]
    assert connection.total_changes == before_replay
    assert notifier.calls == [
        ("experiment-1", "holdout_claimed", NOW),
        ("experiment-1", "holdout_claimed", NOW),
    ]
    database.close_all()


def test_real_handler_normalizes_tampered_claim_snapshot_integrity(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, _store_facade, provider = _owned_coordinator(reader, writer, launch)
    request = _application_request(provider.ledger)
    coordinator.claim_holdout_candidate(request)
    persisted = reader.get_holdout_claim_for_experiment(launch.experiment_id)
    assert persisted is not None
    drifted = replace(persisted, logical_run_id="drifted-logical-run")
    connection = database.get_connection()
    connection.execute("DROP TRIGGER trg_holdout_claim_no_update")
    connection.execute(
        """
        UPDATE holdout_claim SET logical_run_id=?, claim_payload_hash=?
        WHERE experiment_id=?
        """,
        (
            drifted.logical_run_id,
            str(drifted.claim_payload_hash),
            str(launch.experiment_id),
        ),
    )
    connection.commit()
    notifier = _FailOnceNotifier()
    handler = ClaimHoldoutCandidateHandler(process=coordinator, notifier=notifier)

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(ClaimHoldoutCandidateCommand(request))

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == "holdout_claim_derived_identity_drift"
    assert notifier.calls == []
    database.close_all()


def test_same_cycle_clone_conflicts_before_lease_or_moving_dependencies(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, _store_facade, provider = _owned_coordinator(reader, writer, launch)
    original = coordinator.claim_holdout_candidate(
        _application_request(provider.ledger)
    )
    clone, _clone_lease = _persist_candidate_selection(
        writer,
        database,
        experiment_id="experiment-clone",
        acquire_lease=False,
    )
    clone_coordinator = ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(reader, writer),
        first_attempt_factory=_Factory("9" * 64),
        selection_evidence_provider=None,
        owner_token="clone-without-lease",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
    )
    api = _holdout_api()
    request = api.ClaimHoldoutCandidateRequest(
        experiment_id=str(clone.experiment_id),
        candidate_id="candidate-2",
        expected_revision=1,
        expected_selection_evidence_hash="9" * 64,
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=api.ApplicationSelectionReason(
            "objective_review",
            "Candidate won the registered objective review.",
        ),
        occurred_at=NOW,
    )
    connection = database.get_connection()
    before_conflict = connection.total_changes

    with pytest.raises(AppProcessError) as exc_info:
        clone_coordinator.claim_holdout_candidate(request)

    assert exc_info.value.details["code"] == "HOLDOUT_ALREADY_CLAIMED"
    assert exc_info.value.details["reason"] == "holdout_claim_replay_drift"
    assert exc_info.value.details["claim_id"] == original.claim_id
    assert connection.total_changes == before_conflict
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 1
    database.close_all()


def test_coordinator_dispatches_only_claimed_holdout_after_atomic_commit(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    # The fixture lease expires; the coordinator legally reclaims the same occupant.
    connection = database.get_connection()
    store = ExperimentSchedulerStore(reader, writer)
    provider = _SelectionProvider(launch)
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_Factory(),
        selection_evidence_provider=provider,
        owner_token="holdout-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
    )

    gated = coordinator.tick(occurred_at=NOW)
    receipt = coordinator.claim_holdout_candidate(_application_request(provider.ledger))
    dispatched = coordinator.tick(occurred_at=NOW + timedelta(seconds=2))

    assert gated.state is SchedulerTickState.CANDIDATE_SELECTION
    assert receipt.candidate_id == "candidate-2"
    assert dispatched.state is SchedulerTickState.DISPATCHED
    assert len(dispatched.dispatches) == 1
    assert dispatched.dispatches[0].fold.spec.key.candidate_id == CandidateId(
        "candidate-2"
    )
    assert dispatched.dispatches[0].attempt.spec.reproduction_fingerprint == (
        ContentHash("4" * 64)
    )
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 1
    database.close_all()


def test_dispatch_fails_closed_when_resolved_fingerprint_drifts_after_claim(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    connection = database.get_connection()
    factory = _Factory()
    provider = _SelectionProvider(launch)
    coordinator = ExperimentExecutionCoordinator(
        store=ExperimentSchedulerStore(reader, writer),
        first_attempt_factory=factory,
        selection_evidence_provider=provider,
        owner_token="holdout-drift-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW + timedelta(minutes=2),
    )
    coordinator.tick(occurred_at=NOW)
    coordinator.claim_holdout_candidate(_application_request(provider.ledger))
    factory.fingerprint = "9" * 64

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.tick(occurred_at=NOW + timedelta(seconds=2))

    assert exc_info.value.details["reason"] == "holdout_claim_fingerprint_mismatch"
    assert (
        connection.execute(
            """
            SELECT count(*) FROM experiment_attempt AS attempt
            JOIN experiment_fold AS fold
              ON fold.experiment_id=attempt.experiment_id
             AND fold.candidate_id=attempt.candidate_id
             AND fold.fold_id=attempt.fold_id
            WHERE fold.fold_role='holdout'
            """
        ).fetchone()[0]
        == 0
    )
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 1
    database.close_all()


def test_system_retry_preserves_claim_logical_run_and_fingerprint(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, store, provider = _owned_coordinator(reader, writer, launch)
    coordinator.claim_holdout_candidate(_application_request(provider.ledger))
    dispatched = coordinator.tick(occurred_at=NOW + timedelta(seconds=1))
    dispatch = dispatched.dispatches[0]
    coordinator.start_attempt(dispatch, occurred_at=NOW + timedelta(seconds=2))
    coordinator.fail_attempt(
        dispatch.attempt.spec.attempt_id,
        ExperimentFailureCode.SYSTEM_ERROR,
        occurred_at=NOW + timedelta(seconds=3),
    )
    failed = store.load_snapshot(launch.experiment_id)
    original_claim = failed.holdout_claim
    selected = next(
        fold
        for fold in failed.folds
        if str(fold.spec.key.fold_id) == original_claim.fold_id
    )

    coordinator.retry_fold(
        experiment_id=str(launch.experiment_id),
        candidate_id=original_claim.candidate_id,
        fold_id=original_claim.fold_id,
        expected_revision=selected.projection.revision,
        occurred_at=NOW + timedelta(seconds=4),
    )
    retried = coordinator.tick(occurred_at=NOW + timedelta(seconds=5))
    refreshed = store.load_snapshot(launch.experiment_id)
    retry_attempts = tuple(
        attempt
        for attempt in refreshed.attempts
        if str(attempt.spec.fold_key.fold_id) == original_claim.fold_id
    )

    assert retried.state is SchedulerTickState.DISPATCHED
    assert len(retry_attempts) == 2
    assert retry_attempts[1].spec.parent_attempt_id == retry_attempts[0].spec.attempt_id
    assert {
        str(attempt.spec.reproduction_fingerprint) for attempt in retry_attempts
    } == {original_claim.reproduction_fingerprint}
    assert refreshed.holdout_claim.logical_run_id == original_claim.logical_run_id
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


def test_terminal_holdout_failure_cannot_reselect_or_bypass_retry_rules(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, store, provider = _owned_coordinator(reader, writer, launch)
    request = _application_request(provider.ledger)
    original = coordinator.claim_holdout_candidate(request)
    dispatch = coordinator.tick(occurred_at=NOW + timedelta(seconds=1)).dispatches[0]
    coordinator.start_attempt(dispatch, occurred_at=NOW + timedelta(seconds=2))
    coordinator.fail_attempt(
        dispatch.attempt.spec.attempt_id,
        ExperimentFailureCode.CANDIDATE_FAILED,
        occurred_at=NOW + timedelta(seconds=3),
    )
    failed = store.load_snapshot(launch.experiment_id)
    selected = next(
        fold for fold in failed.folds if str(fold.spec.key.fold_id) == original.fold_id
    )
    unselected = next(
        fold
        for fold in failed.folds
        if fold.spec.fold_role is FoldRole.HOLDOUT
        and str(fold.spec.key.fold_id) != original.fold_id
    )

    with pytest.raises(AppProcessError) as reselect_error:
        coordinator.claim_holdout_candidate(
            replace(request, candidate_id="candidate-1")
        )
    with pytest.raises(AppProcessError) as selected_retry_error:
        coordinator.retry_fold(
            experiment_id=str(launch.experiment_id),
            candidate_id=original.candidate_id,
            fold_id=original.fold_id,
            expected_revision=selected.projection.revision,
            occurred_at=NOW + timedelta(seconds=4),
        )
    with pytest.raises(AppProcessError) as unselected_retry_error:
        coordinator.retry_fold(
            experiment_id=str(launch.experiment_id),
            candidate_id=str(unselected.spec.key.candidate_id),
            fold_id=str(unselected.spec.key.fold_id),
            expected_revision=unselected.projection.revision,
            occurred_at=NOW + timedelta(seconds=5),
        )

    assert reselect_error.value.details["reason"] == "holdout_claim_replay_drift"
    assert (
        selected_retry_error.value.details["reason"]
        == "terminal_fold_retry_failure_not_retryable"
    )
    assert (
        unselected_retry_error.value.details["reason"]
        == "terminal_fold_retry_requires_failed_fold"
    )
    refreshed = store.load_snapshot(launch.experiment_id)
    assert refreshed.holdout_claim.claim_id == original.claim_id
    assert (
        database.get_connection()
        .execute("SELECT count(*) FROM holdout_claim")
        .fetchone()[0]
        == 1
    )
    database.close_all()


def test_selected_holdout_completion_advances_scheduler_to_evidence(
    tmp_path: Path,
) -> None:
    database, reader, writer, launch, _lease = _store(tmp_path)
    coordinator, store, provider = _owned_coordinator(reader, writer, launch)
    coordinator.claim_holdout_candidate(_application_request(provider.ledger))
    dispatch = coordinator.tick(occurred_at=NOW + timedelta(seconds=1)).dispatches[0]
    coordinator.start_attempt(dispatch, occurred_at=NOW + timedelta(seconds=2))
    coordinator.complete_attempt(
        dispatch.attempt.spec.attempt_id,
        occurred_at=NOW + timedelta(seconds=3),
    )

    result = coordinator.tick(occurred_at=NOW + timedelta(seconds=4))
    refreshed = store.load_snapshot(launch.experiment_id)

    assert result.state is SchedulerTickState.WAITING
    assert result.dispatches == ()
    assert refreshed.projection.record.stage is ExperimentStage.EVIDENCE
    assert refreshed.projection.record.status is ExperimentStatus.RUNNING
    database.close_all()
