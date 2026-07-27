"""Reusable real-preflight and baseline-semantics support for the R3 golden."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ditto_analysis.experiments import (
    ExperimentFailurePolicy,
    ExperimentLaunchSpec,
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
from ditto_application.processes.execution.factor_bridge import (
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments.baseline_planning import (
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
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
    default_etf_execution_policy,
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
from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "BaselineSemanticsResolver",
    "PlanningAuthorityProbe",
    "PlanningCertificationProbe",
    "PlanningExecutorProbe",
    "build_baseline_semantics_resolver",
    "build_planning_request",
]

_PLANNING_NOW = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)
_EXPERIMENT_ID = "exp-r3-evidence-closure-golden"
_SNAPSHOT_ID = "certified-snapshot-r3-evidence-golden"
_SNAPSHOT_HASH = "5" * 64
_SOURCE_SNAPSHOT_ID = "provider-snapshot-r3-evidence-golden"
_UNIVERSE_ID = "csi_etf_broad"
_MEMBERSHIP_HASH = "9" * 64


def _next_month(month: CalendarMonth) -> CalendarMonth:
    return month.next()


def _validation_request() -> ValidationProtocolRequest:
    months: list[CalendarMonth] = []
    sessions: list[date] = []
    month_sessions: list[tuple[date, ...]] = []
    month = CalendarMonth(2016, 1)
    for _ in range(97):
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
    instrument_ids = ("ETF-0001",)
    eligible_months = months[1:]
    eligible_from = sessions[21]
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
                dataset_id="etf_daily",
                snapshot_id=_SOURCE_SNAPSHOT_ID,
                manifest_hash=_SNAPSHOT_HASH,
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
                warmup_sessions=21,
                eligible_from=eligible_from,
                membership_intervals=(
                    PitUniverseMembershipInterval(months[0], months[-1]),
                ),
            ),
        ),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            universe_id=_UNIVERSE_ID,
            dataset_id="etf_daily",
            snapshot_id=_SOURCE_SNAPSHOT_ID,
            manifest_hash=_SNAPSHOT_HASH,
        ),
        planning_decision_date=_PLANNING_NOW.date(),
    )


def build_planning_request() -> ExperimentPlanningRequest:
    """Build a real 96-month, two-WF-fold, sealed-holdout planning request."""
    validation_request = _validation_request()
    validation_plan = compile_validation_protocol(validation_request)
    assert validation_plan.reserved_holdout is not None
    holdout_window = validation_plan.reserved_holdout.test_window
    matrix = CandidateMatrixSpec(
        baseline=BaselineDescriptor(
            descriptor_type="etf-current-active",
            payload={
                "strategy_id": "seed_etf_rotation",
                "version": 2,
                "spec_hash": "f" * 64,
            },
        ),
    )
    family = declare_trial_family(
        experiment_id=_EXPERIMENT_ID,
        matrix_spec=matrix,
        family_id="r3-evidence-closure-family",
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
    return ExperimentPlanningRequest(
        experiment_id=_EXPERIMENT_ID,
        research_cycle_id="cycle-r3-evidence-closure-golden",
        research_cycle_hash=str(
            canonical_research_cycle_hash(
                strategy_family_id="seed_etf_rotation",
                certified_data_cutoff=holdout_window.end,
                oos_window=holdout_window,
            )
        ),
        strategy_record=StrategySpecRecord(
            strategy_id="seed_etf_rotation",
            name="ETF rotation",
            spec_json={"strategy_id": "seed_etf_rotation"},
            version=3,
        ),
        snapshot_identity=ExperimentSnapshotIdentity(
            snapshot_id=_SNAPSHOT_ID,
            manifest_hash=_SNAPSHOT_HASH,
        ),
        validation_request=validation_request,
        matrix_spec=matrix,
        promotion_objective=objective,
        dataset_requirements=(
            ResearchDatasetRequirement(
                dataset_id="etf_daily",
                expected_snapshot_ids=(_SOURCE_SNAPSHOT_ID,),
                requires_pit_universe=True,
                certified_from=date(2016, 1, 1),
            ),
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


class PlanningCertificationProbe:
    """Return one exact certification projection for the golden snapshot."""

    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        return ResearchCertificationResult(
            ready=True,
            profile=R3_RESEARCH_CERTIFICATION_PROFILE,
            dataset_ids=tuple(item.dataset_id for item in request.requirements),
            report_ids=("cert-report-r3-evidence-golden",),
            reason_codes=(),
            snapshot_evidence=ResearchSnapshotEvidence(
                snapshot_id=request.snapshot_identity.snapshot_id,
                dataset_id="research-etf-rotation",
                manifest_hash=request.snapshot_identity.manifest_hash,
                source_snapshot_ids=(_SOURCE_SNAPSHOT_ID,),
                snapshot_start=request.required_from,
                snapshot_end=request.required_to,
                known_at_policy="sample_time",
                builder_version="research-builder-v1",
            ),
        )


class PlanningExecutorProbe:
    """Return deterministic runtime and candidate identities for real preflight."""

    def probe(
        self,
        request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        registry = default_baseline_registry()
        baseline = resolve_planning_baseline(request.baseline, registry)
        return ResearchExecutorProbeResult(
            available=True,
            code=None,
            reason=None,
            remediation=None,
            strategy_spec_hash="a" * 64,
            node_registry_manifest_hash="e" * 64,
            required_datasets=("etf_daily",),
            candidates=tuple(
                CandidateExecutorEvidence(
                    candidate_hash=candidate.candidate_hash,
                    resolved_spec_hash=f"{candidate.ordinal:064x}",
                    parameter_hash=f"{candidate.ordinal + 128:064x}",
                    pipeline_execution_hash=f"{candidate.ordinal + 256:064x}",
                    compiled_factor_set_hash=compiled_expressions_execution_hash(None),
                )
                for candidate in request.candidates
            ),
            runtime_validation_evidence=RuntimeValidationEvidence(
                lane="etf_rotation",
                universe_id=_UNIVERSE_ID,
                required_datasets=("etf_daily",),
                max_lookback_sessions=21,
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
            baseline_runtime=BaselineRuntimeExecutorEvidence(
                base_spec_hash="f" * 64,
                resolved_spec_hash="b" * 64,
                parameter_hash="c" * 64,
                pipeline_execution_hash=f"{258:064x}",
                compiled_factor_set_hash=compiled_expressions_execution_hash(None),
                max_lookback_sessions=0,
                node_registry_manifest_hash="e" * 64,
                factor_registry_manifest_hash="d" * 64,
                factor_binding_hashes=(),
            ),
        )


class PlanningAuthorityProbe:
    """Seal the exact protocol/runtime/snapshot authority tuple."""

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
            universe_membership_hash=_MEMBERSHIP_HASH,
            requires_pit_universe=True,
            dataset_bindings=request.declared_requirements,
        )
        return ResearchValidationAuthorityResult(True, None, None, None, evidence)


def _backtest_binding(
    snapshot: ResearchSnapshotBinding,
    fee_schedule: ContentAddressedResearchInput,
    instrument_rules: ContentAddressedResearchInput,
) -> BacktestExecutionConfigBinding:
    policy = default_etf_execution_policy()
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


def _baseline_semantics(
    launch: ExperimentLaunchSpec,
    fold: FoldView,
) -> ResearchExecutionSemantics:
    exact_snapshot = ExactResearchSnapshot(_SNAPSHOT_ID, _SNAPSHOT_HASH)
    registry = default_baseline_registry()
    plan = registry.plan(
        BaselinePlanRequest(
            BaselineRef("etf_current_active", 1),
            exact_snapshot,
            ExactUniverseIdentity(_UNIVERSE_ID, _MEMBERSHIP_HASH),
            ExactStrategyIdentity("seed_etf_rotation", 2, "f" * 64),
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
        dataset_id="research-etf-rotation",
        source_snapshot_ids=(_SOURCE_SNAPSHOT_ID,),
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
                _MEMBERSHIP_HASH,
                "6" * 64,
            ),
            fee_schedule,
            instrument_rules,
        ),
    )
    train = fold.spec.train_window
    return ResearchExecutionSemantics(
        experiment_id=str(launch.experiment_id),
        candidate_id=str(fold.spec.key.candidate_id),
        fold_id=str(fold.spec.key.fold_id),
        fold_role=FoldRole.WALK_FORWARD.value,
        is_baseline=True,
        plan_hash=plan.canonical_hash,
        launch_spec_hash=str(encode_launch_spec(launch).content_hash),
        fold_spec_hash=str(fold.spec.payload_hash),
        strategy=StrategyExecutionBinding(
            exact_strategy=plan.exact_strategy,
            resolved_spec_hash="b" * 64,
            parameter_hash="c" * 64,
            node_registry_manifest_hash="e" * 64,
            pipeline_execution_hash=f"{258:064x}",
            factor_registry_manifest_hash="d" * 64,
            compiled_factor_set_hash=compiled_expressions_execution_hash(None),
            factor_bindings=(),
            candidate_parameters=(),
        ),
        backtest=_backtest_binding(snapshot, fee_schedule, instrument_rules),
        snapshot=snapshot,
        membership_hash=_MEMBERSHIP_HASH,
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
        baseline_plan=plan,
        policy=default_etf_execution_policy(),
        environment=CodeEnvironmentLock(
            "git:r3-evidence-closure-golden",
            str(canonical_payload({"fixture": 1}).content_hash),
        ),
    )


class BaselineSemanticsResolver:
    """Resolve the two exact baseline fold semantics by persisted fold key."""

    def __init__(
        self,
        values: dict[object, ResearchExecutionSemantics],
    ) -> None:
        self._values = values

    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        return self._values[fold.spec.key]


def build_baseline_semantics_resolver(
    launch: ExperimentLaunchSpec,
    folds: tuple[FoldView, ...],
) -> BaselineSemanticsResolver:
    """Build semantics only for the launch's declared baseline WF folds."""
    baseline_id = launch.promotion_objective.baseline_candidate_id
    values = {
        fold.spec.key: _baseline_semantics(launch, fold)
        for fold in folds
        if (
            fold.spec.fold_role is FoldRole.WALK_FORWARD
            and fold.spec.key.candidate_id == baseline_id
        )
    }
    assert len(values) == 2
    return BaselineSemanticsResolver(values)
