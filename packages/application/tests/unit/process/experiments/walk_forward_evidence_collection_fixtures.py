"""Typed ``tmp_path`` fixtures for walk-forward evidence collection tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from ditto_analysis.errors import ExperimentConflictError
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
    ConstraintOperator,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
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
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
    StrategyVersion,
    encode_launch_spec,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.builders.research_artifact_loader import (
    IndexedBacktestReportArtifactAdapter,
)
from ditto_application.processes.experiments._evidence_inputs import (
    SnapshotManifestProjection,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    CollectedWalkForwardEvidence,
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchExecutionSemantics,
    ResearchFillMode,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
    VersionedExecutionComponent,
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ExactUniverseIdentity,
    default_stock_execution_policy,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)
from ditto_application.processes.experiments.worker import (
    ResearchExecutionSemanticsResolver,
)
from ditto_backtest.statistics import (
    BacktestReport,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
)

__all__ = [
    "BASELINE_ID",
    "CANDIDATE_ID",
    "EXPERIMENT_ID",
    "NAVS",
    "NOW",
    "NOW_US",
    "REGISTRY_HASH",
    "SNAPSHOT_HASH",
    "EvidenceCase",
    "MemoryArtifactIndex",
    "Resolver",
    "artifact_identity",
    "build_case",
    "scheduler_snapshot",
    "snapshot_manifest",
]

EXPERIMENT_ID = ExperimentId("experiment-r3-evidence")
BASELINE_ID = CandidateId("candidate-baseline")
CANDIDATE_ID = CandidateId("candidate-selected")
SNAPSHOT_ID = SnapshotId("snapshot-r3")
SNAPSHOT_HASH = ContentHash("a" * 64)
REGISTRY_HASH = ContentHash("f" * 64)
NOW = datetime(2026, 7, 27, 9, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)
WINDOWS = {
    2: DateWindow(date(2024, 1, 1), date(2024, 1, 2)),
    3: DateWindow(date(2025, 1, 1), date(2025, 1, 2)),
}
NAVS = {
    (BASELINE_ID, 2): (102.0, 101.0),
    (BASELINE_ID, 3): (101.0, 104.0),
    (CANDIDATE_ID, 2): (110.0, 105.0),
    (CANDIDATE_ID, 3): (106.0, 112.0),
}


class Resolver:
    """Exact in-memory resolver for the two baseline folds."""

    def __init__(self, values: dict[FoldKey, ResearchExecutionSemantics]) -> None:
        self.values = values

    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        return self.values[fold.spec.key]


class MemoryArtifactIndex:
    """Minimal immutable index confined to one test's ``tmp_path``."""

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve()
        self.records: dict[str, ArtifactRecord] = {}

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.relative_path == relative_path
            ),
            None,
        )

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = (lease_fence, now_epoch_us)
        commit_guard()
        matches = tuple(
            item
            for item in self.records.values()
            if item.artifact_id == record.artifact_id
            or item.relative_path == record.relative_path
        )
        if not matches:
            self.records[record.artifact_id] = record
            return
        if replace(matches[0], is_pinned=False, pinned_at=None, revision=0) != record:
            raise ExperimentConflictError(
                "artifact replay drift",
                details={"reason_code": "artifact_replay_drift"},
            )

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        _ = (artifact_id, expected_revision, pinned_at, commit_guard)
        raise AssertionError("pin is outside this evidence-collection boundary")


def _adapter(
    tmp_path: Path,
) -> tuple[IndexedBacktestReportArtifactAdapter, MemoryArtifactIndex]:
    index = MemoryArtifactIndex(tmp_path)
    service = ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )
    return (
        IndexedBacktestReportArtifactAdapter(
            artifact_service=service,
            artifact_index_reader=index,
        ),
        index,
    )


def _launch_spec() -> ExperimentLaunchSpec:
    baseline = CandidateSpec(BASELINE_ID, 1, True, {"lookback": 0})
    selected = CandidateSpec(CANDIDATE_ID, 2, False, {"lookback": 20})
    candidates = (baseline, selected)
    bindings = (
        CandidateExecutionBinding(
            BASELINE_ID,
            1,
            baseline.parameter_hash,
            ContentHash("1" * 64),
        ),
        CandidateExecutionBinding(
            CANDIDATE_ID,
            2,
            selected.parameter_hash,
            ContentHash("2" * 64),
        ),
    )
    trial_family = TrialFamilyDeclaration(
        "walk-forward-evidence-family",
        tuple(
            LogicalTrialIdentity(
                EXPERIMENT_ID,
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                TrialKind.CURRENT,
            )
            for candidate in candidates
        ),
    )
    objective = PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(),
        baseline_candidate_id=BASELINE_ID,
        economic_rationale="Compare frozen walk-forward evidence.",
        trial_family=trial_family,
    )
    return ExperimentLaunchSpec(
        experiment_id=EXPERIMENT_ID,
        strategy_version=StrategyVersion("strategy@1"),
        strategy_spec_hash=ContentHash("3" * 64),
        snapshot_id=SNAPSHOT_ID,
        candidates=candidates,
        execution_bindings=bindings,
        promotion_objective=objective,
        fold_protocol=FoldProtocolSpec(
            "walk-forward-evidence-v1",
            1,
            ContentHash("4" * 64),
        ),
        seed=17,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _fold(candidate_id: CandidateId, ordinal: int) -> FoldView:
    key = FoldKey(EXPERIMENT_ID, candidate_id, FoldId(f"wf-{ordinal}"))
    spec = FoldPersistenceSpec.create(
        key,
        ordinal,
        FoldRole.WALK_FORWARD,
        None,
        WINDOWS[ordinal],
        1,
        1,
    )
    return FoldView(
        spec,
        FoldProjection(
            key,
            ExperimentStatus.COMPLETED,
            None,
            NOW,
            NOW,
            1,
        ),
    )


def _attempt(fold: FoldView, fingerprint: ContentHash) -> AttemptView:
    candidate_id = fold.spec.key.candidate_id
    ordinal = fold.spec.ordinal
    attempt_id = AttemptId(f"attempt:{candidate_id}:wf-{ordinal}")
    return AttemptView(
        AttemptPersistenceSpec(
            attempt_id,
            fold.spec.key,
            1,
            None,
            None,
            fingerprint,
            NOW,
        ),
        AttemptProjection(
            attempt_id,
            ExperimentStatus.COMPLETED,
            BacktestRunId(f"run:{candidate_id}:wf-{ordinal}"),
            None,
            None,
            NOW,
            NOW,
            1,
        ),
    )


def _report(
    attempt: AttemptView,
    window: DateWindow,
    navs: tuple[float, float],
) -> BacktestReport:
    run_id = attempt.projection.backtest_run_id
    assert run_id is not None
    return BacktestReport(
        run_id=str(run_id),
        period=(window.start.isoformat(), window.end.isoformat()),
        initial_cash=100.0,
        final_nav=navs[-1],
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=empty_aggregated_trade_statistics(),
        alpha_stats=empty_alpha_statistics(),
        nav_series=(
            (window.start.isoformat(), navs[0]),
            (window.end.isoformat(), navs[1]),
        ),
        trade_log=(),
        fill_log=(),
    )


def artifact_identity(
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


def scheduler_snapshot(
    folds: tuple[FoldView, ...],
    attempts: tuple[AttemptView, ...],
) -> ExperimentSchedulerSnapshot:
    return ExperimentSchedulerSnapshot(
        projection=ExperimentProjection(
            ExperimentRecord(
                EXPERIMENT_ID,
                ExperimentStatus.RUNNING,
                ExperimentDesiredState.RUN,
                ExperimentStage.EVIDENCE,
                NOW,
            ),
            1,
            1,
            NOW,
        ),
        launch_spec=_launch_spec(),
        folds=folds,
        attempts=attempts,
    )


def snapshot_manifest() -> SnapshotManifestProjection:
    return SnapshotManifestProjection(SNAPSHOT_HASH, REGISTRY_HASH, "sample_time")


def _baseline_plan() -> BaselineExecutionPlan:
    return default_baseline_registry().plan(
        BaselinePlanRequest(
            BaselineRef("stock_universe_equal_weight", 1),
            ExactResearchSnapshot(str(SNAPSHOT_ID), str(SNAPSHOT_HASH)),
            ExactUniverseIdentity("a-share-r3", "b" * 64),
        )
    )


def _backtest_binding(
    snapshot: ResearchSnapshotBinding,
    fee_schedule: ContentAddressedResearchInput,
    instrument_rules: ContentAddressedResearchInput,
) -> BacktestExecutionConfigBinding:
    policy = default_stock_execution_policy()
    component = VersionedExecutionComponent
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=100_000_000,
        currency="CNY",
        engine=component("ditto_backtest.engine", 1),
        engine_version="0.1.0",
        rebalance_policy=component("ditto_strategy.rebalance_schedule", 1),
        rebalance_frequency="daily",
        participation_rate_ppm=50_000,
        fill_mode=ResearchFillMode.PARTIAL,
        fill_model=component("ditto_backtest.a_share_fill", 1),
        brokerage_model=component("ditto_backtest.brokerage", 1),
        execution_planner=component("ditto_execution.simple_planner", 1),
        slippage_basis_points=policy.slippage.basis_points,
        benchmark=None,
        policy_hash=policy.canonical_hash,
        policy_model_evidence=(
            PolicyModelEvidenceBinding(
                "fees",
                component(policy.fees.model_key, policy.fees.model_version),
                ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                (fee_schedule,),
            ),
            PolicyModelEvidenceBinding(
                "rules",
                component(policy.rules.contract_key, policy.rules.contract_version),
                ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                (instrument_rules,),
            ),
            PolicyModelEvidenceBinding(
                "settlement",
                component(
                    policy.settlement.model_key,
                    policy.settlement.model_version,
                ),
                ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT,
                (instrument_rules,),
            ),
            PolicyModelEvidenceBinding(
                "slippage",
                component(
                    policy.slippage.model_key,
                    policy.slippage.model_version,
                ),
                ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY,
                (),
            ),
        ),
        pre_trade_checks=(
            component("ditto_risk.lot_size", 1),
            component("ditto_risk.buying_power", 1),
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=research_data_feed_manifest_hash(snapshot),
    )


def _execution_semantics(
    fold: FoldView,
    plan: BaselineExecutionPlan,
) -> ResearchExecutionSemantics:
    fee_schedule = ContentAddressedResearchInput(
        "fee_schedule",
        "parquet",
        "c" * 64,
        "d" * 64,
    )
    instrument_rules = ContentAddressedResearchInput(
        "instrument_rules",
        "instrument_rules",
        "e" * 64,
        "f" * 64,
    )
    snapshot = ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot(str(SNAPSHOT_ID), str(SNAPSHOT_HASH)),
        dataset_id="research-stock-selection",
        source_snapshot_ids=("provider-snapshot-1",),
        known_at_policy="sample_time",
        builder_version="research-builder-v1",
        inputs=(
            ContentAddressedResearchInput("bars", "bars", "1" * 64, "2" * 64),
            ContentAddressedResearchInput(
                "calendar",
                "calendar",
                "3" * 64,
                "4" * 64,
            ),
            ContentAddressedResearchInput(
                "membership",
                "membership",
                "b" * 64,
                "6" * 64,
            ),
            fee_schedule,
            instrument_rules,
        ),
    )
    registry = default_baseline_registry()
    launch = _launch_spec()
    candidate = next(
        item
        for item in launch.candidates
        if item.candidate_id == fold.spec.key.candidate_id
    )
    execution = next(
        item
        for item in launch.execution_bindings
        if item.candidate_id == fold.spec.key.candidate_id
    )
    if candidate.is_baseline:
        plan_hash = plan.canonical_hash
        strategy: StrategyExecutionBinding | BaselineExecutorBinding = (
            BaselineExecutorBinding(
                baseline_ref=plan.baseline_ref.identity,
                kind=plan.kind,
                descriptor_hash=plan.descriptor_hash,
                implementation_key=plan.implementation_key,
                executor_contract_version=plan.executor_contract_version,
                registry_manifest_hash=registry.manifest_hash,
                factor_versions=(),
            )
        )
        baseline_plan: BaselineExecutionPlan | None = plan
    else:
        plan_hash = str(execution.resolved_spec_hash)
        strategy = StrategyExecutionBinding(
            exact_strategy=ExactStrategyIdentity(
                "strategy",
                1,
                str(launch.strategy_spec_hash),
            ),
            resolved_spec_hash=str(execution.resolved_spec_hash),
            parameter_hash=str(execution.parameter_hash),
            node_registry_manifest_hash=str(REGISTRY_HASH),
            pipeline_execution_hash="6" * 64,
            factor_registry_manifest_hash="5" * 64,
            compiled_factor_set_hash="4" * 64,
            factor_bindings=(),
        )
        baseline_plan = None
    return ResearchExecutionSemantics(
        experiment_id=str(EXPERIMENT_ID),
        candidate_id=str(candidate.candidate_id),
        fold_id=str(fold.spec.key.fold_id),
        fold_role=FoldRole.WALK_FORWARD.value,
        is_baseline=candidate.is_baseline,
        plan_hash=plan_hash,
        launch_spec_hash=str(encode_launch_spec(launch).content_hash),
        fold_spec_hash=str(fold.spec.payload_hash),
        strategy=strategy,
        backtest=_backtest_binding(snapshot, fee_schedule, instrument_rules),
        snapshot=snapshot,
        membership_hash="b" * 64,
        membership_projection_hash="8" * 64,
        train_start=None,
        train_end=None,
        test_start=fold.spec.test_window.start,
        test_end=fold.spec.test_window.end,
        purge_sessions=fold.spec.purge_sessions,
        embargo_sessions=fold.spec.embargo_sessions,
        seed=launch.seed,
        knowledge_lag_days=1,
        execution_delay_sessions=1,
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=baseline_plan,
        policy=default_stock_execution_policy(),
        environment=CodeEnvironmentLock(
            "git:walk-forward-evidence",
            "9" * 64,
        ),
    )


@dataclass(frozen=True, slots=True)
class EvidenceCase:
    """One complete typed test case with a real indexed artifact adapter."""

    folds: tuple[FoldView, ...]
    attempts: tuple[AttemptView, ...]
    semantics: dict[FoldKey, ResearchExecutionSemantics]
    adapter: IndexedBacktestReportArtifactAdapter
    index: MemoryArtifactIndex

    def snapshot(
        self,
        *,
        folds: tuple[FoldView, ...] | None = None,
        attempts: tuple[AttemptView, ...] | None = None,
    ) -> ExperimentSchedulerSnapshot:
        return scheduler_snapshot(
            self.folds if folds is None else folds,
            self.attempts if attempts is None else attempts,
        )

    def publish(self, fold: FoldView, attempt: AttemptView) -> None:
        fence = LeaseFence(EXPERIMENT_ID, "evidence-owner", 1, NOW_US + 1_000_000)
        self.adapter.publish(
            artifact_identity(fold, attempt),
            BacktestReportEvidence.from_report(
                _report(
                    attempt,
                    fold.spec.test_window,
                    NAVS[(fold.spec.key.candidate_id, fold.spec.ordinal)],
                )
            ),
            lease_fence=fence,
            now_epoch_us=NOW_US,
        )

    def assemble(
        self,
        *,
        folds: tuple[FoldView, ...] | None = None,
        attempts: tuple[AttemptView, ...] | None = None,
        semantics: dict[FoldKey, ResearchExecutionSemantics] | None = None,
        resolver: ResearchExecutionSemanticsResolver | None = None,
    ) -> CollectedWalkForwardEvidence:
        selected_semantics = self.semantics if semantics is None else semantics
        return WalkForwardEvidenceAssembler(
            report_reader=self.adapter,
            semantics_resolver=(
                Resolver(selected_semantics) if resolver is None else resolver
            ),
        ).assemble(
            self.snapshot(folds=folds, attempts=attempts),
            snapshot_manifest(),
        )


def build_case(
    tmp_path: Path,
    *,
    publish_indices: tuple[int, ...] = (0, 1, 2, 3),
) -> EvidenceCase:
    folds = tuple(
        _fold(candidate_id, ordinal)
        for candidate_id in (BASELINE_ID, CANDIDATE_ID)
        for ordinal in (2, 3)
    )
    plan = _baseline_plan()
    semantics = {fold.spec.key: _execution_semantics(fold, plan) for fold in folds}
    attempts = tuple(
        _attempt(
            fold,
            semantics[fold.spec.key].reproduction_fingerprint,
        )
        for fold in folds
    )
    adapter, index = _adapter(tmp_path)
    case = EvidenceCase(folds, attempts, semantics, adapter, index)
    for index_value in publish_indices:
        case.publish(folds[index_value], attempts[index_value])
    return case
