"""Task 8 launch saga integration against the Task 7 research database."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    BacktestRunId,
    ContentHash,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldRole,
    FoldView,
    HoldoutClaimAuthorityCommand,
    HoldoutSelectionReason,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SchedulerLease,
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
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_execution_resolver import (
    DurableResearchExecutionResolver,
    FrozenResearchExecutionInputs,
    FrozenResearchInputRequest,
    ResearchExecutionRuntimeBuilders,
)
from ditto_application.builders.research_factor_registry import ResearchFactorBinding
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    read_durable_launch,
)
from ditto_application.processes.experiments.baseline_planning import (
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ResearchExecutionSemantics,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
    ResearchAssetLane,
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
    ExperimentPlanningProcess,
    ExperimentPlanningRequest,
    ExperimentSnapshotIdentity,
    ResearchCertificationProbe,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchDatasetRequirement,
    ResearchExecutorProbe,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
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
    compile_validation_protocol,
)
from ditto_features.expression.contracts import CompileIdentity
from ditto_strategy.models import StrategySpecRecord

_NOW = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)
_NOW_US = int(_NOW.timestamp() * 1_000_000)
_EXPERIMENT_ID = "exp-task8-integration-1"
_GATE_RULES = (
    "matrix",
    "executor",
    "authority",
    "history",
    "certification",
    "budget",
)


def _next_month(month: CalendarMonth) -> CalendarMonth:
    if month.month == 12:
        return CalendarMonth(month.year + 1, 1)
    return CalendarMonth(month.year, month.month + 1)


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
                snapshot_id="provider-snapshot-task8",
                manifest_hash=_exact_snapshot().manifest_hash,
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
            universe_id="csi_etf_broad",
            dataset_id="etf_daily",
            snapshot_id="provider-snapshot-task8",
            manifest_hash=_exact_snapshot().manifest_hash,
        ),
        planning_decision_date=_NOW.date(),
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


def _planning_request() -> ExperimentPlanningRequest:
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
    return ExperimentPlanningRequest(
        experiment_id=_EXPERIMENT_ID,
        research_cycle_id="cycle-task8-integration-1",
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
            status="draft",
        ),
        snapshot_identity=ExperimentSnapshotIdentity(
            snapshot_id="certified-snapshot-task8",
            manifest_hash=_exact_snapshot().manifest_hash,
        ),
        validation_request=validation_request,
        matrix_spec=matrix,
        promotion_objective=_objective(_EXPERIMENT_ID, matrix),
        dataset_requirements=(
            ResearchDatasetRequirement(
                dataset_id="etf_daily",
                expected_snapshot_ids=("provider-snapshot-task8",),
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
        created_at=_NOW,
    )


class _CertificationProbe:
    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        return ResearchCertificationResult(
            ready=True,
            profile=R3_RESEARCH_CERTIFICATION_PROFILE,
            dataset_ids=tuple(item.dataset_id for item in request.requirements),
            report_ids=("cert-report-task8",),
            reason_codes=(),
            snapshot_evidence=ResearchSnapshotEvidence(
                snapshot_id=request.snapshot_identity.snapshot_id,
                dataset_id="research-etf-rotation",
                manifest_hash=request.snapshot_identity.manifest_hash,
                source_snapshot_ids=("provider-snapshot-task8",),
                snapshot_start=request.required_from,
                snapshot_end=request.required_to,
                known_at_policy="sample_time",
                builder_version="research-builder-v1",
            ),
        )


class _ExecutorProbe:
    def probe(
        self,
        request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        registry = default_baseline_registry()
        baseline = resolve_planning_baseline(request.baseline, registry)
        factor_binding = _exact_factor_binding()
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
                universe_id="csi_etf_broad",
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
            factor_binding_hashes=(factor_binding.binding_hash,),
            baseline_runtime=BaselineRuntimeExecutorEvidence(
                base_spec_hash="f" * 64,
                resolved_spec_hash="b" * 64,
                parameter_hash="c" * 64,
                pipeline_execution_hash=f"{258:064x}",
                compiled_factor_set_hash=compiled_expressions_execution_hash(None),
                max_lookback_sessions=0,
                node_registry_manifest_hash="e" * 64,
                factor_registry_manifest_hash="d" * 64,
                factor_binding_hashes=(factor_binding.binding_hash,),
            ),
        )


class _AuthorityProbe:
    def probe(self, request):
        runtime = request.runtime_validation
        assert runtime is not None
        evidence = ResearchValidationAuthorityEvidence.create(
            protocol=request.declared_protocol,
            snapshot_identity=request.snapshot_identity,
            runtime_evidence_hash=runtime.payload_hash,
            universe_membership_hash="9" * 64,
            requires_pit_universe=True,
            dataset_bindings=request.declared_requirements,
        )
        return ResearchValidationAuthorityResult(True, None, None, None, evidence)


def _gates(reader: SQLiteExperimentReader):
    return tuple(
        reader.get_gate_evaluation(
            f"{_EXPERIMENT_ID}:preflight:{index}:{rule_id}",
        )
        for index, rule_id in enumerate(_GATE_RULES, start=1)
    )


def _persisted_snapshot(reader: SQLiteExperimentReader, receipt):
    experiment_id = ExperimentId(_EXPERIMENT_ID)
    projection = reader.get_experiment_projection(experiment_id)
    launch_spec = reader.get_launch_spec(experiment_id)
    candidates = reader.list_candidates(experiment_id)
    folds = reader.list_folds(experiment_id)
    gates = _gates(reader)
    events = reader.list_status_events(experiment_id)

    assert receipt.status == ExperimentStatus.QUEUED.value
    assert projection is not None
    assert projection.record.status is ExperimentStatus.QUEUED
    assert launch_spec is not None
    assert launch_spec.promotion_objective == _planning_request().promotion_objective
    assert projection.queue_ordinal == receipt.queue_ordinal
    assert len(candidates) == receipt.candidate_count == 2
    assert len(folds) == receipt.fold_count == 4 * len(candidates)
    for candidate in candidates:
        candidate_folds = tuple(
            fold
            for fold in folds
            if fold.spec.key.candidate_id == candidate.candidate_id
        )
        fold_rows = [
            (fold.spec.ordinal, fold.spec.fold_role) for fold in candidate_folds
        ]
        assert fold_rows == [
            (1, FoldRole.EXPLORATION),
            (2, FoldRole.WALK_FORWARD),
            (3, FoldRole.WALK_FORWARD),
            (4, FoldRole.HOLDOUT),
        ]
    assert len(gates) == 6
    assert all(gate is not None for gate in gates)
    assert tuple(gate.rule_id for gate in gates if gate is not None) == _GATE_RULES
    assert all(reader.list_attempts(fold.spec.key) == () for fold in folds)
    enqueue_events = tuple(
        event
        for event in events
        if event.subject_type is StatusSubjectType.EXPERIMENT
        and event.subject_revision == 1
    )
    assert len(enqueue_events) == 1
    detail = enqueue_events[0].detail
    assert detail["plan_hash"] == receipt.plan_hash
    assert (
        detail["preflight_hash"]
        == canonical_payload(detail["preflight"]).content_hash.value
    )
    assert enqueue_events[0].detail_hash == canonical_payload(detail).content_hash
    return launch_spec, projection, candidates, folds, gates, events


def _complete_planning_fold(
    writer: SQLiteExperimentWriter,
    fold: FoldView,
    lease: SchedulerLease,
) -> None:
    attempt_id = AttemptId(
        f"attempt-complete-{fold.spec.key.candidate_id}-{fold.spec.key.fold_id}"
    )
    attempt_spec = AttemptPersistenceSpec(
        attempt_id,
        fold.spec.key,
        1,
        None,
        None,
        ContentHash("8" * 64),
        _NOW,
    )
    initial = AttemptProjection(
        attempt_id,
        ExperimentStatus.QUEUED,
        None,
        None,
        None,
        _NOW,
        _NOW,
        0,
    )
    fold_projection, attempt_projection = writer.claim_fold_and_add_attempt(
        fold.spec.key,
        attempt_spec,
        initial,
        expected_fold_revision=fold.projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=_NOW_US + 4,
        occurred_at=_NOW,
    )
    running = writer.transition_attempt(
        attempt_id,
        target_status=ExperimentStatus.RUNNING,
        backtest_run_id=BacktestRunId(f"run-{attempt_id}"),
        checkpoint_ref=None,
        failure_code=None,
        expected_revision=attempt_projection.revision,
        lease_fence=lease.fence,
        now_epoch_us=_NOW_US + 5,
        occurred_at=_NOW,
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
        now_epoch_us=_NOW_US + 6,
        occurred_at=_NOW,
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
        now_epoch_us=_NOW_US + 7,
        occurred_at=_NOW,
        reason_code="fold_completed",
        detail={},
    )


def _advance_planning_launch_to_candidate_selection(
    reader: SQLiteExperimentReader,
    writer: SQLiteExperimentWriter,
) -> SchedulerLease:
    experiment_id = ExperimentId(_EXPERIMENT_ID)
    lease = writer.try_claim_lease(
        experiment_id,
        "planning-holdout-owner",
        expected_revision=reader.get_scheduler_slot().revision,
        now_epoch_us=_NOW_US,
        lease_until_epoch_us=_NOW_US + 60_000_000,
    )
    assert lease is not None
    writer.transition_scheduled_experiment(
        experiment_id,
        target_status=ExperimentStatus.RUNNING,
        target_stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        expected_revision=1,
        lease_fence=lease.fence,
        now_epoch_us=_NOW_US + 1,
        occurred_at=_NOW,
        attempt_started=False,
        precondition_repairable=False,
        reason_code="scheduler_dispatch",
        detail={},
    )
    folds = reader.list_folds(experiment_id)
    for fold in folds:
        if fold.spec.fold_role is FoldRole.EXPLORATION:
            _complete_planning_fold(writer, fold, lease)
    projection = writer.advance_experiment_stage(
        experiment_id,
        target_stage=ExperimentStage.WALK_FORWARD,
        expected_revision=2,
        lease_fence=lease.fence,
        now_epoch_us=_NOW_US + 2,
        occurred_at=_NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "exploration"},
    )
    assert projection.revision == 3
    for fold in folds:
        if fold.spec.fold_role is FoldRole.WALK_FORWARD:
            _complete_planning_fold(writer, fold, lease)
    projection = writer.advance_experiment_stage(
        experiment_id,
        target_stage=ExperimentStage.CANDIDATE_SELECTION,
        expected_revision=3,
        lease_fence=lease.fence,
        now_epoch_us=_NOW_US + 3,
        occurred_at=_NOW,
        reason_code="scheduler_stage_complete",
        detail={"completed_stage": "walk_forward"},
    )
    assert projection.revision == 4
    return lease


def test_launch_is_durable_and_exact_hash_replay_is_zero_write(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=_CertificationProbe(),
        executor_probe=_ExecutorProbe(),
        authority_probe=_AuthorityProbe(),
    )
    request = _planning_request()

    try:
        report = process.preflight(request)
        assert report.plan_hash is not None

        receipt = process.launch(request, confirmed_plan_hash=report.plan_hash)
        snapshot = _persisted_snapshot(reader, receipt)

        changes_before_replay = database.get_connection().total_changes
        replay = process.launch(request, confirmed_plan_hash=report.plan_hash)

        assert replay == receipt
        assert database.get_connection().total_changes == changes_before_replay
        assert _persisted_snapshot(reader, replay) == snapshot
    finally:
        database.close_all()

    reopened = ResearchExperimentDatabase(tmp_path)
    reopened.initialize()
    try:
        durable_reader = SQLiteExperimentReader(reopened)
        assert _persisted_snapshot(durable_reader, receipt) == snapshot
    finally:
        reopened.close_all()


def test_real_planning_launch_passes_storage_holdout_claim_preflight(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=_CertificationProbe(),
        executor_probe=_ExecutorProbe(),
        authority_probe=_AuthorityProbe(),
    )
    request = _planning_request()

    try:
        report = process.preflight(request)
        assert report.plan_hash is not None
        process.launch(request, confirmed_plan_hash=report.plan_hash)
        launch = reader.get_launch_spec(ExperimentId(_EXPERIMENT_ID))
        assert launch is not None
        lease = _advance_planning_launch_to_candidate_selection(reader, writer)
        selected = next(
            candidate.candidate_id
            for candidate in launch.candidates
            if not candidate.is_baseline
        )

        receipt = writer.claim_holdout_candidate(
            HoldoutClaimAuthorityCommand(
                experiment_id=launch.experiment_id,
                candidate_id=selected,
                expected_revision=4,
                expected_selection_evidence_hash=ContentHash("5" * 64),
                operator_confirmation="operator reviewed immutable evidence",
                selection_reason=HoldoutSelectionReason(
                    "objective_review",
                    "Candidate won the registered objective review.",
                ),
                resolved_reproduction_fingerprint=ContentHash("4" * 64),
                occurred_at=_NOW,
            ),
            lease_fence=lease.fence,
            now_epoch_us=_NOW_US + 8,
        )

        assert receipt.experiment_revision == 5
        assert receipt.claim.fold_key.candidate_id == selected
        assert reader.get_holdout_claim_for_experiment(launch.experiment_id) is not None
    finally:
        database.close_all()


def test_invalid_promotion_objective_is_rejected_before_probe_or_sql_write(
    tmp_path: Path,
) -> None:
    class _BombProbe:
        def assess(self, _request):
            raise AssertionError("certification probe must not run")

        def probe(self, _request):
            raise AssertionError("research probe must not run")

    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    request = _planning_request()
    current = request.promotion_objective.trial_family.current_members
    substituted = replace(current[1], parameter_hash=ContentHash("f" * 64))
    request = replace(
        request,
        promotion_objective=replace(
            request.promotion_objective,
            trial_family=TrialFamilyDeclaration(
                request.promotion_objective.trial_family.family_id,
                (current[0], substituted),
            ),
        ),
    )
    bomb = _BombProbe()
    process = ExperimentPlanningProcess(
        reader=SQLiteExperimentReader(database),
        writer=SQLiteExperimentWriter(database),
        certification_probe=cast("ResearchCertificationProbe", bomb),
        executor_probe=cast("ResearchExecutorProbe", bomb),
        authority_probe=cast("ResearchValidationAuthorityProbe", bomb),
    )
    before = database.get_connection().total_changes

    try:
        report = process.preflight(request)
        with pytest.raises(AppProcessError) as exc_info:
            process.launch(request, confirmed_plan_hash="0" * 64)

        assert report.status.value == "blocked"
        assert report.checks[0].reason == "promotion_current_trial_family_mismatch"
        assert exc_info.value.details == {
            "code": "SPEC_INVALID",
            "reason": "promotion_current_trial_family_mismatch",
        }
        assert database.get_connection().total_changes == before
    finally:
        database.close_all()


class _ExactStrategyReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def get_spec(self, strategy_id: str, version: int) -> StrategySpecRecord | None:
        self.calls.append((strategy_id, version))
        if strategy_id != "seed_etf_rotation" or version not in {2, 3}:
            return None
        return StrategySpecRecord(
            strategy_id=strategy_id,
            name="ETF rotation",
            spec_json={"strategy_id": strategy_id},
            version=version,
            status="published" if version == 2 else "draft",
        )


def _exact_factor_binding() -> ResearchFactorBinding:
    return ResearchFactorBinding(
        factor_id="etf_momentum",
        version=1,
        spec_hash="9" * 64,
        compile_identity=CompileIdentity(
            compile_input_hash="1" * 64,
            operator_fingerprint="2" * 64,
            compiler_fingerprint="3" * 64,
            cache_key="4" * 64,
            engine_codegen_version="polars-codegen-v1",
            analysis_version="factor-analysis-v1",
            polars_version="1.0.0",
            expr_serialization_format="polars-expr-v1",
            operator_versions=(("rank", "1"),),
            global_compile_flags=("grain=1d",),
        ),
        compiled_expression_hash="8" * 64,
        analysis_execution_hash="7" * 64,
    )


class _ExactRuntimeBuilder:
    def __init__(
        self,
        *,
        lane: str = "etf_rotation",
        frequency: str = "M",
        compiled_expressions: CompiledExpressions | None = None,
        baseline_pipeline_execution_hash: str | None = None,
        required_datasets: tuple[str, ...] = ("etf_daily",),
        baseline_strategy_id: str = "seed_etf_rotation",
        baseline_strategy_version: int = 2,
    ) -> None:
        self._lane = lane
        self._frequency = frequency
        self._compiled_expressions = compiled_expressions
        self._baseline_pipeline_execution_hash = baseline_pipeline_execution_hash
        self._required_datasets = required_datasets
        self._baseline_strategy_id = baseline_strategy_id
        self._baseline_strategy_version = baseline_strategy_version
        self.calls: list[tuple[int, str]] = []

    def build(self, **kwargs: object) -> ResearchStrategyRuntime:
        record = cast("StrategySpecRecord", kwargs["record"])
        self.calls.append((record.version, record.status))
        if record.version == 2:
            base_hash = "f" * 64
            resolved_hash = "b" * 64
            parameter_hash = "c" * 64
            strategy_id = self._baseline_strategy_id
            strategy_version = self._baseline_strategy_version
        else:
            base_hash = "a" * 64
            resolved_hash = f"{2:064x}"
            parameter_hash = f"{130:064x}"
            strategy_id = record.strategy_id
            strategy_version = record.version
        factor_binding = _exact_factor_binding()
        pipeline_execution_hash = f"{258:064x}"
        if record.version == 2 and self._baseline_pipeline_execution_hash is not None:
            pipeline_execution_hash = self._baseline_pipeline_execution_hash
        return cast(
            "ResearchStrategyRuntime",
            SimpleNamespace(
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                version_status=record.status,
                base_spec_hash=base_hash,
                resolved_spec_hash=resolved_hash,
                parameter_hash=parameter_hash,
                node_registry_manifest_hash="e" * 64,
                pipeline_execution_hash=pipeline_execution_hash,
                compiled_expressions=self._compiled_expressions,
                factor_registry_manifest_hash="d" * 64,
                used_factor_bindings=(factor_binding,),
                legacy_spec=SimpleNamespace(
                    universe="csi_etf_broad",
                    required_datasets=self._required_datasets,
                    benchmark=None,
                    execution=SimpleNamespace(
                        frequency=self._frequency,
                        default_order_type=SimpleNamespace(value="market"),
                    ),
                ),
                resolved_spec=SimpleNamespace(
                    strategy_kind=SimpleNamespace(value=self._lane)
                ),
            ),
        )


def _runtime_builders(
    candidate: _ExactRuntimeBuilder,
    published_baseline: _ExactRuntimeBuilder,
) -> ResearchExecutionRuntimeBuilders:
    return ResearchExecutionRuntimeBuilders(
        candidate=cast("ResearchRuntimeBuilder", candidate),
        published_baseline=cast(
            "PublishedBaselineRuntimeBuilder",
            published_baseline,
        ),
    )


def _instrument_rules_artifact(
    source_snapshot_id: str = "provider-snapshot-task8",
) -> VerifiedInstrumentRulesArtifact:
    rules_frame = pl.DataFrame(
        {
            "instrument_code": ["510300.SH"],
            "instrument_id": [2_000_001],
            "asset_class": ["etf"],
            "exchange": ["XSHG"],
            "currency": ["CNY"],
            "tick_size": [0.001],
            "lot_size": [100],
            "multiplier": [1.0],
            "board_segment": ["fund"],
            "lifecycle_state": ["normal"],
            "ipo_date": [date(2012, 5, 28)],
            "delisting_date": [None],
            "as_of_date": [date(2026, 1, 1)],
            "known_at": [date(2025, 12, 31)],
            "settlement_cycle": [1],
            "fund_settlement_cycle": [0],
            "price_limit_pct": [0.1],
            "order_types_supported": [["market", "limit"]],
            "call_auction_sessions": [["open", "close"]],
            "commission_rate": [0.0003],
            "min_commission": [5.0],
            "stamp_duty_rate": [0.0],
            "transfer_fee_rate": [0.00001],
            "source_snapshot_id": [source_snapshot_id],
        },
        schema={
            "instrument_code": pl.String,
            "instrument_id": pl.Int64,
            "asset_class": pl.String,
            "exchange": pl.String,
            "currency": pl.String,
            "tick_size": pl.Float64,
            "lot_size": pl.Int64,
            "multiplier": pl.Float64,
            "board_segment": pl.String,
            "lifecycle_state": pl.String,
            "ipo_date": pl.Date,
            "delisting_date": pl.Date,
            "as_of_date": pl.Date,
            "known_at": pl.Date,
            "settlement_cycle": pl.Int64,
            "fund_settlement_cycle": pl.Int64,
            "price_limit_pct": pl.Float64,
            "order_types_supported": pl.List(pl.String),
            "call_auction_sessions": pl.List(pl.String),
            "commission_rate": pl.Float64,
            "min_commission": pl.Float64,
            "stamp_duty_rate": pl.Float64,
            "transfer_fee_rate": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )
    rules_buffer = BytesIO()
    rules_frame.write_parquet(rules_buffer)
    rules_bytes = rules_buffer.getvalue()
    rules_schema = tuple(
        (name, str(dtype)) for name, dtype in rules_frame.schema.items()
    )
    return VerifiedInstrumentRulesArtifact(
        input_evidence=ContentAddressedResearchInput(
            input_id="instrument_rules",
            artifact_kind="instrument_rules",
            content_hash=hashlib.sha256(rules_bytes).hexdigest(),
            schema_hash=hashlib.sha256(orjson.dumps(rules_schema)).hexdigest(),
        ),
        artifact_bytes=rules_bytes,
    )


def _snapshot_inputs(
    instrument_rules: VerifiedInstrumentRulesArtifact,
    *,
    membership_hash: str = "9" * 64,
) -> tuple[ContentAddressedResearchInput, ...]:
    return (
        ContentAddressedResearchInput("calendar", "calendar", "3" * 64, "4" * 64),
        ContentAddressedResearchInput(
            "etf_daily",
            "bars",
            "1" * 64,
            "2" * 64,
        ),
        ContentAddressedResearchInput(
            "etf_momentum@1",
            "factor",
            "7" * 64,
            "a" * 64,
        ),
        instrument_rules.input_evidence,
        ContentAddressedResearchInput(
            "membership",
            "membership",
            membership_hash,
            "8" * 64,
        ),
    )


def _snapshot_manifest_bytes(
    inputs: tuple[ContentAddressedResearchInput, ...],
) -> bytes:
    return orjson.dumps(
        {
            "schema_version": 1,
            "snapshot_id": "certified-snapshot-task8",
            "dataset_id": "research-etf-rotation",
            "source_snapshot_ids": ["provider-snapshot-task8"],
            "known_at_policy": "sample_time",
            "builder_version": "research-builder-v1",
            "inputs": [
                dict(item.as_payload())
                for item in sorted(inputs, key=lambda item: item.input_id)
            ],
        },
        option=orjson.OPT_SORT_KEYS,
    )


def _exact_snapshot() -> ExactResearchSnapshot:
    raw = _snapshot_manifest_bytes(
        _snapshot_inputs(_instrument_rules_artifact()),
    )
    return ExactResearchSnapshot(
        "certified-snapshot-task8",
        hashlib.sha256(raw).hexdigest(),
    )


class _ExactInputsResolver:
    def __init__(self, *, complete: bool = True) -> None:
        self.calls: list[FrozenResearchInputRequest] = []
        self._complete = complete

    def resolve(
        self,
        request: FrozenResearchInputRequest,
    ) -> FrozenResearchExecutionInputs:
        self.calls.append(request)
        instrument_rules = _instrument_rules_artifact(request.source_snapshot_ids[0])
        all_inputs = _snapshot_inputs(
            instrument_rules,
            membership_hash=request.universe.membership_hash,
        )
        inputs = (
            all_inputs
            if self._complete
            else tuple(
                item
                for item in all_inputs
                if item.artifact_kind in {"membership", "instrument_rules"}
            )
        )
        return FrozenResearchExecutionInputs(
            snapshot_manifest=VerifiedResearchSnapshotManifest(
                exact_snapshot=request.snapshot,
                manifest_bytes=_snapshot_manifest_bytes(inputs),
            ),
            universe=request.universe,
            membership_projection_hash=request.membership_projection_hash,
            instrument_rules=instrument_rules,
        )


class _MissingFoldReader:
    def __init__(self, delegate: SQLiteExperimentReader) -> None:
        self._delegate = delegate

    def get_launch_spec(self, experiment_id: ExperimentId):
        return self._delegate.get_launch_spec(experiment_id)

    def list_status_events(self, experiment_id: ExperimentId):
        return self._delegate.list_status_events(experiment_id)

    def list_folds(self, experiment_id: ExperimentId):
        return self._delegate.list_folds(experiment_id)[1:]


def _resolver_with_distinct_runtime_lanes(
    reader: SQLiteExperimentReader,
    strategy_reader: _ExactStrategyReader,
    input_resolver: _ExactInputsResolver,
) -> tuple[
    DurableResearchExecutionResolver,
    _ExactRuntimeBuilder,
    _ExactRuntimeBuilder,
]:
    candidate = _ExactRuntimeBuilder()
    published_baseline = _ExactRuntimeBuilder()
    return (
        DurableResearchExecutionResolver(
            experiment_reader=reader,
            strategy_reader=strategy_reader,
            runtime_builders=_runtime_builders(candidate, published_baseline),
            input_resolver=input_resolver,
            environment=CodeEnvironmentLock("git:test", "7" * 64),
        ),
        candidate,
        published_baseline,
    )


def _assert_exact_baseline_identity_drift_is_rejected(
    *,
    reader: SQLiteExperimentReader,
    strategy_reader: _ExactStrategyReader,
    baseline_fold: FoldView,
) -> None:
    drifted_builders = (
        _ExactRuntimeBuilder(baseline_pipeline_execution_hash="0" * 64),
        _ExactRuntimeBuilder(baseline_strategy_id="wrong-baseline"),
        _ExactRuntimeBuilder(baseline_strategy_version=99),
    )
    for published_baseline in drifted_builders:
        with pytest.raises(AppProcessError) as exc_info:
            DurableResearchExecutionResolver(
                experiment_reader=reader,
                strategy_reader=strategy_reader,
                runtime_builders=_runtime_builders(
                    _ExactRuntimeBuilder(),
                    published_baseline,
                ),
                input_resolver=_ExactInputsResolver(),
                environment=CodeEnvironmentLock("git:test", "7" * 64),
            ).resolve(baseline_fold)
        assert exc_info.value.details["reason"] == "baseline_runtime_identity_drift"


def _assert_exact_baseline_required_datasets_drift_is_rejected(
    *,
    reader: SQLiteExperimentReader,
    strategy_reader: _ExactStrategyReader,
    baseline_fold: FoldView,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        DurableResearchExecutionResolver(
            experiment_reader=reader,
            strategy_reader=strategy_reader,
            runtime_builders=_runtime_builders(
                _ExactRuntimeBuilder(),
                _ExactRuntimeBuilder(required_datasets=("calendar", "etf_daily")),
            ),
            input_resolver=_ExactInputsResolver(),
            environment=CodeEnvironmentLock("git:test", "7" * 64),
        ).resolve(baseline_fold)
    assert exc_info.value.details["reason"] == (
        "baseline_runtime_validation_evidence_drift"
    )


def _assert_exact_baseline_runtime_is_frozen(
    *,
    reader: SQLiteExperimentReader,
    baseline_fold: FoldView,
    baseline: ResearchExecutionSemantics,
) -> None:
    assert baseline.is_baseline is True
    assert baseline.baseline_plan is not None
    assert baseline.baseline_plan.exact_strategy is not None
    assert baseline.strategy.exact_strategy.version == 2
    durable_launch = read_durable_launch(reader, baseline_fold)
    assert durable_launch.executor["baseline_runtime"] == {
        "base_spec_hash": "f" * 64,
        "resolved_spec_hash": "b" * 64,
        "parameter_hash": "c" * 64,
        "pipeline_execution_hash": f"{258:064x}",
        "compiled_factor_set_hash": compiled_expressions_execution_hash(None),
        "max_lookback_sessions": 0,
        "node_registry_manifest_hash": "e" * 64,
        "factor_registry_manifest_hash": "d" * 64,
        "factor_binding_hashes": [_exact_factor_binding().binding_hash],
    }


def test_durable_execution_resolver_uses_only_exact_strategy_and_snapshot_identity(
    tmp_path: Path,
) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=SQLiteExperimentWriter(database),
        certification_probe=_CertificationProbe(),
        executor_probe=_ExecutorProbe(),
        authority_probe=_AuthorityProbe(),
    )
    request = _planning_request()
    strategy_reader = _ExactStrategyReader()
    input_resolver = _ExactInputsResolver()

    try:
        report = process.preflight(request)
        assert report.plan_hash is not None
        process.launch(request, confirmed_plan_hash=report.plan_hash)
        folds = reader.list_folds(ExperimentId(_EXPERIMENT_ID))
        candidates = reader.list_candidates(ExperimentId(_EXPERIMENT_ID))
        binder_id = next(
            item.candidate_id for item in candidates if not item.is_baseline
        )
        baseline_id = next(item.candidate_id for item in candidates if item.is_baseline)
        binder_fold = next(
            item
            for item in folds
            if item.spec.key.candidate_id == binder_id
            and item.spec.fold_role is FoldRole.WALK_FORWARD
        )
        baseline_fold = next(
            item
            for item in folds
            if item.spec.key.candidate_id == baseline_id
            and item.spec.fold_role is FoldRole.EXPLORATION
        )
        resolver, candidate_runtime_builder, published_baseline_builder = (
            _resolver_with_distinct_runtime_lanes(
                reader,
                strategy_reader,
                input_resolver,
            )
        )

        binder = resolver.resolve(binder_fold)
        replay = resolver.resolve(binder_fold)
        baseline = resolver.resolve(baseline_fold)

        assert (
            binder.reproduction_fingerprint,
            binder.is_baseline,
            binder.baseline_plan,
            binder.strategy.exact_strategy.version,
        ) == (
            replay.reproduction_fingerprint,
            False,
            None,
            3,
        )
        assert binder.policy.lane is ResearchAssetLane.ETF
        assert (
            binder.backtest.engine_version,
            binder.backtest.rebalance_frequency,
            binder.backtest.participation_rate_ppm,
            binder.backtest.benchmark,
            len(binder.backtest.data_feed_manifest_hash),
        ) == ("0.1.0", "monthly", 50_000, None, 64)
        assert binder.snapshot.exact_snapshot == _exact_snapshot()
        assert binder.membership_hash == "9" * 64
        _assert_exact_baseline_runtime_is_frozen(
            reader=reader,
            baseline_fold=baseline_fold,
            baseline=baseline,
        )
        assert strategy_reader.calls == [
            ("seed_etf_rotation", 3),
            ("seed_etf_rotation", 3),
            ("seed_etf_rotation", 2),
        ]
        assert (
            candidate_runtime_builder.calls,
            published_baseline_builder.calls,
        ) == ([(3, "draft"), (3, "draft")], [(2, "published")])
        assert len(input_resolver.calls) == 3
        assert all(item.snapshot == _exact_snapshot() for item in input_resolver.calls)
        assert all(
            item.universe == ExactUniverseIdentity("csi_etf_broad", "9" * 64)
            for item in input_resolver.calls
        )

        with pytest.raises(AppProcessError) as missing_inputs:
            DurableResearchExecutionResolver(
                experiment_reader=reader,
                strategy_reader=strategy_reader,
                runtime_builders=_runtime_builders(
                    _ExactRuntimeBuilder(),
                    _ExactRuntimeBuilder(),
                ),
                input_resolver=_ExactInputsResolver(complete=False),
                environment=CodeEnvironmentLock("git:test", "7" * 64),
            ).resolve(binder_fold)
        assert missing_inputs.value.details["reason"] == (
            "snapshot_manifest_hash_mismatch"
        )

        with pytest.raises(AppProcessError) as lane_drift:
            DurableResearchExecutionResolver(
                experiment_reader=reader,
                strategy_reader=strategy_reader,
                runtime_builders=_runtime_builders(
                    _ExactRuntimeBuilder(lane="stock_selection"),
                    _ExactRuntimeBuilder(),
                ),
                input_resolver=_ExactInputsResolver(),
                environment=CodeEnvironmentLock("git:test", "7" * 64),
            ).resolve(binder_fold)
        assert lane_drift.value.details["reason"] == (
            "candidate_runtime_validation_evidence_drift"
        )

        with pytest.raises(AppProcessError) as compiled_factor_drift:
            DurableResearchExecutionResolver(
                experiment_reader=reader,
                strategy_reader=strategy_reader,
                runtime_builders=_runtime_builders(
                    _ExactRuntimeBuilder(
                        compiled_expressions=CompiledExpressions((), ()),
                    ),
                    _ExactRuntimeBuilder(),
                ),
                input_resolver=_ExactInputsResolver(),
                environment=CodeEnvironmentLock("git:test", "7" * 64),
            ).resolve(binder_fold)
        assert compiled_factor_drift.value.details["reason"] == (
            "candidate_runtime_identity_drift"
        )

        _assert_exact_baseline_identity_drift_is_rejected(
            reader=reader,
            strategy_reader=strategy_reader,
            baseline_fold=baseline_fold,
        )
        _assert_exact_baseline_required_datasets_drift_is_rejected(
            reader=reader,
            strategy_reader=strategy_reader,
            baseline_fold=baseline_fold,
        )

        with pytest.raises(AppProcessError) as missing_fold:
            DurableResearchExecutionResolver(
                experiment_reader=cast(
                    "SQLiteExperimentReader",
                    _MissingFoldReader(reader),
                ),
                strategy_reader=strategy_reader,
                runtime_builders=_runtime_builders(
                    _ExactRuntimeBuilder(),
                    _ExactRuntimeBuilder(),
                ),
                input_resolver=_ExactInputsResolver(),
                environment=CodeEnvironmentLock("git:test", "7" * 64),
            ).resolve(binder_fold)
        assert missing_fold.value.details["reason"] == "launch_spec_preflight_drift"
        assert "persisted_folds" in missing_fold.value.details["fields"]
    finally:
        database.close_all()
