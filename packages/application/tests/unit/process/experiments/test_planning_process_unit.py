"""Unit tests for read-only preflight and the recoverable launch saga."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import cast

import orjson
import pytest
from ditto_analysis.errors import ExperimentConflictError, ResearchDatasetError
from ditto_analysis.experiments import (
    ContentHash,
    ExperimentDesiredState,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentStage,
    ExperimentStatus,
    ExperimentWriterProtocol,
    FoldRole,
    FoldView,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    StatusEventRecord,
    StatusSubjectType,
    TrialFamilyDeclaration,
    canonical_payload,
)
from ditto_analysis.experiments.preflight_authority import (
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments.specs import ExperimentFailurePolicy
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    _launch_material as launch_material_module,
)
from ditto_application.processes.experiments import (
    _preflight_codec as preflight_codec_module,
)
from ditto_application.processes.experiments import (
    planning_process as planning_process_module,
)
from ditto_application.processes.experiments._launch_saga import (
    PreparedExperimentLaunch,
    persist_prepared_launch,
)
from ditto_application.processes.experiments._planning_request_identity import (
    planning_request_hash,
)
from ditto_application.processes.experiments.baseline_planning import (
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    default_baseline_registry,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ExperimentPlanningError,
    ExperimentPlanningSpec,
    ExperimentTrack,
    ParameterAxis,
    ResourceCostModel,
    ValidationWorkload,
    plan_experiment_work,
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
    ExperimentPlanningProcess,
    ExperimentPlanningRequest,
    ExperimentPreflightStatus,
    ExperimentSnapshotIdentity,
    ResearchCertificationProbe,
    ResearchCertificationResult,
    ResearchDatasetRequirement,
    ResearchExecutorProbe,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityProbe,
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
    canonical_validation_protocol_hash,
    canonical_validation_protocol_payload,
    compile_validation_protocol,
)
from ditto_strategy.models import StrategySpecRecord

NOW = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)


def _next_month(month: CalendarMonth) -> CalendarMonth:
    if month.month == 12:
        return CalendarMonth(month.year + 1, 1)
    return CalendarMonth(month.year, month.month + 1)


def _validation(
    month_count: int,
    *,
    instrument_count: int = 1,
) -> ValidationProtocolRequest:
    months: list[CalendarMonth] = []
    sessions: list[date] = []
    month_sessions: list[tuple[date, ...]] = []
    month = CalendarMonth(2016, 1)
    for _ in range(month_count + 1):
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
    instrument_ids = tuple(
        f"ETF-{ordinal:04d}" for ordinal in range(1, instrument_count + 1)
    )
    eligible_months = months[1:]
    eligible_from = sessions[21]
    membership = (PitUniverseMembershipInterval(months[0], months[-1]),)
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
                snapshot_id="provider-snapshot-1",
                manifest_hash="d" * 64,
                certified_through=date(month.year, month.month, 1) - timedelta(days=1),
                authority_as_of=date(month.year, month.month, 1) - timedelta(days=1),
            ),
            month_closures=tuple(
                TradingCalendarMonthClosure.create(
                    month=item,
                    open_sessions=open_sessions,
                )
                for item, open_sessions in zip(months, month_sessions, strict=True)
            ),
        ),
        instrument_eligibility=tuple(
            InstrumentEligibilityEvidence(
                instrument_id=instrument_id,
                listing_date=sessions[0],
                base_data_eligible_start=sessions[0],
                warmup_sessions=21,
                eligible_from=eligible_from,
                membership_intervals=membership,
            )
            for instrument_id in instrument_ids
        ),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            universe_id="csi_etf_broad",
            dataset_id="etf_daily",
            snapshot_id="provider-snapshot-1",
            manifest_hash="d" * 64,
        ),
        planning_decision_date=NOW.date(),
    )


def _objective(
    experiment_id: str,
    matrix: CandidateMatrixSpec,
) -> PromotionObjective:
    family = declare_trial_family(
        experiment_id=experiment_id,
        matrix_spec=matrix,
        family_id="stock-selection-r3-v1",
    )
    return PromotionObjective(
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
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=family.current_members[0].candidate_id,
        economic_rationale="Capture durable returns after costs.",
        trial_family=family,
    )


def _request(month_count: int = 96) -> ExperimentPlanningRequest:
    experiment_id = "exp-plan-1"
    validation_request = _validation(month_count)
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
    return ExperimentPlanningRequest(
        experiment_id=experiment_id,
        research_cycle_id="cycle-plan-1",
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
            snapshot_id="certified-snapshot-1",
            manifest_hash="d" * 64,
        ),
        validation_request=validation_request,
        matrix_spec=matrix,
        promotion_objective=_objective(experiment_id, matrix),
        dataset_requirements=(
            ResearchDatasetRequirement(
                dataset_id="etf_daily",
                expected_snapshot_ids=("provider-snapshot-1",),
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
        created_at=NOW,
    )


def test_planning_request_hash_covers_every_promotion_objective_declaration() -> None:
    request = _request()
    objective = request.promotion_objective
    constraint = objective.hard_constraints[0]
    tie_break = objective.tie_break_order[0]
    variants = (
        replace(
            objective,
            primary=ObjectiveMetric(
                ResearchMetricId.RELATIVE_NET_RETURN,
                ResearchMetricDirection.MAXIMIZE,
            ),
        ),
        replace(
            objective,
            hard_constraints=(
                MetricConstraint(
                    ResearchMetricValue(ResearchMetricId.CAPACITY, 1_000_000.0),
                    ConstraintOperator.GREATER_THAN_OR_EQUAL,
                ),
            ),
        ),
        replace(
            objective,
            hard_constraints=(
                replace(
                    constraint,
                    operator=ConstraintOperator.LESS_THAN_OR_EQUAL,
                ),
            ),
        ),
        replace(
            objective,
            hard_constraints=(
                replace(
                    constraint,
                    threshold=ResearchMetricValue(
                        ResearchMetricId.MAX_DRAWDOWN,
                        -25.0,
                    ),
                ),
            ),
        ),
        replace(
            objective,
            tie_break_order=(
                ObjectiveMetric(
                    ResearchMetricId.COST_DRAG,
                    ResearchMetricDirection.MINIMIZE,
                ),
            ),
        ),
        replace(
            objective,
            tie_break_order=(
                ObjectiveMetric(
                    ResearchMetricId.CAPACITY,
                    ResearchMetricDirection.MAXIMIZE,
                ),
                tie_break,
            ),
        ),
        replace(objective, economic_rationale="Prefer robust net capacity."),
        replace(
            objective,
            trial_family=TrialFamilyDeclaration(
                "stock-selection-r3-v2",
                objective.trial_family.members,
            ),
        ),
    )

    hashes = {
        planning_request_hash(request),
        *(
            planning_request_hash(replace(request, promotion_objective=item))
            for item in variants
        ),
    }

    assert len(hashes) == len(variants) + 1


def _objective_with_other_declared_baseline() -> PromotionObjective:
    objective = _request().promotion_objective
    return replace(
        objective,
        baseline_candidate_id=objective.trial_family.current_members[1].candidate_id,
    )


def _objective_with_substituted_current_trial() -> PromotionObjective:
    objective = _request().promotion_objective
    current = objective.trial_family.current_members
    substituted = replace(current[1], parameter_hash=ContentHash("f" * 64))
    return replace(
        objective,
        trial_family=TrialFamilyDeclaration(
            objective.trial_family.family_id,
            (current[0], substituted),
        ),
    )


@pytest.mark.parametrize(
    ("objective", "reason"),
    [
        (
            _objective_with_other_declared_baseline(),
            "promotion_baseline_candidate_mismatch",
        ),
        (
            _objective_with_substituted_current_trial(),
            "promotion_current_trial_family_mismatch",
        ),
    ],
)
def test_promotion_objective_must_name_the_complete_planned_candidate_family(
    objective: PromotionObjective,
    reason: str,
) -> None:
    request = replace(_request(), promotion_objective=objective)
    store = _Store()
    certification = _CertificationProbe()
    executor = _ExecutorProbe()
    authority = _AuthorityProbe()

    report = _process(
        store,
        certification=certification,
        executor=executor,
        authority=authority,
    ).preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.checks[0].reason == reason
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


class _CertificationProbe:
    def __init__(
        self,
        *,
        ready: bool = True,
        dataset_ids: tuple[str, ...] | None = None,
        snapshot_evidence: ResearchSnapshotEvidence | None = None,
    ) -> None:
        self.ready = ready
        self.dataset_ids = dataset_ids
        self.snapshot_evidence = snapshot_evidence
        self.calls: list[tuple[str, date, date]] = []

    def assess(self, request):
        self.calls.append((request.profile, request.required_from, request.required_to))
        return ResearchCertificationResult(
            ready=self.ready,
            profile=request.profile,
            dataset_ids=(
                tuple(item.dataset_id for item in request.requirements)
                if self.dataset_ids is None
                else self.dataset_ids
            ),
            report_ids=(
                tuple(
                    f"cert-report-{index}"
                    for index, _ in enumerate(request.requirements, start=1)
                )
                if self.ready
                else ()
            ),
            reason_codes=() if self.ready else ("CERTIFICATION_MISSING",),
            snapshot_evidence=(
                self.snapshot_evidence
                if self.snapshot_evidence is not None
                else ResearchSnapshotEvidence(
                    snapshot_id=request.snapshot_identity.snapshot_id,
                    dataset_id="research-etf-rotation",
                    manifest_hash=request.snapshot_identity.manifest_hash,
                    source_snapshot_ids=tuple(
                        sorted(
                            {
                                snapshot_id
                                for requirement in request.requirements
                                for snapshot_id in requirement.expected_snapshot_ids
                            }
                        )
                    ),
                    snapshot_start=request.required_from,
                    snapshot_end=request.required_to,
                    known_at_policy="sample_time",
                    builder_version="research-builder-v1",
                )
            ),
        )


class _ExecutorProbe:
    def __init__(
        self,
        *,
        available: bool = True,
        strategy_spec_hash: str = "a" * 64,
        node_registry_manifest_hash: str = "e" * 64,
        required_datasets: tuple[str, ...] = ("etf_daily",),
        isolation: tuple[int, int, int] = (2, 5, 1),
    ) -> None:
        self.available = available
        self.strategy_spec_hash = strategy_spec_hash
        self.node_registry_manifest_hash = node_registry_manifest_hash
        self.required_datasets = required_datasets
        self.isolation = isolation
        self.calls = 0

    def probe(self, request):
        self.calls += 1
        if not self.available:
            return ResearchExecutorProbeResult(
                available=False,
                code="EXECUTOR_UNAVAILABLE",
                reason="native_v2_executor_unavailable",
                remediation="install or implement the native v2 executor",
                strategy_spec_hash=None,
                node_registry_manifest_hash=None,
                required_datasets=(),
                candidates=(),
            )
        registry = default_baseline_registry()
        baseline = resolve_planning_baseline(
            BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={
                    "strategy_id": "seed_etf_rotation",
                    "version": 2,
                    "spec_hash": "f" * 64,
                },
            ),
            registry,
        )
        return ResearchExecutorProbeResult(
            available=True,
            code=None,
            reason=None,
            remediation=None,
            strategy_spec_hash=self.strategy_spec_hash,
            node_registry_manifest_hash=self.node_registry_manifest_hash,
            required_datasets=self.required_datasets,
            candidates=tuple(
                CandidateExecutorEvidence(
                    candidate_hash=candidate.candidate_hash,
                    resolved_spec_hash=(hex(candidate.ordinal)[2:] * 64)[:64],
                    parameter_hash=(hex(candidate.ordinal + 2)[2:] * 64)[:64],
                    pipeline_execution_hash=(hex(candidate.ordinal + 4)[2:] * 64)[:64],
                    compiled_factor_set_hash=(hex(candidate.ordinal + 6)[2:] * 64)[:64],
                )
                for candidate in request.candidates
            ),
            runtime_validation_evidence=RuntimeValidationEvidence(
                lane="etf_rotation",
                universe_id="csi_etf_broad",
                required_datasets=self.required_datasets,
                max_lookback_sessions=21,
                requires_pit_universe=True,
                forward_horizon_sessions=self.isolation[0],
                holding_period_sessions=self.isolation[1],
                execution_lag_sessions=self.isolation[2],
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
            factor_binding_hashes=("c" * 64,),
            baseline_runtime=BaselineRuntimeExecutorEvidence(
                base_spec_hash="f" * 64,
                resolved_spec_hash="b" * 64,
                parameter_hash="c" * 64,
                pipeline_execution_hash="1" * 64,
                compiled_factor_set_hash="2" * 64,
                max_lookback_sessions=21,
                node_registry_manifest_hash=self.node_registry_manifest_hash,
                factor_registry_manifest_hash="d" * 64,
                factor_binding_hashes=("c" * 64,),
            ),
        )


class _AuthorityProbe:
    def __init__(
        self,
        *,
        protocol: ValidationProtocolRequest | None = None,
        membership_hash: str = "9" * 64,
        snapshot_identity: ExperimentSnapshotIdentity | None = None,
        dataset_ids: tuple[str, ...] | None = None,
        snapshot_ids: tuple[str, ...] | None = None,
        requires_pit_universe: bool | None = None,
    ) -> None:
        self.protocol = protocol
        self.membership_hash = membership_hash
        self.snapshot_identity = snapshot_identity
        self.dataset_ids = dataset_ids
        self.snapshot_ids = snapshot_ids
        self.requires_pit_universe = requires_pit_universe
        self.calls = 0

    def probe(self, request):
        self.calls += 1
        runtime = request.runtime_validation
        assert runtime is not None
        dataset_bindings = request.declared_requirements
        if self.dataset_ids is not None:
            declared_by_id = {
                binding.dataset_id: binding for binding in dataset_bindings
            }
            dataset_bindings = tuple(
                declared_by_id.get(
                    dataset_id,
                    ResearchDatasetRequirement(
                        dataset_id,
                        (f"authority-{dataset_id}-snapshot",),
                        certified_from=date(2016, 1, 1),
                    ),
                )
                for dataset_id in self.dataset_ids
            )
        if self.snapshot_ids is not None:
            dataset_bindings = (
                replace(
                    dataset_bindings[0],
                    expected_snapshot_ids=self.snapshot_ids,
                ),
                *dataset_bindings[1:],
            )
        if self.requires_pit_universe is not None:
            dataset_bindings = tuple(
                replace(
                    binding,
                    requires_pit_universe=self.requires_pit_universe,
                )
                for binding in dataset_bindings
            )
        evidence = ResearchValidationAuthorityEvidence.create(
            protocol=self.protocol or request.declared_protocol,
            snapshot_identity=self.snapshot_identity or request.snapshot_identity,
            runtime_evidence_hash=runtime.payload_hash,
            universe_membership_hash=self.membership_hash,
            requires_pit_universe=(
                any(binding.requires_pit_universe for binding in dataset_bindings)
                if self.requires_pit_universe is None
                else self.requires_pit_universe
            ),
            dataset_bindings=dataset_bindings,
        )
        return ResearchValidationAuthorityResult(True, None, None, None, evidence)


class _MalformedAuthorityProbe:
    def probe(self, request):
        return object()


class _RaisingAuthorityProbe:
    def probe(self, request):
        raise ResearchDatasetError(
            "corrupt authority evidence",
            details={"reason_code": "corrupt_authority_evidence"},
        )


class _BombCertificationProbe(_CertificationProbe):
    def assess(self, request):
        self.calls.append((request.profile, request.required_from, request.required_to))
        raise AssertionError("certification probe must not run during durable replay")


class _BombExecutorProbe(_ExecutorProbe):
    def probe(self, request):
        self.calls += 1
        raise AssertionError("executor probe must not run during durable replay")


class _BombAuthorityProbe(_AuthorityProbe):
    def probe(self, request):
        self.calls += 1
        raise AssertionError("authority probe must not run during durable replay")


class _Store:
    """Minimal reader/writer double with exact replay and injectable fold failure."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.cycle = None
        self.spec = None
        self.projection: ExperimentProjection | None = None
        self.creation_event: StatusEventRecord | None = None
        self.gates = {}
        self.folds = {}
        self.events: list[StatusEventRecord] = []
        self.raise_after_enqueue = False
        self.fail_fold_call: int | None = None
        self.fold_call_count = 0
        self.projection_read_hook: Callable[[], None] | None = None
        self.fold_read_hook: Callable[[], None] | None = None
        self.gate_read_hook: Callable[[], None] | None = None

    def get_research_cycle_identity(self, experiment_id):
        return self.cycle

    def get_launch_spec(self, experiment_id):
        return self.spec

    def get_experiment_projection(self, experiment_id):
        projection = self.projection
        hook = self.projection_read_hook
        if hook is not None:
            self.projection_read_hook = None
            hook()
        return projection

    def list_candidates(self, experiment_id):
        return () if self.spec is None else tuple(self.spec.candidates)

    def list_folds(self, experiment_id):
        hook = self.fold_read_hook
        if hook is not None:
            self.fold_read_hook = None
            hook()
        return tuple(
            sorted(
                self.folds.values(),
                key=lambda view: (
                    view.spec.key.candidate_id.value,
                    view.spec.ordinal,
                ),
            )
        )

    def get_gate_evaluation(self, evaluation_id):
        return self.gates.get(evaluation_id)

    def list_gate_evaluations(self, experiment_id):
        hook = self.gate_read_hook
        if hook is not None:
            self.gate_read_hook = None
            hook()
        return tuple(sorted(self.gates.values(), key=lambda gate: gate.evaluation_id))

    def list_status_events(self, experiment_id):
        creation = () if self.creation_event is None else (self.creation_event,)
        return (*creation, *self.events)

    def create_experiment(
        self,
        cycle,
        spec,
        initial_record,
        *,
        creation_detail=None,
    ):
        self.calls.append("create")
        detail = {} if creation_detail is None else dict(creation_detail)
        if self.spec is not None:
            assert self.cycle == cycle
            assert self.spec == spec
            assert self.creation_event is not None
            assert self.creation_event.detail in ({}, detail)
            return
        self.cycle = cycle
        self.spec = spec
        self.projection = ExperimentProjection(
            record=initial_record,
            queue_ordinal=None,
            revision=0,
            updated_at=initial_record.created_at,
        )
        self.creation_event = StatusEventRecord(
            event_id=f"experiment:{spec.experiment_id}:0",
            experiment_id=spec.experiment_id,
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            subject_type=StatusSubjectType.EXPERIMENT,
            subject_revision=0,
            previous_status=None,
            status=ExperimentStatus.DRAFT,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            failure_code=None,
            reason_code="experiment_created",
            detail=detail,
            detail_hash=canonical_payload(detail).content_hash,
            occurred_at=initial_record.created_at,
        )

    def add_gate_evaluation(self, record):
        self.calls.append(f"gate:{record.rule_id}")
        existing = self.gates.get(record.evaluation_id)
        assert existing is None or existing == record
        self.gates[record.evaluation_id] = record

    def add_fold(self, spec, initial):
        self.fold_call_count += 1
        self.calls.append(f"fold:{spec.key.candidate_id}:{spec.ordinal}")
        if self.fail_fold_call == self.fold_call_count:
            raise AppProcessError(
                "injected fold failure",
                details={"code": "ARTIFACT_WRITE_FAILED"},
            )
        existing = self.folds.get(spec.key)
        view = FoldView(spec=spec, projection=initial)
        assert existing is None or existing == view
        self.folds[spec.key] = view

    def enqueue_experiment(
        self,
        experiment_id,
        *,
        expected_revision,
        occurred_at,
        reason_code,
        detail,
        launch_fence,
    ):
        self.calls.append("enqueue")
        assert len(launch_fence.gates) == len(self.gates)
        assert len(launch_fence.folds) == len(self.folds)
        assert self.projection is not None
        assert self.projection.record.status is ExperimentStatus.DRAFT
        record = self.projection.record
        self.projection = ExperimentProjection(
            record=type(record)(
                experiment_id=record.experiment_id,
                status=ExperimentStatus.QUEUED,
                desired_state=record.desired_state,
                stage=record.stage,
                created_at=record.created_at,
            ),
            queue_ordinal=1,
            revision=expected_revision + 1,
            updated_at=occurred_at,
        )
        self.events.append(
            StatusEventRecord(
                event_id=f"experiment:{experiment_id}:1",
                experiment_id=experiment_id,
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                subject_type=StatusSubjectType.EXPERIMENT,
                subject_revision=1,
                previous_status=ExperimentStatus.DRAFT,
                status=ExperimentStatus.QUEUED,
                desired_state=ExperimentDesiredState.RUN,
                stage=ExperimentStage.PREFLIGHT,
                failure_code=None,
                reason_code=reason_code,
                detail=dict(detail),
                detail_hash=canonical_payload(detail).content_hash,
                occurred_at=occurred_at,
            )
        )
        if self.raise_after_enqueue:
            self.raise_after_enqueue = False
            raise ExperimentConflictError(
                "experiment revision is stale",
                details={"reason_code": "stale_projection_revision"},
            )
        return self.projection


def _process(
    store: _Store,
    *,
    certification: _CertificationProbe | None = None,
    executor: _ExecutorProbe | None = None,
    authority: object | None = None,
) -> ExperimentPlanningProcess:
    return ExperimentPlanningProcess(
        reader=cast(ExperimentReaderProtocol, store),
        writer=cast(ExperimentWriterProtocol, store),
        certification_probe=cast(
            ResearchCertificationProbe,
            certification or _CertificationProbe(),
        ),
        executor_probe=cast(
            ResearchExecutorProbe,
            executor or _ExecutorProbe(),
        ),
        authority_probe=cast(
            ResearchValidationAuthorityProbe,
            authority or _AuthorityProbe(),
        ),
    )


def test_preflight_is_pure_read_and_returns_complete_promotion_budget() -> None:
    store = _Store()
    certification = _CertificationProbe()
    process = _process(store, certification=certification)

    report = process.preflight(_request())

    assert report.status is ExperimentPreflightStatus.READY
    assert report.plan_hash is not None
    assert report.candidate_count == 2
    assert report.planned_fold_count == 8
    assert report.budget_run_count == 7
    assert report.eligible_month_count == 96
    assert report.isolation_width_sessions == 5
    assert [check.outcome.value for check in report.checks] == [
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
    ]
    assert certification.calls[0][0] == R3_RESEARCH_CERTIFICATION_PROFILE
    assert store.calls == []


def test_launch_material_seals_one_reserved_holdout_fold_per_candidate() -> None:
    store = _Store()
    process = _process(store)
    request = _request()

    report = process.preflight(request)
    prepared = process._prepare(request).launch

    assert report.validation_plan is not None
    assert report.validation_plan.reserved_holdout is not None
    assert prepared is not None
    assert report.candidate_count == 2
    assert report.planned_fold_count == 8
    assert report.budget_run_count == 7
    assert len(prepared.folds) == 8
    reserved_holdout = report.validation_plan.reserved_holdout
    for candidate in prepared.spec.candidates:
        candidate_folds = tuple(
            fold
            for fold in prepared.folds
            if fold.key.candidate_id == candidate.candidate_id
        )
        assert [(fold.ordinal, fold.fold_role) for fold in candidate_folds] == [
            (1, FoldRole.EXPLORATION),
            (2, FoldRole.WALK_FORWARD),
            (3, FoldRole.WALK_FORWARD),
            (4, FoldRole.HOLDOUT),
        ]
        holdout = candidate_folds[-1]
        assert holdout.train_window == reserved_holdout.train_window
        assert holdout.test_window == reserved_holdout.test_window
        assert holdout.purge_sessions == reserved_holdout.purge_sessions
        assert holdout.embargo_sessions == reserved_holdout.embargo_sessions


@pytest.mark.parametrize(
    ("forged_protocol", "expected_rule", "expected_code"),
    [
        (_validation(96), "authority", "VALIDATION_AUTHORITY_MISMATCH"),
        (
            replace(
                _validation(37),
                strategy_eligible_start=_validation(37).trading_sessions[1],
            ),
            "compile",
            "SPEC_INVALID",
        ),
        (
            replace(
                _validation(37),
                coverage_decisions=(
                    MonthCoverageDecision.create(
                        month=_validation(37).coverage_decisions[0].month,
                        eligibility=CoverageEligibility.INELIGIBLE,
                        universe_instrument_ids=("ETF-0001",),
                        eligible_instrument_ids=(),
                    ),
                    *_validation(37).coverage_decisions[1:],
                ),
            ),
            "compile",
            "SPEC_INVALID",
        ),
        (
            replace(_validation(37), isolation=IsolationSemantics(0, 0, 0)),
            "authority",
            "VALIDATION_AUTHORITY_MISMATCH",
        ),
    ],
    ids=("fake-96-months", "fake-start", "fake-coverage", "fake-zero-isolation"),
)
def test_validation_assertion_forgery_blocks_before_certification_or_writes(
    forged_protocol: ValidationProtocolRequest,
    expected_rule: str,
    expected_code: str,
) -> None:
    store = _Store()
    certification = _CertificationProbe()
    executor = _ExecutorProbe()
    authority = _AuthorityProbe(protocol=_validation(37))
    process = _process(
        store,
        certification=certification,
        executor=executor,
        authority=authority,
    )
    request = replace(_request(37), validation_request=forged_protocol)

    report = process.preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    check = next(item for item in report.checks if item.rule_id == expected_rule)
    assert check.code == expected_code
    expected_probe_calls = 0 if expected_rule == "compile" else 1
    assert executor.calls == expected_probe_calls
    assert authority.calls == expected_probe_calls
    assert certification.calls == []
    with pytest.raises(AppProcessError) as exc_info:
        process.launch(request, confirmed_plan_hash="0" * 64)
    assert exc_info.value.details["code"] == expected_code
    final_probe_calls = 0 if expected_rule == "compile" else 2
    assert executor.calls == final_probe_calls
    assert authority.calls == final_probe_calls
    assert store.calls == []


@pytest.mark.parametrize(
    "authority",
    [_MalformedAuthorityProbe(), _RaisingAuthorityProbe()],
    ids=("malformed", "exception"),
)
def test_invalid_authority_result_fails_closed_without_writes(
    authority: object,
) -> None:
    store = _Store()
    certification = _CertificationProbe()

    report = _process(
        store,
        certification=certification,
        authority=authority,
    ).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    check = next(item for item in report.checks if item.rule_id == "authority")
    assert check.code == "VALIDATION_AUTHORITY_INVALID"
    assert certification.calls == []
    assert store.calls == []


def test_authority_evidence_hash_and_complete_semantics_are_in_plan_identity() -> None:
    original_request = _request()
    original = _process(
        _Store(),
        authority=_AuthorityProbe(membership_hash="9" * 64),
    ).preflight(original_request)
    membership_drift = _process(
        _Store(),
        authority=_AuthorityProbe(membership_hash="8" * 64),
    ).preflight(original_request)
    same_width_semantics = replace(
        _request(),
        validation_request=replace(
            _request().validation_request,
            isolation=IsolationSemantics(4, 5, 1),
        ),
    )
    semantics_drift = _process(
        _Store(), executor=_ExecutorProbe(isolation=(4, 5, 1))
    ).preflight(same_width_semantics)

    assert original.plan_hash is not None
    assert membership_drift.plan_hash is not None
    assert semantics_drift.plan_hash is not None
    assert (
        len(
            {
                original.plan_hash,
                membership_drift.plan_hash,
                semantics_drift.plan_hash,
            }
        )
        == 3
    )


@pytest.mark.parametrize(
    "authority",
    [
        _AuthorityProbe(
            snapshot_identity=ExperimentSnapshotIdentity("other-snapshot", "d" * 64)
        ),
        _AuthorityProbe(
            snapshot_identity=ExperimentSnapshotIdentity(
                "certified-snapshot-1", "f" * 64
            )
        ),
        _AuthorityProbe(dataset_ids=("etf_daily", "trade_cal")),
        _AuthorityProbe(snapshot_ids=("other-provider-snapshot",)),
        _AuthorityProbe(requires_pit_universe=False),
    ],
    ids=(
        "snapshot-id",
        "snapshot-manifest",
        "dataset-extra",
        "source-snapshot",
        "pit-false",
    ),
)
def test_authority_fact_drift_is_a_mismatch_and_zero_write(authority: object) -> None:
    store = _Store()
    certification = _CertificationProbe()

    report = _process(
        store,
        certification=certification,
        authority=authority,
    ).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    check = next(item for item in report.checks if item.rule_id == "authority")
    assert check.code == "VALIDATION_AUTHORITY_MISMATCH"
    assert certification.calls == []
    assert store.calls == []


def test_authority_rejects_runtime_dataset_omission_and_caller_pit_false() -> None:
    requirements = (
        ResearchDatasetRequirement(
            "etf_daily",
            ("provider-snapshot-1",),
            requires_pit_universe=False,
            certified_from=date(2016, 1, 1),
        ),
        ResearchDatasetRequirement(
            "trade_cal",
            ("provider-calendar-1",),
            certified_from=date(2016, 1, 1),
        ),
    )
    request = replace(_request(), dataset_requirements=requirements)
    store = _Store()
    report = _process(
        store,
        executor=_ExecutorProbe(required_datasets=("etf_daily", "trade_cal")),
        authority=_AuthorityProbe(dataset_ids=("etf_daily",)),
    ).preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    check = next(item for item in report.checks if item.rule_id == "authority")
    assert check.code == "VALIDATION_AUTHORITY_MISMATCH"
    assert store.calls == []


def test_requirement_and_source_snapshot_permutations_keep_one_plan_hash() -> None:
    first_requirements = (
        ResearchDatasetRequirement(
            "trade_cal",
            ("provider-calendar-2", "provider-calendar-1"),
            certified_from=date(2016, 1, 1),
        ),
        ResearchDatasetRequirement(
            "etf_daily",
            ("provider-snapshot-2", "provider-snapshot-1"),
            requires_pit_universe=True,
            certified_from=date(2016, 1, 1),
        ),
    )
    second_requirements = tuple(
        reversed(
            tuple(
                replace(
                    requirement,
                    expected_snapshot_ids=tuple(
                        reversed(requirement.expected_snapshot_ids)
                    ),
                )
                for requirement in first_requirements
            )
        )
    )
    executor = _ExecutorProbe(required_datasets=("etf_daily", "trade_cal"))

    first = _process(_Store(), executor=executor).preflight(
        replace(_request(), dataset_requirements=first_requirements)
    )
    second = _process(
        _Store(),
        executor=_ExecutorProbe(required_datasets=("trade_cal", "etf_daily")),
    ).preflight(replace(_request(), dataset_requirements=second_requirements))

    assert first.plan_hash is not None
    assert second.plan_hash == first.plan_hash


def test_research_only_plan_seals_holdout_rows_without_budgeting_holdout_runs() -> None:
    report = _process(_Store()).preflight(_request(37))

    assert report.status is ExperimentPreflightStatus.RESEARCH_ONLY
    assert report.planned_fold_count == 8
    assert report.budget_run_count == 6
    validation = next(check for check in report.checks if check.rule_id == "history")
    assert validation.outcome.value == "warn"
    assert validation.code == "INSUFFICIENT_PROMOTION_HISTORY"


def test_native_executor_unavailable_and_plan_hash_drift_are_zero_write_failures() -> (
    None
):
    for process, request, confirmed_hash, expected_code in (
        (
            _process(_Store(), executor=_ExecutorProbe(available=False)),
            _request(),
            "0" * 64,
            "EXECUTOR_UNAVAILABLE",
        ),
        (
            _process(_Store()),
            _request(),
            "0" * 64,
            "PLAN_HASH_MISMATCH",
        ),
    ):
        with pytest.raises(AppProcessError) as exc_info:
            process.launch(request, confirmed_plan_hash=confirmed_hash)

        assert exc_info.value.details["code"] == expected_code
        assert process._writer.calls == []  # type: ignore[attr-defined]


def test_invalid_identity_blocks_before_probes_or_writes() -> None:
    store = _Store()
    certification = _CertificationProbe()
    executor = _ExecutorProbe()
    process = _process(store, certification=certification, executor=executor)

    report = process.preflight(
        replace(_request(), research_cycle_hash="not-a-canonical-hash")
    )

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    assert report.checks[0].rule_id == "compile"
    assert report.checks[0].code == "SPEC_INVALID"
    assert certification.calls == []
    assert executor.calls == 0
    assert store.calls == []


def test_cycle_hash_must_match_durable_certification_authority() -> None:
    store = _Store()
    report = _process(store).preflight(
        replace(_request(), research_cycle_hash="0" * 64)
    )

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    certification = next(
        check for check in report.checks if check.rule_id == "certification"
    )
    assert certification.code == "INPUT_HASH_MISMATCH"
    assert certification.reason == "research_cycle_hash_authority_mismatch"
    assert store.calls == []


@pytest.mark.parametrize("operation", ["preflight", "launch"])
def test_non_exact_planning_request_blocks_before_probes_or_writes(
    operation: str,
) -> None:
    class _RequestSubclass(ExperimentPlanningRequest):
        __slots__ = ()

    base = _request()
    request = _RequestSubclass(
        experiment_id=base.experiment_id,
        research_cycle_id=base.research_cycle_id,
        research_cycle_hash=base.research_cycle_hash,
        strategy_record=base.strategy_record,
        snapshot_identity=base.snapshot_identity,
        validation_request=base.validation_request,
        matrix_spec=base.matrix_spec,
        promotion_objective=base.promotion_objective,
        dataset_requirements=base.dataset_requirements,
        cost_model=base.cost_model,
        budget=base.budget,
        seed=base.seed,
        worker_count=base.worker_count,
        failure_policy=base.failure_policy,
        created_at=base.created_at,
    )
    store = _Store()
    certification = _CertificationProbe()
    executor = _ExecutorProbe()
    authority = _AuthorityProbe()
    process = _process(
        store,
        certification=certification,
        executor=executor,
        authority=authority,
    )

    if operation == "preflight":
        report = process.preflight(request)
        assert report.status is ExperimentPreflightStatus.BLOCKED
        assert report.checks[0].code == "SPEC_INVALID"
        assert report.checks[0].reason == "invalid_planning_request_type"
    else:
        with pytest.raises(AppProcessError) as exc_info:
            process.launch(request, confirmed_plan_hash="0" * 64)
        assert exc_info.value.details == {
            "code": "SPEC_INVALID",
            "reason": "invalid_planning_request_type",
        }

    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


def _mutate_cost_scalar(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(request.cost_model, "bytes_per_run", True)


def _mutate_budget_node(request: ExperimentPlanningRequest) -> None:
    class _BudgetSubclass(ExperimentBudgetSpec):
        __slots__ = ()

    budget = object.__new__(_BudgetSubclass)
    object.__setattr__(budget, "candidate_limit", request.budget.candidate_limit)
    object.__setattr__(budget, "fold_run_limit", request.budget.fold_run_limit)
    object.__setattr__(
        budget,
        "trading_session_limit",
        request.budget.trading_session_limit,
    )
    object.__setattr__(budget, "disk_byte_limit", request.budget.disk_byte_limit)
    object.__setattr__(request, "budget", budget)


def _mutate_matrix_baseline_identity(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(request.matrix_spec.baseline, "canonical_json", "{}")


def _mutate_promotion_objective_graph(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(
        request.promotion_objective.primary,
        "direction",
        request.promotion_objective.primary.direction.value,
    )


def _mutate_seed_bool(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(request, "seed", True)


def _mutate_seed_negative(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(request, "seed", -1)


def _mutate_worker_count(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(request, "worker_count", 3)


def _mutate_failure_policy_type(request: ExperimentPlanningRequest) -> None:
    class _FailurePolicyValue(str):
        pass

    object.__setattr__(
        request,
        "failure_policy",
        _FailurePolicyValue(request.failure_policy.value),
    )


def _mutate_validation_decision_graph(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(
        request.validation_request.coverage_decisions[0],
        "eligible_instrument_count",
        999,
    )


def _mutate_dataset_requirement(request: ExperimentPlanningRequest) -> None:
    object.__setattr__(
        request.dataset_requirements[0],
        "requires_pit_universe",
        1,
    )


@pytest.mark.parametrize("operation", ["preflight", "launch"])
@pytest.mark.parametrize(
    "mutator",
    [
        _mutate_cost_scalar,
        _mutate_budget_node,
        _mutate_matrix_baseline_identity,
        _mutate_promotion_objective_graph,
        _mutate_seed_bool,
        _mutate_seed_negative,
        _mutate_worker_count,
        _mutate_failure_policy_type,
        _mutate_validation_decision_graph,
        _mutate_dataset_requirement,
    ],
    ids=(
        "cost-scalar",
        "budget-node-subclass",
        "matrix-baseline-identity",
        "promotion-objective-graph",
        "seed-bool",
        "seed-negative",
        "worker-count",
        "failure-policy-type",
        "validation-decision-graph",
        "dataset-requirement",
    ),
)
def test_mutated_planning_graph_blocks_before_probes_or_writes(
    operation: str,
    mutator: Callable[[ExperimentPlanningRequest], None],
) -> None:
    request = _request()
    mutator(request)
    store = _Store()
    certification = _CertificationProbe()
    executor = _ExecutorProbe()
    authority = _AuthorityProbe()
    process = _process(
        store,
        certification=certification,
        executor=executor,
        authority=authority,
    )

    if operation == "preflight":
        report = process.preflight(request)
        assert report.status is ExperimentPreflightStatus.BLOCKED
        assert report.checks[0].code == "SPEC_INVALID"
    else:
        with pytest.raises(AppProcessError) as exc_info:
            process.launch(request, confirmed_plan_hash="0" * 64)
        assert exc_info.value.details["code"] == "SPEC_INVALID"

    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


@pytest.mark.parametrize(
    "requirements",
    [
        (),
        (
            ResearchDatasetRequirement("etf_daily", ("provider-snapshot-1",)),
            ResearchDatasetRequirement("etf_daily", ("provider-snapshot-2",)),
        ),
    ],
    ids=("missing", "duplicate-dataset"),
)
def test_missing_or_duplicate_dataset_requirements_block_before_probes(
    requirements: tuple[ResearchDatasetRequirement, ...],
) -> None:
    store = _Store()
    certification = _CertificationProbe()
    executor = _ExecutorProbe()
    authority = _AuthorityProbe()

    report = _process(
        store,
        certification=certification,
        executor=executor,
        authority=authority,
    ).preflight(replace(_request(), dataset_requirements=requirements))

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.checks[0].code == "SPEC_INVALID"
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


@pytest.mark.parametrize(
    ("certification", "executor", "expected_code"),
    [
        (
            _CertificationProbe(dataset_ids=("unexpected_dataset",)),
            _ExecutorProbe(),
            "SNAPSHOT_NOT_CERTIFIED",
        ),
        (
            _CertificationProbe(),
            _ExecutorProbe(strategy_spec_hash="not-a-canonical-hash"),
            "REPRODUCIBILITY_FAILED",
        ),
    ],
)
def test_probe_identity_drift_blocks_preflight_without_writes(
    certification: _CertificationProbe,
    executor: _ExecutorProbe,
    expected_code: str,
) -> None:
    store = _Store()
    report = _process(
        store,
        certification=certification,
        executor=executor,
    ).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    assert any(check.code == expected_code for check in report.checks)
    assert store.calls == []


class _RaisingCertificationProbe(_CertificationProbe):
    def assess(self, request):
        raise ResearchDatasetError(
            "corrupt research snapshot row",
            details={"reason_code": "corrupt_snapshot_row"},
        )


class _UnexpectedCertificationProbe(_CertificationProbe):
    def assess(self, request):
        raise RuntimeError("unexpected certification adapter failure")


class _RaisingExecutorProbe(_ExecutorProbe):
    def probe(self, request):
        raise ResearchDatasetError(
            "corrupt runtime evidence",
            details={"reason_code": "corrupt_runtime_evidence"},
        )


@pytest.mark.parametrize(
    ("certification", "executor", "expected_code"),
    [
        (_RaisingCertificationProbe(), _ExecutorProbe(), "SNAPSHOT_NOT_CERTIFIED"),
        (_CertificationProbe(), _RaisingExecutorProbe(), "REPRODUCIBILITY_FAILED"),
    ],
)
def test_probe_domain_errors_fail_closed_without_cross_layer_leak_or_writes(
    certification: _CertificationProbe,
    executor: _ExecutorProbe,
    expected_code: str,
) -> None:
    store = _Store()
    process = _process(store, certification=certification, executor=executor)

    report = process.preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    assert any(check.code == expected_code for check in report.checks)
    with pytest.raises(AppProcessError) as exc_info:
        process.launch(_request(), confirmed_plan_hash="0" * 64)
    assert exc_info.value.details["code"] == expected_code
    assert store.calls == []


def test_unexpected_certification_adapter_error_normalizes_without_writes() -> None:
    store = _Store()
    process = _process(store, certification=_UnexpectedCertificationProbe())

    report = process.preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    certification = next(
        check for check in report.checks if check.rule_id == "certification"
    )
    assert certification.code == "SNAPSHOT_NOT_CERTIFIED"
    with pytest.raises(AppProcessError) as exc_info:
        process.launch(_request(), confirmed_plan_hash="0" * 64)
    assert exc_info.value.details["code"] == "SNAPSHOT_NOT_CERTIFIED"
    assert store.calls == []


def test_certification_rejects_snapshot_that_starts_at_fold_after_warmup_input() -> (
    None
):
    protocol = _validation(96)
    validation = compile_validation_protocol(protocol)
    assert validation.reserved_holdout is not None
    late_snapshot = ResearchSnapshotEvidence(
        snapshot_id="certified-snapshot-1",
        dataset_id="research-etf-rotation",
        manifest_hash="d" * 64,
        source_snapshot_ids=("provider-snapshot-1",),
        snapshot_start=validation.folds[0].test_window.start,
        snapshot_end=validation.reserved_holdout.test_window.end,
        known_at_policy="sample_time",
        builder_version="research-builder-v1",
    )
    store = _Store()
    certification = _CertificationProbe(snapshot_evidence=late_snapshot)

    report = _process(store, certification=certification).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    check = next(item for item in report.checks if item.rule_id == "certification")
    assert check.code == "SNAPSHOT_NOT_CERTIFIED"
    assert certification.calls[0][1] == protocol.trading_sessions[0]
    assert store.calls == []


def test_certification_result_subclass_is_rejected_before_property_reads() -> None:
    class _CertificationResultSubclass(ResearchCertificationResult):
        pass

    class _SubclassProbe(_CertificationProbe):
        def assess(self, request):
            result = super().assess(request)
            return _CertificationResultSubclass(
                result.ready,
                result.profile,
                result.dataset_ids,
                result.report_ids,
                result.reason_codes,
                result.snapshot_evidence,
            )

    store = _Store()
    report = _process(store, certification=_SubclassProbe()).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    certification = next(
        check for check in report.checks if check.rule_id == "certification"
    )
    assert certification.code == "SNAPSHOT_NOT_CERTIFIED"
    assert store.calls == []


def test_snapshot_evidence_subclass_and_string_subclass_fail_closed() -> None:
    class _SnapshotSubclass(ResearchSnapshotEvidence):
        pass

    class _PolicyStringSubclass(str):
        pass

    base = (
        _CertificationProbe()
        .assess(
            type(
                "_Request",
                (),
                {
                    "profile": R3_RESEARCH_CERTIFICATION_PROFILE,
                    "requirements": _request().dataset_requirements,
                    "snapshot_identity": _request().snapshot_identity,
                    "required_from": date(2016, 1, 1),
                    "required_to": date(2023, 12, 29),
                },
            )()
        )
        .snapshot_evidence
    )
    assert base is not None
    subclass_snapshot = _SnapshotSubclass(
        base.snapshot_id,
        base.dataset_id,
        base.manifest_hash,
        base.source_snapshot_ids,
        base.snapshot_start,
        base.snapshot_end,
        base.known_at_policy,
        base.builder_version,
    )
    string_subclass_snapshot = ResearchSnapshotEvidence(
        base.snapshot_id,
        base.dataset_id,
        base.manifest_hash,
        base.source_snapshot_ids,
        base.snapshot_start,
        base.snapshot_end,
        _PolicyStringSubclass("sample_time"),
        base.builder_version,
    )

    for snapshot in (subclass_snapshot, string_subclass_snapshot):
        store = _Store()
        report = _process(
            store,
            certification=_CertificationProbe(snapshot_evidence=snapshot),
        ).preflight(_request())

        assert report.status is ExperimentPreflightStatus.BLOCKED
        certification = next(
            check for check in report.checks if check.rule_id == "certification"
        )
        assert certification.code == "SNAPSHOT_NOT_CERTIFIED"
        observed_snapshot = certification.observed["snapshot_evidence"]
        if snapshot is subclass_snapshot:
            assert observed_snapshot is None
        else:
            assert isinstance(observed_snapshot, Mapping)
            assert observed_snapshot["known_at_policy"] is None
        assert store.calls == []


@pytest.mark.parametrize(
    "mutation",
    ["strategy", "snapshot", "baseline", "candidate"],
)
def test_executor_probe_request_mutation_is_isolated_and_fails_closed(
    mutation: str,
) -> None:
    class _MutatingExecutorProbe:
        def __init__(self) -> None:
            self.seen_requests = []

        def probe(self, request):
            self.seen_requests.append(request)
            if mutation == "strategy":
                request.strategy_record.spec_json["mutated"] = True
            elif mutation == "snapshot":
                object.__setattr__(
                    request.snapshot_identity,
                    "snapshot_id",
                    "mutated-snapshot",
                )
            elif mutation == "baseline":
                object.__setattr__(
                    request.baseline,
                    "descriptor_type",
                    "mutated-baseline",
                )
            else:
                object.__setattr__(request.candidates[0], "ordinal", 999)
            return _ExecutorProbe().probe(request)

    class _CountingAuthorityProbe(_AuthorityProbe):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def probe(self, request):
            self.calls += 1
            return super().probe(request)

    store = _Store()
    certification = _CertificationProbe()
    executor = _MutatingExecutorProbe()
    authority = _CountingAuthorityProbe()
    request = _request()
    original_spec = dict(request.strategy_record.spec_json)

    report = _process(
        store,
        certification=certification,
        executor=cast("_ExecutorProbe", executor),
        authority=authority,
    ).preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    executor_check = next(
        check for check in report.checks if check.rule_id == "executor"
    )
    assert executor_check.code == "REPRODUCIBILITY_FAILED"
    assert executor_check.reason == "executor_probe_mutated_request"
    assert executor.seen_requests[0].strategy_record is not request.strategy_record
    assert request.strategy_record.spec_json == original_spec
    assert authority.calls == 0
    assert certification.calls == []
    assert store.calls == []


def test_executor_available_result_with_remediation_fails_closed() -> None:
    class _PassWithRemediation(_ExecutorProbe):
        def probe(self, request):
            return replace(
                super().probe(request),
                remediation="this must not survive a PASS result",
            )

    store = _Store()
    report = _process(store, executor=_PassWithRemediation()).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    executor_check = next(
        check for check in report.checks if check.rule_id == "executor"
    )
    assert executor_check.code == "REPRODUCIBILITY_FAILED"
    assert executor_check.remediation is not None
    assert store.calls == []


@pytest.mark.parametrize(
    "snapshot_evidence",
    [
        ResearchSnapshotEvidence(
            snapshot_id="certified-snapshot-1",
            dataset_id="research-etf-rotation",
            manifest_hash="f" * 64,
            source_snapshot_ids=("provider-snapshot-1",),
            snapshot_start=date(2022, 1, 1),
            snapshot_end=date(2025, 12, 31),
            known_at_policy="sample_time",
            builder_version="research-builder-v1",
        ),
        ResearchSnapshotEvidence(
            snapshot_id="certified-snapshot-1",
            dataset_id="research-etf-rotation",
            manifest_hash="d" * 64,
            source_snapshot_ids=("other-provider-snapshot",),
            snapshot_start=date(2016, 1, 1),
            snapshot_end=date(2025, 12, 31),
            known_at_policy="sample_time",
            builder_version="research-builder-v1",
        ),
        ResearchSnapshotEvidence(
            snapshot_id="certified-snapshot-1",
            dataset_id="research-etf-rotation",
            manifest_hash="d" * 64,
            source_snapshot_ids=("provider-snapshot-1",),
            snapshot_start=date(2016, 1, 1),
            snapshot_end=date(2025, 12, 31),
            known_at_policy="unverified",
            builder_version="research-builder-v1",
        ),
    ],
)
def test_authoritative_snapshot_drift_blocks_preflight(
    snapshot_evidence: ResearchSnapshotEvidence,
) -> None:
    report = _process(
        _Store(),
        certification=_CertificationProbe(snapshot_evidence=snapshot_evidence),
    ).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    certification = next(
        check for check in report.checks if check.rule_id == "certification"
    )
    assert certification.code == "SNAPSHOT_NOT_CERTIFIED"


def test_malformed_probe_scalar_types_fail_closed() -> None:
    class _MalformedCertification(_CertificationProbe):
        def assess(self, request):
            result = super().assess(request)
            return replace(result, ready=cast("bool", 1), report_ids=("",))

    report = _process(_Store(), certification=_MalformedCertification()).preflight(
        _request()
    )

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None


def test_malformed_snapshot_evidence_type_fails_closed() -> None:
    class _MalformedCertification(_CertificationProbe):
        def assess(self, request):
            result = super().assess(request)
            return replace(
                result,
                snapshot_evidence=cast("ResearchSnapshotEvidence", object()),
            )

    report = _process(_Store(), certification=_MalformedCertification()).preflight(
        _request()
    )

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    certification = next(
        check for check in report.checks if check.rule_id == "certification"
    )
    assert certification.observed["snapshot_evidence"] is None


def test_datetime_snapshot_bounds_fail_closed_without_type_error() -> None:
    evidence = ResearchSnapshotEvidence(
        snapshot_id="certified-snapshot-1",
        dataset_id="research-etf-rotation",
        manifest_hash="d" * 64,
        source_snapshot_ids=("provider-snapshot-1",),
        snapshot_start=cast("date", datetime(2016, 1, 1, tzinfo=UTC)),
        snapshot_end=cast("date", datetime(2025, 12, 31, tzinfo=UTC)),
        known_at_policy="sample_time",
        builder_version="research-builder-v1",
    )

    report = _process(
        _Store(), certification=_CertificationProbe(snapshot_evidence=evidence)
    ).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None


def test_research_cycle_id_is_part_of_confirmed_plan_hash() -> None:
    process = _process(_Store())

    original = process.preflight(_request())
    changed = process.preflight(
        replace(_request(), research_cycle_id="cycle-plan-other")
    )

    assert original.plan_hash is not None
    assert changed.plan_hash is not None
    assert changed.plan_hash != original.plan_hash


def test_preflight_policy_version_is_part_of_confirmed_plan_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _process(_Store())
    original = process.preflight(_request())

    monkeypatch.setattr(
        planning_process_module,
        "_PREFLIGHT_POLICY_VERSION",
        "r3-experiment-preflight-v2",
    )
    changed = process.preflight(_request())

    assert original.plan_hash is not None
    assert changed.plan_hash is not None
    assert changed.plan_hash != original.plan_hash


def test_preflight_check_explanation_is_part_of_confirmed_plan_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _process(_Store())
    original = process.preflight(_request())
    original_check = ExperimentPlanningProcess._certification_check

    def _changed_check(result, request):
        return replace(
            original_check(result, request),
            remediation="use the replacement certification workflow",
        )

    monkeypatch.setattr(
        ExperimentPlanningProcess,
        "_certification_check",
        staticmethod(_changed_check),
    )
    changed = process.preflight(_request())

    assert original.plan_hash is not None
    assert changed.plan_hash is not None
    assert changed.plan_hash != original.plan_hash


def test_registry_manifest_and_exact_fold_rows_are_part_of_confirmed_plan_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _process(_Store())
    original = process.preflight(_request())
    changed_registry = _process(
        _Store(), executor=_ExecutorProbe(node_registry_manifest_hash="f" * 64)
    ).preflight(_request())

    monkeypatch.setattr(planning_process_module, "_FOLD_ID_PREFIX", "drift-fold")
    changed_folds = process.preflight(_request())

    assert original.plan_hash is not None
    assert changed_registry.plan_hash is not None
    assert changed_folds.plan_hash is not None
    assert (
        len({original.plan_hash, changed_registry.plan_hash, changed_folds.plan_hash})
        == 3
    )


def test_invalid_registry_manifest_blocks_preflight() -> None:
    report = _process(
        _Store(), executor=_ExecutorProbe(node_registry_manifest_hash="invalid")
    ).preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    executor = next(check for check in report.checks if check.rule_id == "executor")
    assert executor.code == "REPRODUCIBILITY_FAILED"


def test_budget_failure_preserves_estimates_and_explicit_remediation() -> None:
    request = replace(
        _request(),
        budget=ExperimentBudgetSpec(
            candidate_limit=128,
            fold_run_limit=6,
            trading_session_limit=1,
            disk_byte_limit=1,
        ),
    )

    report = _process(_Store()).preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.candidate_count == 2
    assert report.planned_fold_count == 8
    assert report.budget_run_count == 7
    assert report.estimated_trading_sessions > 0
    assert report.estimated_disk_bytes > 0
    budget = next(check for check in report.checks if check.rule_id == "budget")
    assert budget.code == "BUDGET_EXCEEDED"
    assert budget.reason == "resource_estimate_exceeds_registered_budget"
    assert budget.remediation is not None


def test_matrix_limit_failure_preserves_validated_candidate_count() -> None:
    request = _request()
    request = replace(
        request,
        matrix_spec=CandidateMatrixSpec(
            baseline=request.matrix_spec.baseline,
            axes=(ParameterAxis(name="node.rank", values=tuple(range(128))),),
        ),
    )

    report = _process(_Store()).preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.candidate_count == 129
    assert report.checks[0].code == "MATRIX_TOO_LARGE"
    assert report.checks[0].observed["candidate_count"] == 129


def test_matrix_limit_ignores_forged_error_detail_and_uses_canonical_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    request = replace(
        request,
        matrix_spec=CandidateMatrixSpec(
            baseline=request.matrix_spec.baseline,
            axes=(ParameterAxis(name="node.rank", values=tuple(range(128))),),
        ),
    )

    def _forged_matrix_error(_spec):
        raise ExperimentPlanningError(
            "forged matrix count",
            details={
                "code": "MATRIX_TOO_LARGE",
                "candidate_count": 999,
                "candidate_limit": 128,
            },
        )

    monkeypatch.setattr(
        planning_process_module,
        "expand_candidate_matrix",
        _forged_matrix_error,
    )

    report = _process(_Store()).preflight(request)

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.candidate_count == 129
    assert report.checks[0].code == "SPEC_INVALID"
    assert report.checks[0].reason == "matrix_size_error_detail_mismatch"
    assert report.checks[0].observed["candidate_count"] == 129


def test_launch_writes_draft_gates_all_folds_then_enqueues_without_attempts() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None

    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert receipt.status == "queued"
    assert receipt.queue_ordinal == 1
    assert receipt.fold_count == 8
    assert store.calls[0] == "create"
    assert all(call.startswith("gate:") for call in store.calls[1:7])
    assert all(call.startswith("fold:") for call in store.calls[7:15])
    assert store.calls[15] == "enqueue"
    assert len(store.gates) == 6
    assert {gate.layer for gate in store.gates.values()} == {"hard"}
    authority = next(
        gate for gate in store.gates.values() if gate.rule_id == "authority"
    )
    assert len(authority.observed["authority_payload_hash"]) == 64
    assert authority.observed["summaries"]["semantics"] == {
        "execution_lag_sessions": 1,
        "forward_horizon_sessions": 2,
        "holding_period_sessions": 5,
    }
    assert len(store.folds) == 8
    assert not any("attempt" in call for call in store.calls)
    assert store.spec.budget.fold_run_limit == request.budget.fold_run_limit


def test_enqueue_event_durably_reconstructs_confirmed_preflight() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    assert report.validation_plan is not None
    assert report.work_plan is not None

    process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert store.spec is not None
    event = store.events[-1]
    preflight = cast("Mapping[str, object]", event.detail["preflight"])
    assert event.detail["plan_hash"] == report.plan_hash
    assert (
        event.detail["preflight_hash"]
        == canonical_payload(preflight).content_hash.value
    )
    assert event.detail_hash == canonical_payload(event.detail).content_hash
    assert set(preflight) >= {
        "checks",
        "counts",
        "validation",
        "work",
        "executor",
        "authority",
    }


def test_full_500_instrument_96_month_event_fits_one_mib_without_protocol_copy() -> (
    None
):
    request = replace(
        _request(),
        validation_request=_validation(96, instrument_count=500),
    )

    prepared = _process(_Store())._prepare(request).launch

    assert prepared is not None
    assert (
        len(prepared.enqueue_detail_json)
        <= launch_material_module._MAX_ENQUEUE_DETAIL_BYTES
    )
    detail = cast("dict[str, object]", orjson.loads(prepared.enqueue_detail_json))
    preflight = cast("dict[str, object]", detail["preflight"])
    validation = cast("dict[str, object]", preflight["validation"])
    protocol = cast("dict[str, object]", validation["protocol"])
    authority = cast("dict[str, object]", preflight["authority"])
    assert len(cast("list[object]", protocol["instrument_eligibility"])) == 500
    assert authority["protocol_hash"] == canonical_validation_protocol_hash(
        request.validation_request
    )
    assert "protocol" not in authority
    assert prepared.enqueue_detail_json.count(b'"trading_calendar"') == 1


def test_persisted_preflight_roundtrip_reconstructs_the_full_report() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None

    process.launch(request, confirmed_plan_hash=report.plan_hash)

    reconstructed = planning_process_module.reconstruct_preflight_report(
        store.events[-1].detail
    )
    assert reconstructed == report
    preflight = cast("Mapping[str, object]", store.events[-1].detail["preflight"])
    validation = cast("Mapping[str, object]", preflight["validation"])
    protocol = cast("Mapping[str, object]", validation["protocol"])
    work = cast("Mapping[str, object]", preflight["work"])
    executor = cast("Mapping[str, object]", preflight["executor"])
    authority = cast("Mapping[str, object]", preflight["authority"])
    assert len(cast("list[object]", protocol["trading_sessions"])) > 1_000
    assert cast("Mapping[str, object]", validation["plan"])["folds"]
    assert cast("Mapping[str, object]", work["candidate_matrix"])["candidates"]
    assert cast("list[object]", executor["candidates"])[0]
    assert authority["protocol_hash"] == canonical_validation_protocol_hash(
        _validation(96)
    )
    assert "protocol" not in authority


def test_persisted_preflight_tamper_cannot_detach_from_confirmed_plan_hash() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    detail = cast(
        "dict[str, object]",
        orjson.loads(canonical_payload(store.events[-1].detail).json_bytes),
    )
    preflight = cast("dict[str, object]", detail["preflight"])
    identities = cast("dict[str, object]", preflight["identities"])
    identities["strategy_id"] = "tampered_strategy"
    detail["preflight_hash"] = canonical_payload(preflight).content_hash.value

    with pytest.raises(AppProcessError) as exc_info:
        planning_process_module.reconstruct_preflight_report(detail)

    assert exc_info.value.details["code"] == "PREFLIGHT_DETAIL_INVALID"


def test_launch_material_deep_freezes_gate_and_event_json_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mutable_observed = {"nested": {"values": [1, 2]}}
    mutable_policy = {"allowed": ["a", "b"]}
    original_check = ExperimentPlanningProcess._certification_check

    def _aliased_check(result, request):
        return replace(
            original_check(result, request),
            observed=mutable_observed,
            policy=mutable_policy,
        )

    monkeypatch.setattr(
        ExperimentPlanningProcess,
        "_certification_check",
        staticmethod(_aliased_check),
    )
    process = _process(_Store())
    prepared = process._prepare(_request()).launch
    assert prepared is not None
    certification = next(
        gate for gate in prepared.gates if gate.rule_id == "certification"
    )
    original_gate_hash = certification.payload_hash
    original_detail_hash = prepared.enqueue_detail_hash

    mutable_observed["nested"]["values"].append(3)
    mutable_policy["allowed"].append("c")

    assert certification.payload_hash == original_gate_hash
    assert prepared.enqueue_detail_hash == original_detail_hash
    assert (
        cast("Mapping[str, object]", certification.observed)["nested"]
        != (mutable_observed["nested"])
    )
    with pytest.raises(TypeError):
        cast("dict[str, object]", certification.observed)["drift"] = True
    with pytest.raises(TypeError):
        cast("dict[str, object]", prepared.enqueue_detail)["drift"] = True


def test_prepared_launch_identity_drift_blocks_before_first_write() -> None:
    store = _Store()
    prepared = _process(store)._prepare(_request()).launch
    assert prepared is not None
    tampered = replace(prepared, plan_hash="f" * 64)

    with pytest.raises(AppProcessError) as exc_info:
        persist_prepared_launch(
            reader=cast(ExperimentReaderProtocol, store),
            writer=cast(ExperimentWriterProtocol, store),
            prepared=tampered,
        )

    assert exc_info.value.details["reason"] == "prepared_launch_identity_mismatch"
    assert store.calls == []


def test_rehashed_illegal_preflight_check_blocks_before_first_write() -> None:
    store = _Store()
    prepared = _process(store)._prepare(_request()).launch
    assert prepared is not None
    detail = cast(
        "dict[str, object]",
        orjson.loads(prepared.enqueue_detail_json),
    )
    preflight = cast("dict[str, object]", detail["preflight"])
    checks = cast("list[dict[str, object]]", preflight["checks"])
    checks[0]["outcome"] = "fail"
    checks[0]["code"] = "FORGED"
    checks[0]["reason"] = "self_consistent_rehash"
    checks[0]["remediation"] = "none"
    preflight_payload = canonical_payload(preflight)
    plan_preimage = cast("dict[str, object]", detail["plan_preimage"])
    plan_preimage["preflight_hash"] = str(preflight_payload.content_hash)
    plan_preimage_payload = canonical_payload(plan_preimage)
    detail["preflight_hash"] = str(preflight_payload.content_hash)
    detail["plan_hash"] = str(plan_preimage_payload.content_hash)
    detail_payload = canonical_payload(detail)
    tampered = replace(
        prepared,
        preflight_json=preflight_payload.json_bytes,
        preflight_hash=preflight_payload.content_hash,
        plan_preimage_json=plan_preimage_payload.json_bytes,
        plan_hash=str(plan_preimage_payload.content_hash),
        enqueue_detail=detail,
        enqueue_detail_json=detail_payload.json_bytes,
        enqueue_detail_hash=detail_payload.content_hash,
    )

    with pytest.raises(AppProcessError) as exc_info:
        persist_prepared_launch(
            reader=cast(ExperimentReaderProtocol, store),
            writer=cast(ExperimentWriterProtocol, store),
            prepared=tampered,
        )

    assert exc_info.value.details["reason"] == "prepared_launch_identity_mismatch"
    assert store.calls == []


def _fully_rehashed_work_launch(
    prepared: PreparedExperimentLaunch,
    request: ExperimentPlanningRequest,
    *,
    track: ExperimentTrack,
    fold_session_counts: tuple[int, ...] | None = None,
    holdout_session_count: int | None = None,
) -> PreparedExperimentLaunch:
    detail = cast("dict[str, object]", orjson.loads(prepared.enqueue_detail_json))
    preflight = cast("dict[str, object]", detail["preflight"])
    original_work = cast("dict[str, object]", preflight["work"])
    original_workload = cast("dict[str, object]", original_work["workload"])
    original_fold_counts = tuple(
        cast("list[int]", original_workload["fold_session_counts"])
    )
    original_holdout_count = cast("int", original_workload["holdout_session_count"])
    forged_work = plan_experiment_work(
        ExperimentPlanningSpec(
            matrix=request.matrix_spec,
            track=track,
            workload=ValidationWorkload(
                fold_session_counts=(
                    original_fold_counts
                    if fold_session_counts is None
                    else fold_session_counts
                ),
                holdout_session_count=(
                    original_holdout_count
                    if holdout_session_count is None
                    else holdout_session_count
                ),
            ),
            cost_model=request.cost_model,
            budget=request.budget,
            seed=request.seed,
            worker_count=request.worker_count,
            failure_policy=request.failure_policy,
        )
    )
    encoded_work = canonical_payload(
        preflight_codec_module._work_payload(forged_work, request.matrix_spec)
    )
    preflight["work"] = orjson.loads(encoded_work.json_bytes)
    counts = cast("dict[str, object]", preflight["counts"])
    counts.update(
        {
            "budget_run_count": forged_work.estimate.total_run_count,
            "estimated_trading_sessions": (
                forged_work.estimate.estimated_trading_sessions
            ),
            "estimated_disk_bytes": forged_work.estimate.estimated_disk_bytes,
        }
    )
    checks = cast("list[dict[str, object]]", preflight["checks"])
    budget_observed = {
        "total_run_count": forged_work.estimate.total_run_count,
        "estimated_trading_sessions": (forged_work.estimate.estimated_trading_sessions),
        "estimated_disk_bytes": forged_work.estimate.estimated_disk_bytes,
    }
    checks[5]["observed"] = budget_observed
    gates = (
        *prepared.gates[:5],
        replace(prepared.gates[5], observed=budget_observed),
    )
    preflight_payload = canonical_payload(preflight)
    plan_preimage = cast("dict[str, object]", detail["plan_preimage"])
    plan_preimage["work_plan_hash"] = forged_work.plan_hash
    plan_preimage["gate_payload_hashes"] = [str(item.payload_hash) for item in gates]
    plan_preimage["preflight_hash"] = str(preflight_payload.content_hash)
    plan_preimage_payload = canonical_payload(plan_preimage)
    detail["preflight_hash"] = str(preflight_payload.content_hash)
    detail["plan_hash"] = str(plan_preimage_payload.content_hash)
    detail_payload = canonical_payload(detail)
    return replace(
        prepared,
        gates=gates,
        gate_payload_hashes=tuple(item.payload_hash for item in gates),
        preflight_json=preflight_payload.json_bytes,
        preflight_hash=preflight_payload.content_hash,
        plan_preimage_json=plan_preimage_payload.json_bytes,
        plan_hash=str(plan_preimage_payload.content_hash),
        enqueue_detail=detail,
        enqueue_detail_json=detail_payload.json_bytes,
        enqueue_detail_hash=detail_payload.content_hash,
    )


@pytest.mark.parametrize("tamper", ["track", "workload"])
def test_fully_rehashed_work_drift_blocks_before_first_write(tamper: str) -> None:
    store = _Store()
    request = _request()
    prepared = _process(store)._prepare(request).launch
    assert prepared is not None
    tampered = (
        _fully_rehashed_work_launch(
            prepared,
            request,
            track=ExperimentTrack.RESEARCH_ONLY,
        )
        if tamper == "track"
        else _fully_rehashed_work_launch(
            prepared,
            request,
            track=ExperimentTrack.PROMOTION,
            fold_session_counts=(1, 1, 1),
            holdout_session_count=1,
        )
    )

    with pytest.raises(AppProcessError) as exc_info:
        persist_prepared_launch(
            reader=cast(ExperimentReaderProtocol, store),
            writer=cast(ExperimentWriterProtocol, store),
            prepared=tampered,
        )

    assert exc_info.value.details["reason"] == "prepared_launch_identity_mismatch"
    assert store.calls == []


def _fully_rehashed_protocol_launch(
    prepared: PreparedExperimentLaunch,
    request: ExperimentPlanningRequest,
    protocol: ValidationProtocolRequest,
) -> PreparedExperimentLaunch:
    detail = cast(
        "dict[str, object]",
        orjson.loads(prepared.enqueue_detail_json),
    )
    preflight = cast("dict[str, object]", detail["preflight"])
    validation = cast("dict[str, object]", preflight["validation"])
    validation["protocol"] = canonical_validation_protocol_payload(protocol)
    runtime = RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily",),
        max_lookback_sessions=21,
        requires_pit_universe=True,
        forward_horizon_sessions=2,
        holding_period_sessions=5,
        execution_lag_sessions=1,
    )
    evidence = ResearchValidationAuthorityEvidence.create(
        protocol=protocol,
        snapshot_identity=request.snapshot_identity,
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash="9" * 64,
        requires_pit_universe=True,
        dataset_bindings=request.dataset_requirements,
    )
    protocol_hash = canonical_validation_protocol_hash(protocol)
    authority = cast("dict[str, object]", preflight["authority"])
    authority.update(
        {
            "payload_hash": evidence.payload_hash,
            "runtime_evidence_hash": evidence.runtime_evidence_hash,
            "universe_membership_hash": evidence.universe_membership_hash,
            "membership_projection_hash": evidence.membership_projection_hash,
            "requires_pit_universe": evidence.requires_pit_universe,
            "snapshot_identity": {
                "snapshot_id": evidence.snapshot_identity.snapshot_id,
                "manifest_hash": evidence.snapshot_identity.manifest_hash,
            },
            "dataset_bindings": [
                item.as_payload() for item in evidence.dataset_bindings
            ],
            "protocol_hash": protocol_hash,
            "summaries": evidence.summaries,
        }
    )
    authority_check = cast(
        "dict[str, object]",
        cast("list[object]", preflight["checks"])[2],
    )
    check_summaries = dict(evidence.summaries)
    check_summaries["eligibility"] = {
        **check_summaries["eligibility"],
        "eligible_month_count": len(
            compile_validation_protocol(protocol).eligible_months
        ),
    }
    authority_check["observed"] = {
        "ready": True,
        "authority_payload_hash": evidence.payload_hash,
        "runtime_evidence_hash": evidence.runtime_evidence_hash,
        "authority_protocol_hash": protocol_hash,
        "declared_protocol_hash": protocol_hash,
        "summaries": check_summaries,
    }
    identities = cast("dict[str, object]", preflight["identities"])
    identities["request_hash"] = planning_request_hash(
        replace(request, validation_request=protocol)
    )
    gates = (
        *prepared.gates[:2],
        replace(prepared.gates[2], observed=authority_check["observed"]),
        *prepared.gates[3:],
    )
    preflight_payload = canonical_payload(preflight)
    plan_preimage = cast("dict[str, object]", detail["plan_preimage"])
    plan_preimage["request_hash"] = identities["request_hash"]
    plan_preimage["gate_payload_hashes"] = [str(item.payload_hash) for item in gates]
    plan_preimage["validation_authority"] = {
        "payload_hash": evidence.payload_hash,
        "runtime_evidence_hash": evidence.runtime_evidence_hash,
        "universe_membership_hash": evidence.universe_membership_hash,
        "membership_projection_hash": evidence.membership_projection_hash,
        "requires_pit_universe": evidence.requires_pit_universe,
        "dataset_bindings": [item.as_payload() for item in evidence.dataset_bindings],
    }
    plan_preimage["preflight_hash"] = str(preflight_payload.content_hash)
    plan_preimage_payload = canonical_payload(plan_preimage)
    detail["preflight_hash"] = str(preflight_payload.content_hash)
    detail["plan_hash"] = str(plan_preimage_payload.content_hash)
    detail_payload = canonical_payload(detail)
    return replace(
        prepared,
        gates=gates,
        gate_payload_hashes=tuple(item.payload_hash for item in gates),
        preflight_json=preflight_payload.json_bytes,
        preflight_hash=preflight_payload.content_hash,
        plan_preimage_json=plan_preimage_payload.json_bytes,
        plan_hash=str(plan_preimage_payload.content_hash),
        enqueue_detail=detail,
        enqueue_detail_json=detail_payload.json_bytes,
        enqueue_detail_hash=detail_payload.content_hash,
    )


@pytest.mark.parametrize("source", ["calendar", "membership"])
def test_fully_rehashed_source_manifest_drift_fails_persisted_reconstruction(
    source: str,
) -> None:
    request = _request()
    prepared = _process(_Store())._prepare(request).launch
    assert prepared is not None
    protocol = request.validation_request
    if source == "calendar":
        calendar = protocol.trading_calendar
        forged = replace(
            protocol,
            trading_calendar=TradingCalendarEvidence.create(
                calendar_id=calendar.calendar_id,
                version=calendar.version,
                source=TradingCalendarSourceIdentity(
                    dataset_id=calendar.dataset_id,
                    snapshot_id=calendar.snapshot_id,
                    manifest_hash="f" * 64,
                    certified_through=calendar.certified_through,
                    authority_as_of=calendar.authority_as_of,
                ),
                month_closures=calendar.month_closures,
            ),
        )
    else:
        forged = replace(
            protocol,
            membership_source=replace(
                protocol.membership_source,
                manifest_hash="f" * 64,
            ),
        )
    tampered = _fully_rehashed_protocol_launch(prepared, request, forged)

    with pytest.raises(AppProcessError) as exc_info:
        planning_process_module.reconstruct_preflight_report(tampered.enqueue_detail)

    assert exc_info.value.details["code"] == "PREFLIGHT_DETAIL_INVALID"


def test_rehashed_planning_decision_date_drift_blocks_before_first_write() -> None:
    store = _Store()
    request = _request()
    prepared = _process(store)._prepare(request).launch
    assert prepared is not None
    forged = replace(
        request.validation_request,
        planning_decision_date=request.validation_request.planning_decision_date
        - timedelta(days=1),
    )
    tampered = _fully_rehashed_protocol_launch(prepared, request, forged)

    with pytest.raises(AppProcessError) as exc_info:
        persist_prepared_launch(
            reader=cast(ExperimentReaderProtocol, store),
            writer=cast(ExperimentWriterProtocol, store),
            prepared=tampered,
        )

    assert exc_info.value.details["reason"] == "prepared_launch_identity_mismatch"
    assert store.calls == []


def test_oversized_canonical_preflight_is_blocked_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        launch_material_module,
        "_MAX_ENQUEUE_DETAIL_BYTES",
        1,
        raising=False,
    )
    store = _Store()
    process = _process(store)

    report = process.preflight(_request())

    assert report.status is ExperimentPreflightStatus.BLOCKED
    assert report.plan_hash is None
    detail_check = next(
        check for check in report.checks if check.rule_id == "preflight_detail"
    )
    assert detail_check.code == "PREFLIGHT_DETAIL_TOO_LARGE"
    assert detail_check.observed["canonical_detail_bytes"] > 1
    assert detail_check.policy["maximum_canonical_detail_bytes"] == 1
    with pytest.raises(AppProcessError) as exc_info:
        process.launch(_request(), confirmed_plan_hash="0" * 64)
    assert exc_info.value.details["code"] == "PREFLIGHT_DETAIL_TOO_LARGE"
    assert store.calls == []


def test_partial_draft_replays_exactly_and_queued_replay_is_zero_write() -> None:
    store = _Store()
    store.fail_fold_call = 3
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None

    with pytest.raises(AppProcessError):
        process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert store.projection is not None
    assert store.projection.record.status is ExperimentStatus.DRAFT
    assert len(store.folds) == 2

    store.fail_fold_call = None
    store.calls.clear()
    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert receipt.status == "queued"
    assert len(store.folds) == 8

    store.calls.clear()
    replay = process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert replay == receipt
    assert store.calls == []


def test_partial_draft_rejects_immutable_request_drift_without_writes() -> None:
    store = _Store()
    store.fail_fold_call = 3
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None

    with pytest.raises(AppProcessError):
        process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert store.projection is not None
    assert store.projection.record.status is ExperimentStatus.DRAFT

    drifted = replace(request, seed=request.seed + 1)
    drifted_report = process.preflight(drifted)
    assert drifted_report.plan_hash is not None
    assert drifted_report.plan_hash != report.plan_hash
    store.fail_fold_call = None
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        process.launch(
            drifted,
            confirmed_plan_hash=drifted_report.plan_hash,
        )

    assert exc_info.value.details == {
        "code": "EXPERIMENT_ALREADY_EXISTS",
        "reason": "durable_launch_request_mismatch",
        "durable_request_hash": planning_request_hash(request),
        "caller_request_hash": planning_request_hash(drifted),
    }
    assert store.calls == []

    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert receipt.status == "queued"


def test_partial_draft_fences_full_request_identity_before_preflight() -> None:
    store = _Store()
    store.fail_fold_call = 3
    request = _request()
    process = _process(store)
    report = process.preflight(request)
    assert report.plan_hash is not None

    with pytest.raises(AppProcessError):
        process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert store.projection is not None
    assert store.projection.record.status is ExperimentStatus.DRAFT

    drifted = replace(
        request,
        budget=replace(request.budget, disk_byte_limit=1),
    )
    certification = _BombCertificationProbe()
    executor = _BombExecutorProbe()
    authority = _BombAuthorityProbe()
    store.fail_fold_call = None
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        _process(
            store,
            certification=certification,
            executor=executor,
            authority=authority,
        ).launch(drifted, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["code"] == "EXPERIMENT_ALREADY_EXISTS"
    assert exc_info.value.details["reason"] == "durable_launch_request_mismatch"
    assert exc_info.value.details["durable_request_hash"] == planning_request_hash(
        request
    )
    assert exc_info.value.details["caller_request_hash"] == planning_request_hash(
        drifted
    )
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []

    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert receipt.status == "queued"


def test_legacy_partial_draft_recovers_without_backfilling_creation_detail() -> None:
    store = _Store()
    store.fail_fold_call = 3
    request = _request()
    process = _process(store)
    report = process.preflight(request)
    assert report.plan_hash is not None

    with pytest.raises(AppProcessError):
        process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert store.creation_event is not None
    store.creation_event = replace(
        store.creation_event,
        detail={},
        detail_hash=canonical_payload({}).content_hash,
    )
    store.fail_fold_call = None
    store.calls.clear()

    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert receipt.status == "queued"
    assert store.creation_event.detail == {}


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("malformed-detail", "durable_creation_identity_invalid"),
        ("duplicate-event", "durable_creation_event_invalid"),
    ],
)
def test_partial_draft_creation_identity_corruption_fails_before_probes(
    mutation: str,
    reason: str,
) -> None:
    store = _Store()
    store.fail_fold_call = 3
    request = _request()
    process = _process(store)
    report = process.preflight(request)
    assert report.plan_hash is not None

    with pytest.raises(AppProcessError):
        process.launch(request, confirmed_plan_hash=report.plan_hash)
    assert store.creation_event is not None
    if mutation == "malformed-detail":
        malformed = {**store.creation_event.detail, "unexpected": True}
        store.creation_event = replace(
            store.creation_event,
            detail=malformed,
            detail_hash=canonical_payload(malformed).content_hash,
        )
    else:
        store.events.append(
            replace(store.creation_event, event_id="duplicate-creation-event")
        )
    certification = _BombCertificationProbe()
    executor = _BombExecutorProbe()
    authority = _BombAuthorityProbe()
    store.fail_fold_call = None
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        _process(
            store,
            certification=certification,
            executor=executor,
            authority=authority,
        ).launch(request, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["code"] == "EXPERIMENT_LAUNCH_CONFLICT"
    assert exc_info.value.details["reason"] == reason
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


def test_committed_enqueue_retry_replays_before_every_planning_probe() -> None:
    store = _Store()
    request = _request()
    process = _process(store)
    report = process.preflight(request)
    assert report.plan_hash is not None
    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)
    certification = _BombCertificationProbe()
    executor = _BombExecutorProbe()
    authority = _BombAuthorityProbe()
    store.calls.clear()

    replay = _process(
        store,
        certification=certification,
        executor=executor,
        authority=authority,
    ).launch(request, confirmed_plan_hash=report.plan_hash)

    assert replay == receipt
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


def test_committed_enqueue_rejects_caller_request_drift_before_probes() -> None:
    store = _Store()
    request = _request()
    process = _process(store)
    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    drifted = replace(
        request,
        strategy_record=replace(request.strategy_record, name="drifted name"),
    )
    certification = _BombCertificationProbe()
    executor = _BombExecutorProbe()
    authority = _BombAuthorityProbe()
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        _process(
            store,
            certification=certification,
            executor=executor,
            authority=authority,
        ).launch(drifted, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["code"] == "EXPERIMENT_ALREADY_EXISTS"
    assert exc_info.value.details["reason"] == "durable_launch_request_mismatch"
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


def test_stateful_strategy_mapping_is_rejected_without_iteration_or_probes() -> None:
    class _StatefulSpec(dict[str, object]):
        iterations = 0

        def items(self):
            self.iterations += 1
            return super().items()

    store = _Store()
    request = _request()
    process = _process(store)
    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    stateful = _StatefulSpec(request.strategy_record.spec_json)
    drifted = replace(
        request,
        strategy_record=replace(request.strategy_record, spec_json=stateful),
    )
    certification = _BombCertificationProbe()
    executor = _BombExecutorProbe()
    authority = _BombAuthorityProbe()
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        _process(
            store,
            certification=certification,
            executor=executor,
            authority=authority,
        ).launch(drifted, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_strategy_record_identity",
    }
    assert stateful.iterations == 0
    assert certification.calls == []
    assert executor.calls == 0
    assert authority.calls == 0
    assert store.calls == []


def test_draft_extra_fail_gate_blocks_before_enqueue() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None

    def _inject_extra_fail_gate() -> None:
        expected = next(iter(store.gates.values()))
        extra = replace(
            expected,
            evaluation_id=f"{request.experiment_id}:preflight:extra:unexpected",
            rule_id="unexpected",
            outcome="fail",
        )
        store.gates[extra.evaluation_id] = extra

    store.gate_read_hook = _inject_extra_fail_gate

    with pytest.raises(AppProcessError) as exc_info:
        process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["reason"] == "gate_readback_set_mismatch"
    assert store.projection is not None
    assert store.projection.record.status is ExperimentStatus.DRAFT
    assert "enqueue" not in store.calls
    assert store.events == []


def test_queued_replay_rejects_durable_plan_hash_drift_without_writes() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)

    event = store.events[-1]
    drifted_detail = {"plan_hash": "f" * 64}
    store.events[-1] = replace(
        event,
        detail=drifted_detail,
        detail_hash=canonical_payload(drifted_detail).content_hash,
    )
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["code"] == "PLAN_HASH_MISMATCH"
    assert store.calls == []


def test_queued_replay_rejects_durable_preflight_hash_drift_without_writes() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)

    event = store.events[-1]
    store.events[-1] = replace(
        event,
        detail_hash=canonical_payload({"drift": True}).content_hash,
    )
    store.calls.clear()

    with pytest.raises(AppProcessError) as exc_info:
        process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["reason"] == "enqueue_event_preflight_detail_mismatch"
    assert store.calls == []


def _progress_store_to_running(store: _Store) -> None:
    assert store.projection is not None
    projection = store.projection
    store.projection = replace(
        projection,
        record=replace(
            projection.record,
            status=ExperimentStatus.RUNNING,
            stage=ExperimentStage.EXPLORATION,
        ),
        revision=max(2, projection.revision + 1),
        updated_at=NOW + timedelta(seconds=1),
    )
    key = next(iter(store.folds))
    fold = store.folds[key]
    store.folds[key] = replace(
        fold,
        projection=replace(
            fold.projection,
            status=ExperimentStatus.RUNNING,
            claim_owner_token="worker-1",
            revision=1,
            updated_at=NOW + timedelta(seconds=1),
        ),
    )


def test_progressed_exact_aggregate_replay_returns_original_queued_receipt() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    original = process.launch(request, confirmed_plan_hash=report.plan_hash)
    expected = next(iter(store.gates.values()))
    later_gate = replace(
        expected,
        evaluation_id=f"{request.experiment_id}:running:later",
        rule_id="later_runtime_gate",
        outcome="pass",
    )
    store.gates[later_gate.evaluation_id] = later_gate
    _progress_store_to_running(store)
    store.calls.clear()

    replay = process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert replay == original
    assert replay.status == ExperimentStatus.QUEUED.value
    assert replay.revision == 1
    assert store.calls == []


def test_queued_to_running_read_race_retries_to_one_stable_launch_receipt() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    original = process.launch(request, confirmed_plan_hash=report.plan_hash)
    store.calls.clear()
    store.projection_read_hook = lambda: _progress_store_to_running(store)

    replay = process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert replay == original
    assert store.calls == []


def test_draft_child_read_race_reconciles_concurrent_enqueue_and_fold_claim() -> None:
    store = _Store()
    outer = _process(store)
    concurrent = _process(store)
    request = _request()
    report = outer.preflight(request)
    assert report.plan_hash is not None
    concurrent_receipts = []
    completed_write_counts = []

    def _enqueue_and_claim() -> None:
        concurrent_receipts.append(
            concurrent.launch(request, confirmed_plan_hash=report.plan_hash)
        )
        _progress_store_to_running(store)
        completed_write_counts.append(len(store.calls))

    store.fold_read_hook = _enqueue_and_claim

    receipt = outer.launch(request, confirmed_plan_hash=report.plan_hash)

    assert concurrent_receipts == [receipt]
    assert receipt.status == ExperimentStatus.QUEUED.value
    assert receipt.revision == 1
    assert completed_write_counts == [len(store.calls)]
    assert store.calls.count("enqueue") == 1
    assert len(store.events) == 1


def test_continuous_root_revision_drift_fails_consistently_without_writes() -> None:
    store = _Store()
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None
    process.launch(request, confirmed_plan_hash=report.plan_hash)
    store.calls.clear()

    def _churn_revision() -> None:
        assert store.projection is not None
        store.projection = replace(
            store.projection,
            revision=store.projection.revision + 1,
            updated_at=store.projection.updated_at + timedelta(microseconds=1),
        )
        store.projection_read_hook = _churn_revision

    store.projection_read_hook = _churn_revision

    with pytest.raises(AppProcessError) as exc_info:
        process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert exc_info.value.details["reason"] == "concurrent_experiment_update"
    assert store.calls == []


def test_concurrent_exact_enqueue_reconciles_to_durable_receipt() -> None:
    store = _Store()
    store.raise_after_enqueue = True
    process = _process(store)
    request = _request()
    report = process.preflight(request)
    assert report.plan_hash is not None

    receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)

    assert receipt.status == "queued"
    assert receipt.queue_ordinal == 1
    assert len(store.events) == 1


def test_concurrent_exact_root_create_after_absent_projection_reconciles() -> None:
    store = _Store()
    first = _process(store)
    concurrent = _process(store)
    request = _request()
    report = first.preflight(request)
    assert report.plan_hash is not None
    concurrent_receipts = []

    store.projection_read_hook = lambda: concurrent_receipts.append(
        concurrent.launch(request, confirmed_plan_hash=report.plan_hash)
    )
    receipt = first.launch(request, confirmed_plan_hash=report.plan_hash)

    assert concurrent_receipts == [receipt]
    assert receipt.status == "queued"
    assert len(store.events) == 1
    assert len(store.folds) == receipt.fold_count
