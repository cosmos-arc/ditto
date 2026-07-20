"""Task 8 launch saga integration against the Task 7 research database."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ditto_analysis.experiments import (
    ExperimentId,
    ExperimentStatus,
    FoldRole,
    StatusSubjectType,
    canonical_payload,
)
from ditto_analysis.experiments.specs import ExperimentFailurePolicy
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ResourceCostModel,
)
from ditto_application.processes.experiments.planning_process import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    CandidateExecutorEvidence,
    ExperimentPlanningProcess,
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
)
from ditto_strategy.models import StrategySpecRecord

_NOW = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)
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
            manifest_hash="d" * 64,
        ),
        planning_decision_date=_NOW.date(),
    )


def _planning_request() -> ExperimentPlanningRequest:
    return ExperimentPlanningRequest(
        experiment_id=_EXPERIMENT_ID,
        research_cycle_id="cycle-task8-integration-1",
        research_cycle_hash="c" * 64,
        strategy_record=StrategySpecRecord(
            strategy_id="seed_etf_rotation",
            name="ETF rotation",
            spec_json={"strategy_id": "seed_etf_rotation"},
            version=3,
            status="draft",
        ),
        snapshot_identity=ExperimentSnapshotIdentity(
            snapshot_id="certified-snapshot-task8",
            manifest_hash="d" * 64,
        ),
        validation_request=_validation_request(),
        matrix_spec=CandidateMatrixSpec(
            baseline=BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={"strategy_id": "seed_etf_rotation", "version": 2},
            ),
        ),
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
    candidates = reader.list_candidates(experiment_id)
    folds = reader.list_folds(experiment_id)
    gates = _gates(reader)
    events = reader.list_status_events(experiment_id)

    assert receipt.status == ExperimentStatus.QUEUED.value
    assert projection is not None
    assert projection.record.status is ExperimentStatus.QUEUED
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
    return projection, candidates, folds, gates, events


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
