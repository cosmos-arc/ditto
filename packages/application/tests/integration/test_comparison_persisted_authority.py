"""Fresh-tmp SQLite proof for the R3 comparison execution authority seam."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
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
    LeaseFence,
    LogicalTrialIdentity,
    ResearchCycleIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    SnapshotId,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
    canonical_payload,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence
from ditto_analysis.experiments.trial_ledger import (
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_analysis.research.artifact_measurement import measure_json_bytes
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._report_evidence import (
    BACKTEST_REPORT_ARTIFACT_KIND,
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
    LoadedBacktestReportArtifact,
)
from ditto_application.processes.experiments.comparison import (
    CandidateFoldEvidence,
    load_persisted_fold_execution,
)
from ditto_backtest.statistics import (
    BacktestReport,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
)

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)
EXPERIMENT_ID = ExperimentId("experiment-comparison-authority")
CANDIDATE_ID = CandidateId("candidate-baseline")
FINGERPRINT = ContentHash("f" * 64)


def _launch() -> ExperimentLaunchSpec:
    candidate = CandidateSpec(CANDIDATE_ID, 1, True, {"lookback": 20})
    return ExperimentLaunchSpec(
        experiment_id=EXPERIMENT_ID,
        strategy_version=StrategyVersion("comparison-authority@1"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-comparison-authority"),
        candidates=(candidate,),
        execution_bindings=(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash("b" * 64),
            ),
        ),
        promotion_objective=PromotionObjective(
            ObjectiveMetric(
                ResearchMetricId.NET_RETURN,
                ResearchMetricDirection.MAXIMIZE,
            ),
            (),
            (),
            CANDIDATE_ID,
            "Prove comparison authority through SQLite.",
            TrialFamilyDeclaration(
                "comparison-authority-family",
                (
                    LogicalTrialIdentity(
                        EXPERIMENT_ID,
                        CANDIDATE_ID,
                        1,
                        candidate.parameter_hash,
                        TrialKind.CURRENT,
                    ),
                ),
            ),
        ),
        fold_protocol=FoldProtocolSpec(
            "r3-walk-forward",
            1,
            ContentHash("c" * 64),
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(8, 128),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _fold_specs() -> tuple[FoldPersistenceSpec, FoldPersistenceSpec]:
    return tuple(
        FoldPersistenceSpec.create(
            FoldKey(EXPERIMENT_ID, CANDIDATE_ID, FoldId(f"wf-{ordinal}")),
            ordinal,
            FoldRole.WALK_FORWARD,
            DateWindow(date(2023, 1, 1), date(2023, 12, 31)),
            DateWindow(date(2024, ordinal, 1), date(2024, ordinal, 2)),
            2,
            1,
        )
        for ordinal in (1, 2)
    )


def _running_store(
    tmp_path: Path,
) -> tuple[
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
    LeaseFence,
    tuple[FoldPersistenceSpec, FoldPersistenceSpec],
]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    launch = _launch()
    writer.create_experiment(
        ResearchCycleIdentity("cycle-comparison-authority", ContentHash("d" * 64)),
        launch,
        ExperimentRecord(
            EXPERIMENT_ID,
            ExperimentStatus.DRAFT,
            ExperimentDesiredState.RUN,
            ExperimentStage.PREFLIGHT,
            NOW,
        ),
    )
    folds = _fold_specs()
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
    queued = writer.enqueue_experiment(
        EXPERIMENT_ID,
        expected_revision=0,
        occurred_at=NOW,
        reason_code="preflight_passed",
        detail={},
        launch_fence=ExperimentEnqueueFence.create(gates=(), folds=folds),
    )
    lease = writer.try_claim_lease(
        EXPERIMENT_ID,
        "comparison-authority-owner",
        expected_revision=0,
        now_epoch_us=NOW_US,
        lease_until_epoch_us=NOW_US + 60_000_000,
    )
    assert lease is not None
    writer.transition_scheduled_experiment(
        EXPERIMENT_ID,
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
    return database, reader, writer, lease.fence, folds


def _start_attempt(
    writer: SQLiteExperimentWriter,
    fence: LeaseFence,
    fold: FoldPersistenceSpec,
) -> tuple[AttemptId, BacktestRunId, FoldProjection, AttemptProjection]:
    attempt_id = AttemptId(f"attempt-{fold.key.fold_id}")
    run_id = BacktestRunId(f"run-{fold.key.fold_id}")
    spec = AttemptPersistenceSpec(
        attempt_id,
        fold.key,
        1,
        None,
        None,
        FINGERPRINT,
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
    running_fold, _queued_attempt = writer.claim_fold_and_add_attempt(
        fold.key,
        spec,
        initial,
        expected_fold_revision=0,
        lease_fence=fence,
        now_epoch_us=NOW_US + 2,
        occurred_at=NOW,
    )
    running_attempt = writer.transition_attempt(
        attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=0,
        lease_fence=fence,
        now_epoch_us=NOW_US + 3,
        occurred_at=NOW,
        reason_code="attempt_started",
        detail={},
    )
    return attempt_id, run_id, running_fold, running_attempt


def _complete_attempt(
    writer: SQLiteExperimentWriter,
    fence: LeaseFence,
    fold: FoldPersistenceSpec,
    attempt_id: AttemptId,
    run_id: BacktestRunId,
    running_fold: FoldProjection,
    running_attempt: AttemptProjection,
) -> None:
    writer.transition_attempt(
        attempt_id,
        target_status=ExperimentStatus.COMPLETED,
        backtest_run_id=run_id,
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=running_attempt.revision,
        lease_fence=fence,
        now_epoch_us=NOW_US + 4,
        occurred_at=NOW,
        reason_code="attempt_completed",
        detail={},
    )
    writer.transition_fold(
        fold.key,
        target_status=ExperimentStatus.COMPLETED,
        claim_owner_token=None,
        failure_code=None,
        expected_revision=running_fold.revision,
        lease_fence=fence,
        now_epoch_us=NOW_US + 5,
        occurred_at=NOW,
        reason_code="fold_completed",
        detail={},
    )


def _persist_completed_attempt(
    writer: SQLiteExperimentWriter,
    fence: LeaseFence,
    fold: FoldPersistenceSpec,
) -> tuple[AttemptId, BacktestRunId]:
    attempt_id, run_id, running_fold, running_attempt = _start_attempt(
        writer,
        fence,
        fold,
    )
    _complete_attempt(
        writer,
        fence,
        fold,
        attempt_id,
        run_id,
        running_fold,
        running_attempt,
    )
    return attempt_id, run_id


def _report(run_id: str, fold: FoldPersistenceSpec) -> BacktestReport:
    return BacktestReport(
        run_id=run_id,
        period=(fold.test_window.start.isoformat(), fold.test_window.end.isoformat()),
        initial_cash=100.0,
        final_nav=101.0,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=empty_aggregated_trade_statistics(),
        alpha_stats=empty_alpha_statistics(),
        nav_series=(
            (fold.test_window.start.isoformat(), 100.0),
            (fold.test_window.end.isoformat(), 101.0),
        ),
        trade_log=(),
        fill_log=(),
    )


def test_loader_binds_terminal_execution_read_from_fresh_sqlite(
    tmp_path: Path,
) -> None:
    database, reader, writer, fence, folds = _running_store(tmp_path)
    attempt_id, run_id = _persist_completed_attempt(writer, fence, folds[0])

    binding = load_persisted_fold_execution(reader, folds[0].key, attempt_id)

    assert binding.experiment_id == EXPERIMENT_ID
    assert binding.candidate_id == CANDIDATE_ID
    assert binding.fold_id == folds[0].key.fold_id
    assert binding.fold_ordinal == folds[0].ordinal
    assert binding.test_window == folds[0].test_window
    assert binding.attempt_id == attempt_id
    assert binding.run_id == run_id
    assert binding.reproduction_fingerprint == FINGERPRINT
    database.close_all()


def test_loader_rejects_missing_or_nonterminal_sqlite_execution(
    tmp_path: Path,
) -> None:
    database, reader, writer, fence, folds = _running_store(tmp_path)

    with pytest.raises(AppProcessError) as missing_exc:
        load_persisted_fold_execution(
            reader,
            folds[0].key,
            AttemptId("attempt-missing"),
        )
    assert missing_exc.value.details["reason"] == "persisted_execution_not_found"

    attempt_id, _run_id, _running_fold, _running_attempt = _start_attempt(
        writer,
        fence,
        folds[0],
    )
    with pytest.raises(AppProcessError) as nonterminal_exc:
        load_persisted_fold_execution(reader, folds[0].key, attempt_id)
    assert nonterminal_exc.value.details["reason"] == "persisted_attempt_lineage_drift"
    database.close_all()


def test_loader_rejects_cross_fold_attempt_lineage_from_sqlite(
    tmp_path: Path,
) -> None:
    database, reader, writer, fence, folds = _running_store(tmp_path)
    first_attempt_id, _first_run = _persist_completed_attempt(writer, fence, folds[0])
    second_attempt_id, _second_run = _persist_completed_attempt(writer, fence, folds[1])

    with pytest.raises(AppProcessError) as exc_info:
        load_persisted_fold_execution(reader, folds[0].key, second_attempt_id)

    assert exc_info.value.details["reason"] == "persisted_attempt_lineage_drift"
    assert first_attempt_id != second_attempt_id
    database.close_all()


def test_sqlite_bound_run_identity_rejects_stale_backtest_report(
    tmp_path: Path,
) -> None:
    database, reader, writer, fence, folds = _running_store(tmp_path)
    attempt_id, _run_id = _persist_completed_attempt(writer, fence, folds[0])
    binding = load_persisted_fold_execution(reader, folds[0].key, attempt_id)
    report = _report("run-stale", folds[0])
    evidence = BacktestReportEvidence.from_report(report)
    identity = BacktestReportArtifactIdentity(
        experiment_id=binding.experiment_id,
        candidate_id=binding.candidate_id,
        fold_id=binding.fold_id,
        attempt_id=binding.attempt_id,
        attempt_created_at=binding.attempt_view.spec.created_at,
        run_id=binding.run_id,
        test_window=binding.test_window,
        reproduction_fingerprint=binding.reproduction_fingerprint,
    )
    measurement = measure_json_bytes(
        canonical_payload(evidence.canonical_payload()).json_bytes
    )
    record = ArtifactManifest.create(
        spec=ArtifactPublicationSpec(
            artifact_id=identity.artifact_id,
            experiment_id=identity.experiment_id,
            candidate_id=identity.candidate_id,
            fold_id=identity.fold_id,
            attempt_id=identity.attempt_id,
            artifact_kind=BACKTEST_REPORT_ARTIFACT_KIND,
            relative_path=identity.relative_path,
            reproduction_fingerprint=identity.reproduction_fingerprint,
            audit={
                "attempt_id": str(identity.attempt_id),
                "created_at": identity.attempt_created_at.isoformat(),
                "run_id": str(identity.run_id),
            },
            created_at=identity.attempt_created_at,
        ),
        artifact_format=ArtifactFormat.JSON,
        content_hash=measurement.content_hash,
        schema_hash=measurement.schema_hash,
        row_count=measurement.row_count,
        byte_size=measurement.byte_size,
    ).to_record()
    report_artifact = LoadedBacktestReportArtifact(
        record=record,
        evidence=evidence,
    )

    with pytest.raises(AppProcessError) as exc_info:
        CandidateFoldEvidence(
            execution_binding=binding,
            candidate_ordinal=1,
            snapshot_id=SnapshotId("snapshot-comparison-authority"),
            snapshot_hash=ContentHash("e" * 64),
            parameter_hash=_launch().candidates[0].parameter_hash,
            resolved_spec_hash=ContentHash("b" * 64),
            report_artifact=report_artifact,
        )

    assert exc_info.value.details["reason"] == "report_run_identity_drift"
    database.close_all()
