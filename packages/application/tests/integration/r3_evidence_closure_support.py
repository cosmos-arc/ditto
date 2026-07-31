"""Reusable real-preflight and execution-semantics support for the R3 golden."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import cast

from ditto_analysis.experiments import (
    ExperimentFailurePolicy,
    ExperimentLaunchSpec,
    FoldKey,
    FoldRole,
    FoldView,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments.preflight_authority import (
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_application.builders._research_execution_bindings import (
    build_synthetic_baseline_binding,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
)
from ditto_application.processes.execution.factor_bridge import (
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments.baseline_planning import (
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
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
    ResearchAssetLane,
    ResearchExecutionPolicy,
    default_etf_execution_policy,
    default_stock_execution_policy,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ResourceCostModel,
)
from ditto_application.processes.experiments.planning_contracts import (
    declare_trial_family,
)
from ditto_application.processes.experiments.planning_probes import (
    BaselineRuntimeExecutorEvidence,
)
from ditto_application.processes.experiments.planning_process import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    CandidateExecutorEvidence,
    ExperimentPlanningRequest,
    ExperimentSnapshotIdentity,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchDatasetRequirement,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityRequest,
    ResearchValidationAuthorityResult,
    RuntimeValidationEvidence,
)
from ditto_application.research_validation_protocol import (
    CalendarMonth,
    CoverageEligibility,
    InstrumentEligibilityEvidence,
    IsolationSemantics,
    MonthCoverageDecision,
    PitUniverseMembershipInterval,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    TradingCalendarSourceIdentity,
    UniverseCoveragePolicy,
    UniverseMembershipSource,
    ValidationProtocolRequest,
    compile_validation_protocol,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "ETF_GOLDEN_LANE",
    "GOLDEN_LANES",
    "STOCK_GOLDEN_LANE",
    "ExecutionSemanticsResolver",
    "GoldenLaneSpec",
    "PlanningAuthorityProbe",
    "PlanningCertificationProbe",
    "PlanningExecutorProbe",
    "build_execution_semantics",
    "build_execution_semantics_resolver",
    "build_planning_request",
]

_PLANNING_NOW = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class GoldenLaneSpec:
    """All deterministic identities that distinguish one R3 golden lane."""

    lane_id: str
    asset_lane: ResearchAssetLane
    runtime_lane: str
    experiment_id: str
    research_cycle_id: str
    family_id: str
    strategy_id: str
    strategy_name: str
    strategy_version: int
    baseline_descriptor_type: str
    baseline_exact_strategy: ExactStrategyIdentity | None
    universe_id: str
    membership_hash: str
    instrument_id: str
    snapshot_id: str
    snapshot_hash: str
    source_snapshot_ids: tuple[str, ...]
    primary_dataset_id: str
    research_dataset_id: str
    required_datasets: tuple[str, ...]
    max_lookback_sessions: int
    execution_policy: ResearchExecutionPolicy

    @property
    def baseline_payload(self) -> dict[str, object]:
        """Project the exact planning payload for this lane's baseline."""
        exact = self.baseline_exact_strategy
        if exact is None:
            return {}
        return {
            "strategy_id": exact.strategy_id,
            "version": exact.version,
            "spec_hash": exact.spec_hash,
        }


ETF_GOLDEN_LANE = GoldenLaneSpec(
    lane_id="etf",
    asset_lane=ResearchAssetLane.ETF,
    runtime_lane="etf_rotation",
    experiment_id="exp-r3-evidence-closure-golden",
    research_cycle_id="cycle-r3-evidence-closure-golden",
    family_id="r3-evidence-closure-family",
    strategy_id="seed_etf_industry_rotation",
    strategy_name="ETF 行业轮动",
    strategy_version=3,
    baseline_descriptor_type="etf-current-active",
    baseline_exact_strategy=ExactStrategyIdentity(
        "seed_etf_rotation",
        2,
        "f" * 64,
    ),
    universe_id="csi_etf_broad",
    membership_hash="9" * 64,
    instrument_id="ETF-0001",
    snapshot_id="certified-snapshot-r3-evidence-golden",
    snapshot_hash="5" * 64,
    source_snapshot_ids=("provider-snapshot-r3-evidence-golden",),
    primary_dataset_id="etf_daily",
    research_dataset_id="research-etf-rotation",
    required_datasets=("etf_daily",),
    max_lookback_sessions=21,
    execution_policy=default_etf_execution_policy(),
)

STOCK_GOLDEN_LANE = GoldenLaneSpec(
    lane_id="stock",
    asset_lane=ResearchAssetLane.STOCK,
    runtime_lane="stock_selection",
    experiment_id="exp-r3-stock-evidence-closure-golden",
    research_cycle_id="cycle-r3-stock-evidence-closure-golden",
    family_id="r3-stock-evidence-closure-family",
    strategy_id="seed_stock_selection_rotation",
    strategy_name="个股选股轮动",
    strategy_version=3,
    baseline_descriptor_type="stock-universe-equal-weight",
    baseline_exact_strategy=None,
    universe_id="csi_a_share",
    membership_hash="a" * 64,
    instrument_id="STOCK-0001",
    snapshot_id="certified-snapshot-r3-stock-evidence-golden",
    snapshot_hash="6" * 64,
    source_snapshot_ids=("provider-snapshot-r3-stock-evidence-golden",),
    primary_dataset_id="stock_daily",
    research_dataset_id="research-stock-selection",
    required_datasets=(
        "adj_factor",
        "balance_sheet",
        "income_statement",
        "stock_daily",
    ),
    max_lookback_sessions=252,
    execution_policy=default_stock_execution_policy(),
)

GOLDEN_LANES = (ETF_GOLDEN_LANE, STOCK_GOLDEN_LANE)


def _planning_seed_payload(strategy_id: str) -> dict[str, object]:
    """Keep the full typed seed while sealing every leaf as native JSON."""

    def native(value: object) -> object:
        if isinstance(value, StrEnum):
            return value.value
        if type(value) is dict:
            mapping = cast("dict[object, object]", value)
            return {str(key): native(item) for key, item in mapping.items()}
        if type(value) is tuple:
            sequence = cast("tuple[object, ...]", value)
            return tuple(native(item) for item in sequence)
        if type(value) is list:
            sequence = cast("list[object]", value)
            return [native(item) for item in sequence]
        return value

    payload = native(asdict(SEED_STRATEGY_SPECS[strategy_id]))
    assert type(payload) is dict
    return cast("dict[str, object]", payload)


def _next_month(month: CalendarMonth) -> CalendarMonth:
    return month.next()


def _validation_request(
    lane: GoldenLaneSpec = ETF_GOLDEN_LANE,
) -> ValidationProtocolRequest:
    months: list[CalendarMonth] = []
    sessions: list[date] = []
    month_sessions: list[tuple[date, ...]] = []
    if lane.asset_lane is ResearchAssetLane.STOCK:
        month = CalendarMonth(2015, 2)
        month_count = 108
    else:
        month = CalendarMonth(2016, 1)
        month_count = 97
    for _ in range(month_count):
        months.append(month)
        current_month_sessions: list[date] = []
        current = date(month.year, month.month, 1)
        following = _next_month(month)
        stop = date(following.year, following.month, 1)
        while current < stop:
            if current.weekday() < 5:
                sessions.append(current)
                current_month_sessions.append(current)
            current += timedelta(days=1)
        month_sessions.append(tuple(current_month_sessions))
        month = following
    instrument_ids = (lane.instrument_id,)
    eligible_months = months[-96:]
    eligible_from = sessions[lane.max_lookback_sessions]
    certified_through = date(month.year, month.month, 1) - timedelta(days=1)
    return ValidationProtocolRequest(
        trading_sessions=tuple(sessions),
        strategy_eligible_start=eligible_from,
        last_complete_month=months[-1],
        coverage_policy=UniverseCoveragePolicy("a-share-core", 1),
        coverage_decisions=tuple(
            MonthCoverageDecision.create(
                month=item,
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=instrument_ids,
                eligible_instrument_ids=instrument_ids,
            )
            for item in eligible_months
        ),
        isolation=IsolationSemantics(2, 5, 1),
        trading_calendar=TradingCalendarEvidence.create(
            calendar_id="sse-szse",
            version=1,
            source=TradingCalendarSourceIdentity(
                dataset_id=lane.primary_dataset_id,
                snapshot_id=lane.source_snapshot_ids[0],
                manifest_hash=lane.snapshot_hash,
                certified_through=certified_through,
                authority_as_of=certified_through,
            ),
            month_closures=tuple(
                TradingCalendarMonthClosure.create(
                    month=item,
                    open_sessions=open_sessions,
                )
                for item, open_sessions in zip(months, month_sessions, strict=True)
            ),
        ),
        instrument_eligibility=(
            InstrumentEligibilityEvidence(
                instrument_id=instrument_ids[0],
                listing_date=sessions[0],
                base_data_eligible_start=sessions[0],
                warmup_sessions=lane.max_lookback_sessions,
                eligible_from=eligible_from,
                membership_intervals=(
                    PitUniverseMembershipInterval(months[0], months[-1]),
                ),
            ),
        ),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            universe_id=lane.universe_id,
            dataset_id=lane.primary_dataset_id,
            snapshot_id=lane.source_snapshot_ids[0],
            manifest_hash=lane.snapshot_hash,
        ),
        planning_decision_date=_PLANNING_NOW.date(),
    )


def _baseline_descriptor(lane: GoldenLaneSpec) -> BaselineDescriptor:
    return BaselineDescriptor(
        descriptor_type=lane.baseline_descriptor_type,
        payload=lane.baseline_payload,
    )


def build_planning_request(
    lane: GoldenLaneSpec = ETF_GOLDEN_LANE,
) -> ExperimentPlanningRequest:
    """Build a real 96-month, two-WF-fold, sealed-holdout planning request."""
    validation_request = _validation_request(lane)
    validation_plan = compile_validation_protocol(validation_request)
    assert validation_plan.reserved_holdout is not None
    holdout_window = validation_plan.reserved_holdout.test_window
    matrix = CandidateMatrixSpec(
        baseline=_baseline_descriptor(lane),
    )
    family = declare_trial_family(
        experiment_id=lane.experiment_id,
        matrix_spec=matrix,
        family_id=lane.family_id,
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
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, -100.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(),
        baseline_candidate_id=family.current_members[0].candidate_id,
        economic_rationale="Compare durable returns after frozen costs.",
        trial_family=family,
    )
    seed = SEED_STRATEGY_SPECS[lane.strategy_id]
    assert seed.name == lane.strategy_name
    return ExperimentPlanningRequest(
        experiment_id=lane.experiment_id,
        research_cycle_id=lane.research_cycle_id,
        research_cycle_hash=str(
            canonical_research_cycle_hash(
                strategy_family_id=lane.strategy_id,
                certified_data_cutoff=holdout_window.end,
                oos_window=holdout_window,
            )
        ),
        strategy_record=StrategySpecRecord(
            strategy_id=lane.strategy_id,
            name=seed.name,
            spec_json=_planning_seed_payload(lane.strategy_id),
            version=lane.strategy_version,
            tags=seed.tags,
        ),
        snapshot_identity=ExperimentSnapshotIdentity(
            snapshot_id=lane.snapshot_id,
            manifest_hash=lane.snapshot_hash,
        ),
        validation_request=validation_request,
        matrix_spec=matrix,
        promotion_objective=objective,
        dataset_requirements=tuple(
            ResearchDatasetRequirement(
                dataset_id=dataset_id,
                expected_snapshot_ids=lane.source_snapshot_ids,
                requires_pit_universe=True,
                certified_from=validation_request.required_input_start,
            )
            for dataset_id in lane.required_datasets
        ),
        cost_model=ResourceCostModel(
            bytes_per_run=100,
            bytes_per_trading_session=2,
        ),
        budget=ExperimentBudgetSpec(
            candidate_limit=128,
            fold_run_limit=1_000,
            trading_session_limit=1_000_000,
            disk_byte_limit=100_000_000,
        ),
        seed=17,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        created_at=_PLANNING_NOW,
    )


@dataclass(frozen=True, slots=True)
class PlanningCertificationProbe:
    """Return one exact certification projection for the golden snapshot."""

    lane: GoldenLaneSpec = ETF_GOLDEN_LANE

    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        return ResearchCertificationResult(
            ready=True,
            profile=R3_RESEARCH_CERTIFICATION_PROFILE,
            dataset_ids=tuple(item.dataset_id for item in request.requirements),
            report_ids=tuple(
                f"cert-report-r3-{self.lane.lane_id}-{item.dataset_id}"
                for item in request.requirements
            ),
            reason_codes=(),
            snapshot_evidence=ResearchSnapshotEvidence(
                snapshot_id=request.snapshot_identity.snapshot_id,
                dataset_id=self.lane.research_dataset_id,
                manifest_hash=request.snapshot_identity.manifest_hash,
                source_snapshot_ids=self.lane.source_snapshot_ids,
                snapshot_start=request.required_from,
                snapshot_end=request.required_to,
                known_at_policy="sample_time",
                builder_version="research-builder-v1",
            ),
        )


@dataclass(frozen=True, slots=True)
class PlanningExecutorProbe:
    """Return deterministic runtime and candidate identities for real preflight."""

    lane: GoldenLaneSpec = ETF_GOLDEN_LANE
    bind_real_candidate_identity: bool = False

    def probe(
        self,
        request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        registry = default_baseline_registry()
        baseline = resolve_planning_baseline(request.baseline, registry)
        candidate_evidence_items: list[CandidateExecutorEvidence] = []
        for candidate in request.candidates:
            if self.bind_real_candidate_identity:
                runtime = ResearchRuntimeBuilder().build(
                    record=request.strategy_record,
                    candidate_parameters=candidate.binder_parameters,
                    snapshot_identity=ResearchSnapshotIdentity(
                        request.snapshot_identity.snapshot_id,
                        request.snapshot_identity.manifest_hash,
                    ),
                    version_status="draft",
                )
                resolved_spec_hash = runtime.resolved_spec_hash
                parameter_hash = runtime.parameter_hash
            else:
                resolved_spec_hash = f"{candidate.ordinal:064x}"
                parameter_hash = f"{candidate.ordinal + 128:064x}"
            candidate_evidence_items.append(
                CandidateExecutorEvidence(
                    candidate_hash=candidate.candidate_hash,
                    resolved_spec_hash=resolved_spec_hash,
                    parameter_hash=parameter_hash,
                    pipeline_execution_hash=f"{candidate.ordinal + 256:064x}",
                    compiled_factor_set_hash=compiled_expressions_execution_hash(None),
                )
            )
        candidate_evidence = tuple(candidate_evidence_items)
        baseline_runtime = (
            None
            if baseline.exact_strategy is None
            else BaselineRuntimeExecutorEvidence(
                base_spec_hash=baseline.exact_strategy.spec_hash,
                resolved_spec_hash="b" * 64,
                parameter_hash="c" * 64,
                pipeline_execution_hash=f"{258:064x}",
                compiled_factor_set_hash=compiled_expressions_execution_hash(None),
                max_lookback_sessions=0,
                node_registry_manifest_hash="e" * 64,
                factor_registry_manifest_hash="d" * 64,
                factor_binding_hashes=(),
            )
        )
        return ResearchExecutorProbeResult(
            available=True,
            code=None,
            reason=None,
            remediation=None,
            strategy_spec_hash=canonical_spec_hash_for_record(request.strategy_record),
            node_registry_manifest_hash="e" * 64,
            required_datasets=self.lane.required_datasets,
            candidates=candidate_evidence,
            runtime_validation_evidence=RuntimeValidationEvidence(
                lane=self.lane.runtime_lane,
                universe_id=self.lane.universe_id,
                required_datasets=self.lane.required_datasets,
                max_lookback_sessions=self.lane.max_lookback_sessions,
                requires_pit_universe=True,
                forward_horizon_sessions=2,
                holding_period_sessions=5,
                execution_lag_sessions=1,
            ),
            baseline_ref=baseline.ref.identity,
            baseline_descriptor_hash=baseline.registration.descriptor.canonical_hash,
            baseline_registry_manifest_hash=baseline.registry_manifest_hash,
            baseline_exact_strategy_hash=(
                None
                if baseline.exact_strategy is None
                else baseline.exact_strategy.canonical_hash
            ),
            factor_registry_manifest_hash="d" * 64,
            factor_binding_hashes=(),
            baseline_runtime=baseline_runtime,
        )


@dataclass(frozen=True, slots=True)
class PlanningAuthorityProbe:
    """Seal the exact protocol/runtime/snapshot authority tuple."""

    lane: GoldenLaneSpec = ETF_GOLDEN_LANE

    def probe(
        self,
        request: ResearchValidationAuthorityRequest,
    ) -> ResearchValidationAuthorityResult:
        runtime = request.runtime_validation
        assert runtime is not None
        evidence = ResearchValidationAuthorityEvidence.create(
            protocol=request.declared_protocol,
            snapshot_identity=request.snapshot_identity,
            runtime_evidence_hash=runtime.payload_hash,
            universe_membership_hash=self.lane.membership_hash,
            requires_pit_universe=True,
            dataset_bindings=request.declared_requirements,
        )
        return ResearchValidationAuthorityResult(True, None, None, None, evidence)


def _backtest_binding(
    snapshot: ResearchSnapshotBinding,
    fee_schedule: ContentAddressedResearchInput,
    instrument_rules: ContentAddressedResearchInput,
    policy: ResearchExecutionPolicy,
    *,
    synthetic_baseline: bool,
) -> BacktestExecutionConfigBinding:
    component = VersionedExecutionComponent
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=100_000_000,
        currency="CNY",
        engine=component("ditto_backtest.engine", 1),
        engine_version="0.1.0",
        rebalance_policy=component(
            (
                "research.baseline.fold_schedule"
                if synthetic_baseline
                else "ditto_strategy.rebalance_schedule"
            ),
            1,
        ),
        rebalance_frequency="fold_schedule" if synthetic_baseline else "daily",
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
    launch: ExperimentLaunchSpec,
    fold: FoldView,
    lane: GoldenLaneSpec = ETF_GOLDEN_LANE,
) -> ResearchExecutionSemantics:
    exact_snapshot = ExactResearchSnapshot(lane.snapshot_id, lane.snapshot_hash)
    registry = default_baseline_registry()
    baseline = resolve_planning_baseline(_baseline_descriptor(lane), registry)
    plan = registry.plan(
        BaselinePlanRequest(
            baseline.ref,
            exact_snapshot,
            ExactUniverseIdentity(lane.universe_id, lane.membership_hash),
            baseline.exact_strategy,
        )
    )
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
        exact_snapshot=exact_snapshot,
        dataset_id=lane.research_dataset_id,
        source_snapshot_ids=lane.source_snapshot_ids,
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
                lane.membership_hash,
                "6" * 64,
            ),
            fee_schedule,
            instrument_rules,
        ),
    )
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
    strategy: StrategyExecutionBinding | BaselineExecutorBinding
    if candidate.is_baseline:
        if plan.exact_strategy is None:
            strategy = build_synthetic_baseline_binding(
                plan,
                registry_manifest_hash=registry.manifest_hash,
            )
        else:
            strategy = StrategyExecutionBinding(
                exact_strategy=plan.exact_strategy,
                resolved_spec_hash="b" * 64,
                parameter_hash="c" * 64,
                node_registry_manifest_hash="e" * 64,
                pipeline_execution_hash=f"{258:064x}",
                factor_registry_manifest_hash="d" * 64,
                compiled_factor_set_hash=compiled_expressions_execution_hash(None),
                factor_bindings=(),
                candidate_parameters=(),
            )
        plan_hash = plan.canonical_hash
        baseline_plan = plan
        policy = plan.execution_policy
    else:
        strategy = StrategyExecutionBinding(
            exact_strategy=ExactStrategyIdentity(
                lane.strategy_id,
                lane.strategy_version,
                str(launch.strategy_spec_hash),
            ),
            resolved_spec_hash=str(execution.resolved_spec_hash),
            parameter_hash=str(execution.parameter_hash),
            node_registry_manifest_hash="e" * 64,
            pipeline_execution_hash=f"{candidate.ordinal + 256:064x}",
            factor_registry_manifest_hash="d" * 64,
            compiled_factor_set_hash=compiled_expressions_execution_hash(None),
            factor_bindings=(),
            candidate_parameters=(),
        )
        plan_hash = str(execution.resolved_spec_hash)
        baseline_plan = None
        policy = lane.execution_policy
    train = fold.spec.train_window
    return ResearchExecutionSemantics(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(fold.spec.key.candidate_id),
        fold_id=str(fold.spec.key.fold_id),
        fold_role=FoldRole.WALK_FORWARD.value,
        is_baseline=candidate.is_baseline,
        plan_hash=plan_hash,
        launch_spec_hash=str(encode_launch_spec(launch).content_hash),
        fold_spec_hash=str(fold.spec.payload_hash),
        strategy=strategy,
        backtest=_backtest_binding(
            snapshot,
            fee_schedule,
            instrument_rules,
            policy,
            synthetic_baseline=type(strategy) is BaselineExecutorBinding,
        ),
        snapshot=snapshot,
        membership_hash=lane.membership_hash,
        membership_projection_hash="8" * 64,
        train_start=None if train is None else train.start,
        train_end=None if train is None else train.end,
        test_start=fold.spec.test_window.start,
        test_end=fold.spec.test_window.end,
        purge_sessions=fold.spec.purge_sessions,
        embargo_sessions=fold.spec.embargo_sessions,
        seed=launch.seed,
        knowledge_lag_days=1,
        execution_delay_sessions=1,
        baseline_registry_manifest_hash=registry.manifest_hash,
        baseline_plan=baseline_plan,
        policy=policy,
        environment=CodeEnvironmentLock(
            "git:r3-evidence-closure-golden",
            str(canonical_payload({"fixture": 1}).content_hash),
        ),
    )


class ExecutionSemanticsResolver:
    """Resolve exact execution semantics for every persisted walk-forward fold."""

    def __init__(
        self,
        values: dict[FoldKey, ResearchExecutionSemantics],
    ) -> None:
        self._values = values

    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        return self._values[fold.spec.key]


def build_execution_semantics(
    launch: ExperimentLaunchSpec,
    folds: tuple[FoldView, ...],
    lane: GoldenLaneSpec = ETF_GOLDEN_LANE,
) -> dict[FoldKey, ResearchExecutionSemantics]:
    """Build exact semantics keyed by every launch-declared walk-forward fold."""
    values = {
        fold.spec.key: _execution_semantics(launch, fold, lane)
        for fold in folds
        if fold.spec.fold_role is FoldRole.WALK_FORWARD
    }
    assert len(values) == 4
    return values


def build_execution_semantics_resolver(
    launch: ExperimentLaunchSpec,
    folds: tuple[FoldView, ...],
    lane: GoldenLaneSpec = ETF_GOLDEN_LANE,
) -> ExecutionSemanticsResolver:
    """Build the exact all-fold resolver used by the R3 golden."""
    return ExecutionSemanticsResolver(build_execution_semantics(launch, folds, lane))
