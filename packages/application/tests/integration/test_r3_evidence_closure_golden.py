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

from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_analysis.experiments import (
    HARD_GATE_RULE_IDS,
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
    FoldKey,
    FoldPersistenceSpec,
    FoldRole,
    FoldView,
    ResearchMetricId,
    encode_launch_spec,
)
from ditto_analysis.experiments.evidence import ReviewPacket, SelectionTraceArtifactRef
from ditto_analysis.experiments.gates import GateLayer, GateOutcome
from ditto_analysis.experiments.trial_ledger import TrialLedger
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.builders.fold_selection_trace_artifact_adapter import (
    IndexedFoldSelectionTraceArtifactAdapter,
)
from ditto_application.builders.research_artifact_loader import (
    IndexedBacktestReportArtifactAdapter,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.commands.candidate_selection import (
    CandidateSelectionProcess,
    CandidateSelectionRequest,
)
from ditto_application.commands.strategy_governance import (
    PublishStrategyVersionCommand,
    PublishStrategyVersionHandler,
    ReactivateStrategyCommand,
    ReactivateStrategyHandler,
    reactivate_confirmation_phrase,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import build_mutation_idempotency
from ditto_application.processes.execution.factor_bridge import (
    FactorBridge,
    build_factor_bundle,
)
from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
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
    CollectedWalkForwardEvidence,
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidenceReader,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
    SchedulerTickState,
)
from ditto_application.processes.experiments.evidence_collector import (
    ExperimentEvidenceCollector,
)
from ditto_application.processes.experiments.execution_bundle import (
    ResearchExecutionSemantics,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
)
from ditto_application.processes.experiments.holdout import (
    HoldoutSelectionReason as ApplicationSelectionReason,
)
from ditto_application.processes.experiments.planning import (
    CandidateMatrixSpec,
    ParameterAxis,
)
from ditto_application.processes.experiments.planning_contracts import (
    declare_trial_family,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
    reconstruct_preflight_report,
)
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    NullR2LiveGateEvidenceReader,
    R2LiveGateEvidenceReader,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
    FirstAttempt,
    QueuedAttempt,
)
from ditto_application.processes.strategy.promotion import StrategyPromotionProcess
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_backtest.data_feed import Slice
from ditto_backtest.statistics import (
    BacktestReport,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
)
from ditto_backtest.steps import StepContext
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.parameters import CandidateParameter, legacy_parameter_path
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.alpha.selection_evidence import (
    SelectionEvidenceCollector,
    SelectionEvidenceLog,
    SelectionExposureApplicability,
    SelectionExposureLane,
)
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)

NOW = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)


class _AdvancingClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        current = self._now
        self._now += timedelta(microseconds=1)
        return current


_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"
_GATE_RULES = ("matrix", "executor", "authority", "history", "certification", "budget")
_REPORT_NAVS = {
    (True, 2): (102.0, 101.0),
    (True, 3): (101.0, 104.0),
    (False, 2): (110.0, 105.0),
    (False, 3): (106.0, 112.0),
}
_SemanticsTransform = Callable[
    [dict[FoldKey, ResearchExecutionSemantics]],
    dict[FoldKey, ResearchExecutionSemantics],
]


def _run_stock_golden_selection_trace(
    *,
    candidate_parameters: tuple[CandidateParameter, ...],
    snapshot_identity: ResearchSnapshotIdentity,
    strategy_version: int,
    trade_date: str,
    run_id: str,
) -> tuple[ResearchStrategyRuntime, SelectionEvidenceLog]:
    """Run the stock golden's real compiler, factor bridge, and strategy pipeline."""
    spec = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    collector = SelectionEvidenceCollector()
    runtime = ResearchRuntimeBuilder().build(
        record=StrategySpecRecord(
            strategy_id=spec.strategy_id,
            name=spec.name,
            spec_json=asdict(spec),
            version=strategy_version,
        ),
        candidate_parameters=candidate_parameters,
        snapshot_identity=snapshot_identity,
        version_status="draft",
        evidence_sink=collector,
    )
    compiled = runtime.compiled_expressions
    assert compiled is not None
    trade_day = date.fromisoformat(trade_date)
    knowledge_date = trade_day - timedelta(days=1)
    instrument_ids = list(range(1, 22))
    bars: dict[InstrumentId, MagicMock] = {}
    history_rows: list[dict[str, object]] = []
    for instrument_id in instrument_ids:
        base = 10.0 + instrument_id
        growth = 0.001 + instrument_id * 0.00005
        for offset in range(26, 1, -1):
            historical_close = base * (1 + growth * (26 - offset))
            history_rows.append(
                {
                    "instrument_id": instrument_id,
                    "trade_date": (trade_day - timedelta(days=offset)).isoformat(),
                    "open": historical_close * 0.99,
                    "high": historical_close * 1.01,
                    "low": historical_close * 0.98,
                    "close": historical_close,
                    "volume": 1_000_000.0,
                }
            )
        close = base * (1 + growth * 25)
        bar = MagicMock()
        bar.open = close * 0.99
        bar.high = close * 1.01
        bar.low = close * 0.98
        bar.close = close
        bar.volume = 1_000_000.0
        bars[InstrumentId(instrument_id)] = bar

    slice_ = MagicMock(spec=Slice)
    slice_.bars = bars
    slice_.benchmark_close = None
    step_context = StepContext(
        time_context=TimeContext(
            decision_time=datetime.combine(
                trade_day,
                datetime.min.time(),
                tzinfo=UTC,
            ),
            knowledge_date=knowledge_date,
            trade_date=trade_date,
        ),
        is_rebalance_day=True,
        bars=bars,
        slice_=slice_,
    )
    data_feed = MagicMock()
    data_feed.get_history.return_value = pl.DataFrame(history_rows)
    data_feed.get_fundamental_snapshot.return_value = pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "roe": [0.05 + instrument_id * 0.005 for instrument_id in instrument_ids],
            "eps": [0.50 + instrument_id * 0.05 for instrument_id in instrument_ids],
            "market_cap": [
                5_000_000_000.0 + instrument_id * 5_000_000_000.0
                for instrument_id in instrument_ids
            ],
        }
    )
    data_feed.get_classification_snapshot.return_value = pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "sector_id": [
                f"sector-{instrument_id % 3}" for instrument_id in instrument_ids
            ],
        },
    )
    bridge = FactorBridge()
    bundle = build_factor_bundle(
        ctx=step_context,
        strategy_id=spec.strategy_id,
        run_id=run_id,
        bridge=bridge,
        compiled=compiled,
        data_feed=data_feed,
        lookback_days=25,
    )
    runtime.pipeline.run(
        StrategyContext(),
        bundle,
    )
    return runtime, collector.snapshot()


def _run_etf_golden_selection_trace(
    *,
    candidate_parameters: tuple[CandidateParameter, ...],
    snapshot_identity: ResearchSnapshotIdentity,
    strategy_version: int,
    trade_date: str,
    run_id: str,
) -> tuple[ResearchStrategyRuntime, SelectionEvidenceLog]:
    """Run the ETF golden through the real compiler, factor bridge, and pipeline."""
    spec = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    collector = SelectionEvidenceCollector()
    runtime = ResearchRuntimeBuilder().build(
        record=StrategySpecRecord(
            strategy_id=spec.strategy_id,
            name=spec.name,
            spec_json=asdict(spec),
            version=strategy_version,
        ),
        candidate_parameters=candidate_parameters,
        snapshot_identity=snapshot_identity,
        version_status="draft",
        evidence_sink=collector,
    )
    compiled = runtime.compiled_expressions
    assert compiled is not None
    trade_day = date.fromisoformat(trade_date)
    knowledge_date = trade_day - timedelta(days=1)
    instrument_ids = list(range(1, 7))
    bars: dict[InstrumentId, MagicMock] = {}
    history_rows: list[dict[str, object]] = []
    for instrument_id in instrument_ids:
        base = 20.0 + instrument_id
        growth = 0.001 + instrument_id * 0.0001
        for offset in range(26, 1, -1):
            historical_close = base * (1 + growth * (26 - offset))
            history_rows.append(
                {
                    "instrument_id": instrument_id,
                    "trade_date": (trade_day - timedelta(days=offset)).isoformat(),
                    "open": historical_close * 0.99,
                    "high": historical_close * 1.01,
                    "low": historical_close * 0.98,
                    "close": historical_close,
                    "volume": 1_000_000.0,
                }
            )
        close = base * (1 + growth * 25)
        bar = MagicMock()
        bar.open = close * 0.99
        bar.high = close * 1.01
        bar.low = close * 0.98
        bar.close = close
        bar.volume = 1_000_000.0
        bars[InstrumentId(instrument_id)] = bar

    slice_ = MagicMock(spec=Slice)
    slice_.bars = bars
    slice_.benchmark_close = None
    step_context = StepContext(
        time_context=TimeContext(
            decision_time=datetime.combine(
                trade_day,
                datetime.min.time(),
                tzinfo=UTC,
            ),
            knowledge_date=knowledge_date,
            trade_date=trade_date,
        ),
        is_rebalance_day=True,
        bars=bars,
        slice_=slice_,
    )
    data_feed = MagicMock()
    data_feed.get_history.return_value = pl.DataFrame(history_rows)
    data_feed.get_fundamental_snapshot.return_value = pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "volatility_20": [
                0.03 + instrument_id * 0.001 for instrument_id in instrument_ids
            ],
        },
    )
    data_feed.get_classification_snapshot.return_value = pl.DataFrame()
    bridge = FactorBridge()
    bundle = build_factor_bundle(
        ctx=step_context,
        strategy_id=spec.strategy_id,
        run_id=run_id,
        bridge=bridge,
        compiled=compiled,
        data_feed=data_feed,
        lookback_days=25,
    )
    runtime.pipeline.run(StrategyContext(), bundle)
    return runtime, collector.snapshot()


def _drift_one_cost_semantics(
    values: dict[FoldKey, ResearchExecutionSemantics],
) -> dict[FoldKey, ResearchExecutionSemantics]:
    target_key, original = next(
        (key, semantics)
        for key, semantics in values.items()
        if not semantics.is_baseline
    )
    slippage = replace(
        original.policy.slippage,
        basis_points=original.policy.slippage.basis_points + 1,
    )
    policy = replace(original.policy, slippage=slippage)
    backtest = replace(
        original.backtest,
        slippage_basis_points=slippage.basis_points,
        policy_hash=policy.canonical_hash,
    )
    return {
        **values,
        target_key: replace(original, policy=policy, backtest=backtest),
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


def _trace_identity(
    fold: FoldView,
    attempt: AttemptView,
) -> FoldSelectionTraceArtifactIdentity:
    report = _report_identity(fold, attempt)
    return FoldSelectionTraceArtifactIdentity(
        experiment_id=report.experiment_id,
        candidate_id=report.candidate_id,
        fold_id=report.fold_id,
        attempt_id=report.attempt_id,
        attempt_created_at=report.attempt_created_at,
        run_id=report.run_id,
        test_window=report.test_window,
        reproduction_fingerprint=report.reproduction_fingerprint,
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
    for fold in folds:
        if fold.spec.fold_role is not FoldRole.WALK_FORWARD:
            continue
        fingerprint = str(resolver.resolve(fold).reproduction_fingerprint)
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
    lane: golden_support.GoldenLaneSpec,
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
    trace_adapter = IndexedFoldSelectionTraceArtifactAdapter(
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
        attempt_run_id = attempt.projection.backtest_run_id
        assert isinstance(attempt_run_id, BacktestRunId)
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
        semantics = resolver.resolve(fold)
        assert semantics.is_baseline is candidate.is_baseline
        trace_run = (
            _run_stock_golden_selection_trace(
                candidate_parameters=semantics.strategy.candidate_parameters,
                snapshot_identity=ResearchSnapshotIdentity(
                    semantics.snapshot.exact_snapshot.snapshot_id,
                    semantics.snapshot.exact_snapshot.manifest_hash,
                ),
                strategy_version=semantics.strategy.exact_strategy.version,
                trade_date=fold.spec.test_window.start.isoformat(),
                run_id=str(attempt_run_id),
            )
            if (
                lane.asset_lane is golden_support.ResearchAssetLane.STOCK
                and not candidate.is_baseline
                and isinstance(semantics.strategy, StrategyExecutionBinding)
            )
            else (
                _run_etf_golden_selection_trace(
                    candidate_parameters=semantics.strategy.candidate_parameters,
                    snapshot_identity=ResearchSnapshotIdentity(
                        semantics.snapshot.exact_snapshot.snapshot_id,
                        semantics.snapshot.exact_snapshot.manifest_hash,
                    ),
                    strategy_version=semantics.strategy.exact_strategy.version,
                    trade_date=fold.spec.test_window.start.isoformat(),
                    run_id=str(attempt_run_id),
                )
                if (
                    lane.asset_lane is golden_support.ResearchAssetLane.ETF
                    and not candidate.is_baseline
                    and isinstance(semantics.strategy, StrategyExecutionBinding)
                )
                else SelectionEvidenceLog()
            )
        )
        if isinstance(trace_run, tuple):
            runtime, trace = trace_run
            assert runtime.resolved_spec_hash == semantics.strategy.resolved_spec_hash
        else:
            trace = trace_run
        trace_adapter.publish(
            _trace_identity(fold, attempt),
            trace,
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
            fold_selection_trace_reader=trace_adapter,
            semantics_resolver=resolver,
        ),
        service,
    )


def _store(
    tmp_path: Path,
    *,
    lane: golden_support.GoldenLaneSpec,
    semantics_transform: _SemanticsTransform | None = None,
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
        certification_probe=golden_support.PlanningCertificationProbe(lane),
        executor_probe=golden_support.PlanningExecutorProbe(
            lane,
            bind_real_candidate_identity=True,
        ),
        authority_probe=golden_support.PlanningAuthorityProbe(lane),
    )
    request = golden_support.build_planning_request(lane)
    report = process.preflight(request)
    assert report.plan_hash is not None
    assert report.eligible_month_count == 96
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    launch = reader.get_launch_spec(ExperimentId(request.experiment_id))
    assert launch is not None
    semantics = golden_support.build_execution_semantics(
        launch,
        reader.list_folds(launch.experiment_id),
        lane,
    )
    if semantics_transform is not None:
        semantics = semantics_transform(semantics)
    resolver = golden_support.ExecutionSemanticsResolver(semantics)
    lease = _advance_to_candidate_selection(reader, writer, launch, resolver)
    assembler, artifact_service = _publish_walk_forward_reports(
        tmp_path,
        database,
        reader,
        writer,
        launch,
        lease,
        resolver,
        lane,
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
    selection_id: str | None = None,
    candidate_evidence_content_hash: str | None = None,
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
        selection_id=selection_id,
        expected_candidate_evidence_content_hash=candidate_evidence_content_hash,
        idempotency=(
            None
            if selection_id is None
            else build_mutation_idempotency(
                operation_id="design_research_holdout_evaluations",
                resource_id=str(launch.experiment_id),
                raw_key="golden-holdout-key",
                request_payload={
                    "candidate_id": str(selected.candidate_id),
                    "candidate_evidence_content_hash": (
                        candidate_evidence_content_hash
                    ),
                    "expected_revision": expected_revision,
                    "selection_id": selection_id,
                    "selection_evidence_content_hash": str(ledger.content_hash),
                },
            )
        ),
    )


def _coordinator_with_collector(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
    launch: ExperimentLaunchSpec,
    assembler: WalkForwardEvidenceAssembler,
    artifact_service: ResearchArtifactService,
    r2_live_gate_evidence_reader: R2LiveGateEvidenceReader | None = None,
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
    candidate_evidence_reader = CandidateEvidenceReader(
        scheduler_store=store,
        walk_forward_assembler=assembler,
        artifact_service=artifact_service,
    )
    candidate_selection_process = CandidateSelectionProcess(
        store=store,
        candidate_evidence_reader=candidate_evidence_reader,
    )
    collector = ExperimentEvidenceCollector(
        scheduler_store=store,
        reader=reader,
        writer=writer,
        walk_forward_assembler=assembler,
        selection_evidence_reader=selection_service,
        r2_live_gate_evidence_reader=(
            NullR2LiveGateEvidenceReader()
            if r2_live_gate_evidence_reader is None
            else r2_live_gate_evidence_reader
        ),
    )
    coordinator = ExperimentExecutionCoordinator(
        store=store,
        first_attempt_factory=_Factory(),
        selection_evidence_provider=selection_service,
        owner_token="r3-evidence-closure-coordinator",
        lease_duration=timedelta(minutes=5),
        clock=_AdvancingClock(NOW + timedelta(minutes=2)),
        evidence_collector=collector,
        selection_evidence_publisher=selection_service,
        candidate_selection_process=candidate_selection_process,
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


def _assert_cost_collection_replay(
    *,
    lane: golden_support.GoldenLaneSpec,
    cost_drift: bool,
    collected: CollectedWalkForwardEvidence,
    launch: ExperimentLaunchSpec,
    reader: SQLiteExperimentReader,
    store: ExperimentSchedulerStore,
    artifact_service: ResearchArtifactService,
    preflight_detail: Mapping[str, object],
    semantics_transform: _SemanticsTransform | None,
) -> None:
    expected_cost_hash = ContentHash(lane.execution_policy.canonical_hash)
    assert expected_cost_hash != ContentHash("0" * 64)
    if cost_drift:
        assert len(set(collected.fold_cost_config_hashes)) == 2
        assert collected.fold_cost_config_hashes.count(expected_cost_hash) == 3
    else:
        assert collected.fold_cost_config_hashes == (expected_cost_hash,) * 4
    replay_semantics = golden_support.build_execution_semantics(
        launch,
        reader.list_folds(launch.experiment_id),
        lane,
    )
    if semantics_transform is not None:
        replay_semantics = semantics_transform(replay_semantics)
    restarted_assembler = WalkForwardEvidenceAssembler(
        report_reader=IndexedBacktestReportArtifactAdapter(
            artifact_service=artifact_service,
            artifact_index_reader=reader,
        ),
        fold_selection_trace_reader=IndexedFoldSelectionTraceArtifactAdapter(
            artifact_service=artifact_service,
            artifact_index_reader=reader,
        ),
        semantics_resolver=golden_support.ExecutionSemanticsResolver(replay_semantics),
    )
    assert (
        restarted_assembler.assemble(
            store.load_snapshot(launch.experiment_id),
            project_snapshot_manifest(preflight_detail),
        )
        == collected
    )


def _governance_record(
    lane: golden_support.GoldenLaneSpec,
    version: int,
    *,
    parent_version: int | None,
    created_at: str,
) -> StrategySpecRecord:
    seed = SEED_STRATEGY_SPECS[lane.strategy_id]
    base = StrategySpecRecord(
        strategy_id=lane.strategy_id,
        name=seed.name,
        spec_json=asdict(seed),
        version=version,
        parent_version=parent_version,
        created_at=created_at,
        tags=seed.tags,
    )
    return replace(base, spec_hash=canonical_spec_hash_for_record(base))


def _governance_event_snapshot(
    pool: SQLitePool,
    strategy_id: str,
) -> tuple[tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]:
    connection = pool.get_connection()
    decision_rows = connection.execute(
        "SELECT event_id, version, decision, actor, reason, decided_at "
        "FROM strategy_decision_event WHERE strategy_id = ? ORDER BY rowid",
        (strategy_id,),
    ).fetchall()
    activation_rows = connection.execute(
        "SELECT event_id, target_version, activation_kind, actor, reason, "
        "activated_at FROM strategy_activation_event "
        "WHERE strategy_id = ? ORDER BY rowid",
        (strategy_id,),
    ).fetchall()
    return (
        tuple(tuple(row) for row in decision_rows),
        tuple(tuple(row) for row in activation_rows),
    )


def _assert_deterministic_promotion_is_blocked(
    *,
    tmp_path: Path,
    lane: golden_support.GoldenLaneSpec,
    packet: ReviewPacket,
    reader: SQLiteExperimentReader,
) -> None:
    """Prove one real deterministic packet cannot change production state."""
    pool = SQLitePool(str(tmp_path / f"{lane.lane_id}-governance.sqlite"))
    spec_writer = SQLiteStrategySpecWriter(pool)
    spec_writer.init_schema()
    governance_store = SQLiteStrategyGovernanceStore(pool)
    governance_store.init_schema()
    governance = GovernanceService(governance_store)
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=spec_writer,
        active_pointer_reader=governance_store,
    )
    active_record = _governance_record(
        lane,
        1,
        parent_version=None,
        created_at="2026-07-27T00:00:00Z",
    )
    candidate_record = _governance_record(
        lane,
        lane.strategy_version,
        parent_version=1,
        created_at="2026-07-27T00:00:10Z",
    )
    try:
        governance.create_draft(
            strategy_id=lane.strategy_id,
            version=1,
            spec_record=active_record,
            created_at=active_record.created_at,
        )
        governance.publish_and_activate(
            strategy_id=lane.strategy_id,
            version=1,
            actor="golden-bootstrap",
            reason="existing active strategy",
            decided_at="2026-07-27T00:00:01Z",
        )
        governance.create_draft(
            strategy_id=lane.strategy_id,
            version=lane.strategy_version,
            spec_record=candidate_record,
            created_at=candidate_record.created_at,
        )
        governance.submit_review(
            lane.strategy_id,
            lane.strategy_version,
            event_id=f"{lane.lane_id}:candidate:submit",
            actor="golden-reviewer",
            reason="deterministic candidate review",
            decided_at="2026-07-27T00:00:11Z",
        )
        governance.approve(
            lane.strategy_id,
            lane.strategy_version,
            event_id=f"{lane.lane_id}:candidate:approve",
            actor="golden-reviewer",
            reason="ready except live gate",
            decided_at="2026-07-27T00:00:12Z",
        )
        pointer_before = governance_store.get_active_pointer(lane.strategy_id)
        candidate_before = governance_store.get_state(
            lane.strategy_id,
            lane.strategy_version,
        )
        events_before = _governance_event_snapshot(pool, lane.strategy_id)
        active_spec_before = catalog.get_active_published(lane.strategy_id)
        reloaded_before = reader.get_review_packet(str(packet.bundle_hash))
        assert pointer_before is not None
        assert pointer_before.active_version == 1
        assert candidate_before is not None
        assert candidate_before.state.value == "review"
        assert candidate_before.review_outcome.value == "approved"
        assert active_spec_before is not None
        assert active_spec_before.strategy_id == active_record.strategy_id
        assert active_spec_before.version == active_record.version
        assert active_spec_before.spec_hash == active_record.spec_hash
        assert reloaded_before == packet
        launch = reader.get_launch_spec(ExperimentId(packet.lineage.experiment_id))
        assert launch is not None
        assert packet.spec_hash == encode_launch_spec(launch).content_hash
        assert launch.strategy_spec_hash == ContentHash(candidate_record.spec_hash)

        handler = PublishStrategyVersionHandler(
            StrategyPromotionProcess(governance),
            reader,
        )
        with pytest.raises(AppCommandError) as captured:
            handler.handle(
                PublishStrategyVersionCommand(
                    strategy_id=lane.strategy_id,
                    version=lane.strategy_version,
                    bundle_hash=str(packet.bundle_hash),
                    actor="golden-publisher",
                    reason="attempt deterministic promotion",
                )
            )

        assert captured.value.details["reason"] == "hard_gate_blocked"
        with pytest.raises(AppCommandError) as reactivation:
            ReactivateStrategyHandler(governance).handle(
                ReactivateStrategyCommand(
                    strategy_id=lane.strategy_id,
                    version=lane.strategy_version,
                    actor="golden-operator",
                    reason="attempt to bypass the live gate",
                    confirmation=reactivate_confirmation_phrase(
                        lane.strategy_id,
                        lane.strategy_version,
                        pointer_before.pointer_revision,
                    ),
                    impact_summary="replace the active R1 strategy with the candidate",
                    expected_pointer_revision=pointer_before.pointer_revision,
                )
            )
        assert reactivation.value.details["code"] == "STRATEGY_INVALID_TRANSITION"
        assert governance_store.get_active_pointer(lane.strategy_id) == pointer_before
        assert (
            governance_store.get_state(lane.strategy_id, lane.strategy_version)
            == candidate_before
        )
        assert _governance_event_snapshot(pool, lane.strategy_id) == events_before
        assert catalog.get_active_published(lane.strategy_id) == active_spec_before
        assert reader.get_review_packet(str(packet.bundle_hash)) == packet
    finally:
        pool.close_all()


def test_stock_golden_real_runtime_emits_reviewable_selection_trace() -> None:
    """Stock evidence must come from the real scoring path, not a fabricated log."""
    _runtime, log = _run_stock_golden_selection_trace(
        candidate_parameters=(),
        snapshot_identity=ResearchSnapshotIdentity(
            "stock-golden-factor-snapshot",
            "8" * 64,
        ),
        strategy_version=3,
        trade_date="2026-07-22",
        run_id="stock-golden-selection-trace",
    )

    assert log.initial_universe
    assert log.exclusions
    assert log.selections
    assert log.factor_contributions
    assert log.exposure_declarations
    assert log.exposures
    assert len(log.initial_universe) == 21
    assert len(log.selections) == 21
    assert sum(item.selected for item in log.selections) == 20
    assert len(log.exclusions) == 1
    assert len(log.factor_contributions) == 21 * 3
    assert len(log.exposures) == 20
    assert log.exposure_declarations[0].applicability is (
        SelectionExposureApplicability.APPLICABLE
    )
    assert log.exposure_declarations[0].lane is SelectionExposureLane.STOCK_LANE
    industry_weights: dict[int | str, float] = {}
    size_bucket_weights: dict[str, float] = {}
    for item in log.exposures:
        industry_weights[item.industry_id] = (
            industry_weights.get(item.industry_id, 0.0) + item.selected_weight
        )
        size_bucket_weights[item.size_bucket.value] = (
            size_bucket_weights.get(item.size_bucket.value, 0.0) + item.selected_weight
        )
    assert industry_weights
    assert size_bucket_weights
    assert sum(industry_weights.values()) == pytest.approx(1.0)
    assert sum(size_bucket_weights.values()) == pytest.approx(1.0)
    assert tuple(item.factor_name for item in log.factor_contributions) == (
        *("quality_roe" for _ in range(21)),
        *("value_pe" for _ in range(21)),
        *("momentum_1m" for _ in range(21)),
    )
    assert {item.factor_name: item.weight for item in log.factor_contributions} == {
        "quality_roe": 0.4,
        "value_pe": 0.3,
        "momentum_1m": 0.3,
    }
    assert all(
        item.raw_value is not None
        and item.processed_value is not None
        and item.normalized_value is not None
        and item.contribution is not None
        and item.factor_signal_score is not None
        and item.rank is not None
        and item.selected is not None
        for item in log.factor_contributions
    )
    for selection in log.selections:
        assert sum(
            item.contribution or 0.0
            for item in log.factor_contributions
            if item.instrument_id == selection.instrument_id
        ) == pytest.approx(selection.score)
    repeated_runtime, repeated_log = _run_stock_golden_selection_trace(
        candidate_parameters=(),
        snapshot_identity=ResearchSnapshotIdentity(
            "stock-golden-factor-snapshot",
            "8" * 64,
        ),
        strategy_version=3,
        trade_date="2026-07-22",
        run_id="stock-golden-selection-trace",
    )
    assert repeated_runtime.resolved_spec_hash == _runtime.resolved_spec_hash
    assert repeated_log == log


def test_stock_trace_nonempty_candidate_parameter_changes_hash_and_selection() -> None:
    """A typed top-k override must affect both runtime identity and trace output."""
    snapshot = ResearchSnapshotIdentity(
        "stock-golden-factor-snapshot",
        "8" * 64,
    )
    default_runtime, default_log = _run_stock_golden_selection_trace(
        candidate_parameters=(),
        snapshot_identity=snapshot,
        strategy_version=3,
        trade_date="2026-07-22",
        run_id="stock-golden-default-parameter",
    )
    override_runtime, override_log = _run_stock_golden_selection_trace(
        candidate_parameters=(
            CandidateParameter(path=legacy_parameter_path("top_k"), value=2),
        ),
        snapshot_identity=snapshot,
        strategy_version=3,
        trade_date="2026-07-22",
        run_id="stock-golden-overridden-parameter",
    )

    assert default_runtime.legacy_spec.signal_expressions == (
        "quality_roe",
        "value_pe",
        "momentum_1m",
    )
    assert default_runtime.resolved_spec_hash != override_runtime.resolved_spec_hash
    assert {item.path: item.value for item in override_runtime.effective_parameters}[
        legacy_parameter_path("top_k")
    ] == 2
    assert sum(item.selected for item in default_log.selections) == 20
    assert sum(item.selected for item in override_log.selections) == 2
    assert default_log.exclusions
    assert override_log.exclusions


def test_stock_trace_launch_semantics_preserve_nonempty_candidate_parameter(
    tmp_path: Path,
) -> None:
    """Launch lineage must carry one typed override into the exact fold runtime."""
    lane = golden_support.STOCK_GOLDEN_LANE
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    base = golden_support.build_planning_request(lane)
    parameter_path = legacy_parameter_path("top_k")
    matrix = CandidateMatrixSpec(
        baseline=base.matrix_spec.baseline,
        axes=(ParameterAxis(parameter_path, (2,)),),
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
    )
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=golden_support.PlanningCertificationProbe(lane),
        executor_probe=golden_support.PlanningExecutorProbe(
            lane,
            bind_real_candidate_identity=True,
        ),
        authority_probe=golden_support.PlanningAuthorityProbe(lane),
    )

    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    launch = reader.get_launch_spec(ExperimentId(request.experiment_id))
    assert launch is not None
    candidate = next(
        item for item in launch.candidates if item.parameters.get(parameter_path) == 2
    )
    fold = next(
        item
        for item in reader.list_folds(launch.experiment_id)
        if item.spec.fold_role is FoldRole.WALK_FORWARD
        and item.spec.key.candidate_id == candidate.candidate_id
    )
    semantics = golden_support.build_execution_semantics(
        launch,
        reader.list_folds(launch.experiment_id),
        lane,
    )[fold.spec.key]
    assert isinstance(semantics.strategy, StrategyExecutionBinding)
    assert semantics.strategy.candidate_parameters == (
        CandidateParameter(path=parameter_path, value=2),
    )

    runtime, log = _run_stock_golden_selection_trace(
        candidate_parameters=semantics.strategy.candidate_parameters,
        snapshot_identity=ResearchSnapshotIdentity(
            semantics.snapshot.exact_snapshot.snapshot_id,
            semantics.snapshot.exact_snapshot.manifest_hash,
        ),
        strategy_version=semantics.strategy.exact_strategy.version,
        trade_date=fold.spec.test_window.start.isoformat(),
        run_id="stock-golden-nonempty-launch-lineage",
    )
    assert runtime.resolved_spec_hash == semantics.strategy.resolved_spec_hash
    assert sum(item.selected for item in log.selections) == 2


def _assert_persisted_selection_trace_provenance(
    *,
    collected: CollectedWalkForwardEvidence,
    lane: golden_support.GoldenLaneSpec,
    launch: ExperimentLaunchSpec,
    reader: SQLiteExperimentReader,
) -> tuple[SelectionTraceArtifactRef, ...]:
    """Prove each loaded trace is the exact fold-attempt publication."""
    assert len(collected.selection_traces) == 4
    candidates_by_id = {
        candidate.candidate_id: candidate for candidate in launch.candidates
    }
    folds_by_identity = {
        (fold.spec.key.candidate_id, fold.spec.key.fold_id): fold
        for fold in reader.list_folds(launch.experiment_id)
        if fold.spec.fold_role is FoldRole.WALK_FORWARD
    }
    for trace in collected.selection_traces:
        candidate = candidates_by_id[trace.identity.candidate_id]
        fold = folds_by_identity[(trace.identity.candidate_id, trace.identity.fold_id)]
        attempts = reader.list_attempts(fold.spec.key)
        assert len(attempts) == 1
        assert trace.identity == _trace_identity(fold, attempts[0])
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS:
            record = trace.receipt.record(kind)
            assert record == reader.get_artifact(trace.identity.artifact_id(kind))
            assert record.experiment_id == trace.identity.experiment_id
            assert record.candidate_id == trace.identity.candidate_id
            assert record.fold_id == trace.identity.fold_id
            assert record.attempt_id == trace.identity.attempt_id
            assert record.artifact_kind == kind.value
        if candidate.is_baseline:
            assert trace.evidence == SelectionEvidenceLog()
        elif lane.asset_lane is golden_support.ResearchAssetLane.STOCK:
            assert trace.evidence.factor_contributions
            for selection_item in trace.evidence.selections:
                assert sum(
                    item.contribution or 0.0
                    for item in trace.evidence.factor_contributions
                    if item.instrument_id == selection_item.instrument_id
                ) == pytest.approx(selection_item.score)
                assert (
                    fold.spec.test_window.start
                    <= date.fromisoformat(selection_item.trade_date)
                    <= fold.spec.test_window.end
                )
        else:
            assert len(trace.evidence.exposure_declarations) == 1
            declaration = trace.evidence.exposure_declarations[0]
            assert (
                declaration.applicability
                is SelectionExposureApplicability.NOT_APPLICABLE
            )
            assert declaration.lane is SelectionExposureLane.ETF_LANE
            assert trace.evidence.exposures == ()
    return tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind.value,
            artifact_id=trace.receipt.record(kind).artifact_id,
            content_hash=trace.receipt.record(kind).content_hash,
        )
        for trace in collected.selection_traces
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )


@pytest.mark.parametrize(
    "lane",
    golden_support.GOLDEN_LANES,
    ids=lambda lane: lane.lane_id,
)
@pytest.mark.parametrize("cost_drift", [False, True], ids=["cost-match", "cost-drift"])
def test_r3_evidence_closure_drives_review_packet_and_completed_status(  # noqa: PLR0915
    tmp_path: Path,
    lane: golden_support.GoldenLaneSpec,
    cost_drift: bool,
) -> None:
    """Drive one experiment tick from EVIDENCE to a published packet + COMPLETED."""
    semantics_transform = _drift_one_cost_semantics if cost_drift else None
    database, reader, writer, launch, assembler, artifact_service = _store(
        tmp_path,
        lane=lane,
        semantics_transform=semantics_transform,
    )
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
    expected_trace_refs = _assert_persisted_selection_trace_provenance(
        collected=collected,
        lane=lane,
        launch=launch,
        reader=reader,
    )
    _assert_cost_collection_replay(
        lane=lane,
        cost_drift=cost_drift,
        collected=collected,
        launch=launch,
        reader=reader,
        store=store,
        artifact_service=artifact_service,
        preflight_detail=events[0].detail,
        semantics_transform=semantics_transform,
    )
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
    selection_request_payload = {
        "candidate_id": str(selected.candidate_id),
        "comparison_payload_hash": str(collected.comparison.content_hash),
        "expected_revision": selection_projection.revision,
        "rationale": "Candidate won the registered objective review.",
    }
    selection_request = CandidateSelectionRequest(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(selected.candidate_id),
        comparison_payload_hash=str(collected.comparison.content_hash),
        expected_revision=selection_projection.revision,
        rationale="Candidate won the registered objective review.",
        occurred_at=NOW + timedelta(seconds=35),
        idempotency=build_mutation_idempotency(
            operation_id="design_research_candidate_selection",
            resource_id=str(launch.experiment_id),
            raw_key="golden-candidate-selection-key",
            request_payload=selection_request_payload,
        ),
    )
    candidate_selection = coordinator.select_candidate(selection_request)
    assert coordinator.select_candidate(selection_request) == candidate_selection
    assert (
        len(
            tuple(
                event
                for event in reader.list_status_events(launch.experiment_id)
                if event.reason_code == "candidate_preselected"
            )
        )
        == 1
    )
    holdout_request = _application_request(
        launch,
        selection.ledger,
        expected_revision=candidate_selection.experiment_revision,
        occurred_at=NOW + timedelta(seconds=40),
        selection_id=candidate_selection.selection_id,
        candidate_evidence_content_hash=(
            candidate_selection.candidate_evidence_content_hash
        ),
    )
    holdout_claim = coordinator.claim_holdout_candidate(holdout_request)
    assert coordinator.claim_holdout_candidate(holdout_request) == holdout_claim
    assert holdout_claim.selection_id == candidate_selection.selection_id
    with pytest.raises(AppProcessError) as second_claim:
        coordinator.claim_holdout_candidate(
            replace(
                holdout_request,
                idempotency=build_mutation_idempotency(
                    operation_id="design_research_holdout_evaluations",
                    resource_id=str(launch.experiment_id),
                    raw_key="golden-second-holdout-key",
                    request_payload={
                        "candidate_id": str(selected.candidate_id),
                        "candidate_evidence_content_hash": (
                            candidate_selection.candidate_evidence_content_hash
                        ),
                        "expected_revision": candidate_selection.experiment_revision,
                        "selection_id": candidate_selection.selection_id,
                        "selection_evidence_content_hash": str(
                            selection.ledger.content_hash
                        ),
                    },
                ),
            )
        )
    assert second_claim.value.details["code"] == "HOLDOUT_ALREADY_CLAIMED"
    assert (
        len(
            tuple(
                event
                for event in reader.list_status_events(launch.experiment_id)
                if event.reason_code == "holdout_candidate_claimed"
            )
        )
        == 1
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
        expected_cost_hashes=collected.fold_cost_config_hashes,
        expected_cost_outcome=(GateOutcome.FAIL if cost_drift else GateOutcome.PASS),
        expected_trace_refs=expected_trace_refs,
    )
    if not cost_drift:
        _assert_deterministic_promotion_is_blocked(
            tmp_path=tmp_path,
            lane=lane,
            packet=persisted_packet,
            reader=reader,
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
    expected_cost_hashes: tuple[ContentHash, ...],
    expected_cost_outcome: GateOutcome,
    expected_trace_refs: tuple[SelectionTraceArtifactRef, ...],
) -> None:
    """Assert real metric, artifact, and lineage evidence in the frozen packet."""
    gate_by_rule = {entry.rule_id: entry for entry in packet.gate_evaluations}
    hard_rule_ids = tuple(
        entry.rule_id
        for entry in packet.gate_evaluations
        if entry.layer is GateLayer.HARD
    )
    hard_gates = {
        rule_id: gate
        for rule_id, gate in gate_by_rule.items()
        if gate.layer is GateLayer.HARD
    }
    assert hard_rule_ids == HARD_GATE_RULE_IDS
    # Live R2 evidence is intentionally not inferred from this deterministic
    # tmp_path fixture. Cost assumptions are real execution-policy hashes, while
    # G2 promotion readiness remains explicitly NOT_EVALUATED.
    assert hard_gates["r2_live_gate"].outcome is GateOutcome.NOT_EVALUATED
    for rule_id, gate in hard_gates.items():
        if rule_id == "r2_live_gate":
            assert gate.outcome is GateOutcome.NOT_EVALUATED
        elif rule_id == "cost_assumptions":
            assert gate.outcome is expected_cost_outcome
        else:
            assert gate.outcome is GateOutcome.PASS
    assert hard_gates["artifact_completeness"].outcome is GateOutcome.PASS
    assert hard_gates["cost_assumptions"].outcome is expected_cost_outcome
    cost_observed = hard_gates["cost_assumptions"].observed
    assert isinstance(cost_observed, Mapping)
    assert tuple(cost_observed["cost_config_hashes"]) == tuple(
        str(item) for item in expected_cost_hashes
    )
    assert tuple(cost_observed["unique_cost_config_hashes"]) == tuple(
        sorted({str(item) for item in expected_cost_hashes})
    )
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
    assert packet.selection_trace_artifact_refs == expected_trace_refs
    assert packet.candidate_rationale
    assert packet.candidate_rationale == packet.candidate_rationale.strip()
