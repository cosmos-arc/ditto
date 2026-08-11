"""HTTP integration contract for experiment preflight and collection launch."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from sqlite3 import Connection
from typing import cast

import httpx
import orjson
import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_analysis.errors import ExperimentPersistenceError
from ditto_analysis.experiments import (
    ExperimentId,
    ExperimentWriterProtocol,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.preflight_authority import (
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments.promotion_objective import (
    promotion_objective_payload,
)
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
from ditto_application.commands.experiments import LaunchExperimentHandler
from ditto_application.processes.experiments._launch_idempotency import (
    bind_prepared_launch_idempotency,
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
)
from ditto_application.processes.experiments.planning_contracts import (
    declare_trial_family,
)
from ditto_application.processes.experiments.planning_probes import (
    CandidateExecutorEvidence,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
)
from ditto_application.processes.experiments.planning_process import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    ExperimentPlanningProcess,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchSnapshotEvidence,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
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
    canonical_validation_protocol_payload,
    compile_validation_protocol,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.maturity import build_maturity_openapi_schema
from ditto_apps.api.research_mutations import launch_mutation_idempotency
from ditto_apps.api.routes import research_experiment_routes
from ditto_apps.api.routes.research_experiment_routes import router
from ditto_apps.main import _generate_stable_operation_id
from ditto_apps.middleware import api_error_handler
from ditto_apps.models.research import ExperimentLaunchRequest
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord
from fastapi import FastAPI

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_NOW = datetime(2026, 7, 30, tzinfo=UTC)
_EXPERIMENT_ID = "exp-planning-api-integration-1"
_STRATEGY_ID = "seed_stock_selection_rotation"
_SNAPSHOT_ID = "certified-snapshot-planning-api-1"
_SOURCE_SNAPSHOT_ID = "provider-snapshot-planning-api-1"
_SNAPSHOT_HASH = "d" * 64


def _next_month(month: CalendarMonth) -> CalendarMonth:
    if month.month == 12:
        return CalendarMonth(month.year + 1, 1)
    return CalendarMonth(month.year, month.month + 1)


def _validation_request() -> ValidationProtocolRequest:
    months: list[CalendarMonth] = []
    sessions: list[date] = []
    month_sessions: list[tuple[date, ...]] = []
    month = CalendarMonth(2016, 1)
    for _ in range(38):
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
    instrument_ids = ("STOCK-0001",)
    eligible_from = sessions[21]
    membership = (PitUniverseMembershipInterval(months[0], months[-1]),)
    cutoff = date(month.year, month.month, 1) - timedelta(days=1)
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
            for item in months[1:]
        ),
        isolation=IsolationSemantics(2, 5, 1),
        trading_calendar=TradingCalendarEvidence.create(
            calendar_id="sse-szse",
            version=1,
            source=TradingCalendarSourceIdentity(
                dataset_id="stock_daily",
                snapshot_id=_SOURCE_SNAPSHOT_ID,
                manifest_hash=_SNAPSHOT_HASH,
                certified_through=cutoff,
                authority_as_of=cutoff,
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
                membership_intervals=membership,
            ),
        ),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            universe_id="csi_stock_broad",
            dataset_id="stock_daily",
            snapshot_id=_SOURCE_SNAPSHOT_ID,
            manifest_hash=_SNAPSHOT_HASH,
        ),
        planning_decision_date=_NOW.date(),
    )


def _matrix_spec() -> CandidateMatrixSpec:
    return CandidateMatrixSpec(
        baseline=BaselineDescriptor(
            descriptor_type="stock-universe-equal-weight",
            payload={},
        ),
        candidate_limit=4,
    )


def _promotion_objective(matrix: CandidateMatrixSpec) -> PromotionObjective:
    family = declare_trial_family(
        experiment_id=_EXPERIMENT_ID,
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


def _plain_seed_spec() -> dict[str, object]:
    seed = SEED_STRATEGY_SPECS[_STRATEGY_ID]
    return cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(asdict(seed))),
    )


def _planning_document() -> dict[str, object]:
    validation = _validation_request()
    validation_plan = compile_validation_protocol(validation)
    assert validation_plan.reserved_holdout is not None
    holdout = validation_plan.reserved_holdout.test_window
    matrix = _matrix_spec()
    seed = SEED_STRATEGY_SPECS[_STRATEGY_ID]
    spec_json = _plain_seed_spec()
    strategy_record = StrategySpecRecord(
        strategy_id=_STRATEGY_ID,
        name=seed.name,
        spec_json=spec_json,
        version=2,
        created_at="2026-07-30T00:00:00Z",
        tags=seed.tags,
    )
    return {
        "experiment_id": _EXPERIMENT_ID,
        "research_cycle_id": "cycle-planning-api-integration-1",
        "research_cycle_hash": str(
            canonical_research_cycle_hash(
                strategy_family_id=_STRATEGY_ID,
                certified_data_cutoff=holdout.end,
                oos_window=holdout,
            )
        ),
        "strategy": {
            "strategy_id": _STRATEGY_ID,
            "version": 2,
            "spec_hash": canonical_spec_hash_for_record(strategy_record),
            "spec_json": spec_json,
        },
        "snapshot": {
            "snapshot_id": _SNAPSHOT_ID,
            "manifest_hash": _SNAPSHOT_HASH,
        },
        "validation": dict(canonical_validation_protocol_payload(validation)),
        "matrix": {
            "baseline": {
                "descriptor_type": matrix.baseline.descriptor_type,
                "payload": dict(matrix.baseline.payload),
                "schema_version": matrix.baseline.schema_version,
            },
            "axes": [],
            "candidate_limit": matrix.candidate_limit,
        },
        "promotion_objective": dict(
            promotion_objective_payload(_promotion_objective(matrix))
        ),
        "dataset_requirements": [
            {
                "dataset_id": "stock_daily",
                "expected_snapshot_ids": [_SOURCE_SNAPSHOT_ID],
                "requires_pit_universe": True,
                "certified_from": validation.required_input_start.isoformat(),
            },
        ],
        "cost_model": {
            "bytes_per_run": 100,
            "bytes_per_trading_session": 2,
        },
        "budget": {
            "candidate_limit": 4,
            "fold_run_limit": 1_000,
            "trading_session_limit": 1_000_000,
            "disk_byte_limit": 100_000_000,
        },
        "seed": 42,
        "worker_count": 2,
        "failure_policy": "fail_fast",
        "created_at": "2026-07-30T00:00:00Z",
    }


class _CertificationProbe:
    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        source_snapshot_ids = tuple(
            snapshot_id
            for requirement in request.requirements
            for snapshot_id in requirement.expected_snapshot_ids
        )
        return ResearchCertificationResult(
            ready=True,
            profile=R3_RESEARCH_CERTIFICATION_PROFILE,
            dataset_ids=tuple(item.dataset_id for item in request.requirements),
            report_ids=tuple(
                f"cert-report-{index}"
                for index, _item in enumerate(request.requirements, start=1)
            ),
            reason_codes=(),
            snapshot_evidence=ResearchSnapshotEvidence(
                snapshot_id=request.snapshot_identity.snapshot_id,
                dataset_id="research-planning-api",
                manifest_hash=request.snapshot_identity.manifest_hash,
                source_snapshot_ids=source_snapshot_ids,
                snapshot_start=request.required_from,
                snapshot_end=request.required_to,
                known_at_policy="sample_time",
                builder_version="planning-api-integration-v1",
            ),
        )


class _ExecutorProbe:
    def probe(
        self,
        request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        baseline = resolve_planning_baseline(
            request.baseline,
            default_baseline_registry(),
        )
        return ResearchExecutorProbeResult(
            available=True,
            code=None,
            reason=None,
            remediation=None,
            strategy_spec_hash=request.strategy_record.spec_hash,
            node_registry_manifest_hash="e" * 64,
            required_datasets=("stock_daily",),
            candidates=tuple(
                CandidateExecutorEvidence(
                    candidate_hash=candidate.candidate_hash,
                    resolved_spec_hash=f"{candidate.ordinal + 1:064x}",
                    parameter_hash=f"{candidate.ordinal + 129:064x}",
                    pipeline_execution_hash=f"{candidate.ordinal + 257:064x}",
                    compiled_factor_set_hash=f"{candidate.ordinal + 385:064x}",
                )
                for candidate in request.candidates
            ),
            runtime_validation_evidence=RuntimeValidationEvidence(
                lane="stock_selection",
                universe_id="csi_stock_broad",
                required_datasets=("stock_daily",),
                max_lookback_sessions=21,
                requires_pit_universe=True,
                forward_horizon_sessions=2,
                holding_period_sessions=5,
                execution_lag_sessions=1,
            ),
            baseline_ref=baseline.ref.identity,
            baseline_descriptor_hash=baseline.registration.descriptor.canonical_hash,
            baseline_registry_manifest_hash=baseline.registry_manifest_hash,
            baseline_exact_strategy_hash=None,
            factor_registry_manifest_hash="f" * 64,
            factor_binding_hashes=(),
            baseline_runtime=None,
        )


class _AuthorityProbe:
    def probe(
        self,
        request: ResearchValidationAuthorityRequest,
    ) -> ResearchValidationAuthorityResult:
        runtime = request.runtime_validation
        assert type(runtime) is RuntimeValidationEvidence
        evidence = ResearchValidationAuthorityEvidence.create(
            protocol=request.declared_protocol,
            snapshot_identity=request.snapshot_identity,
            runtime_evidence_hash=runtime.payload_hash,
            universe_membership_hash="9" * 64,
            requires_pit_universe=True,
            dataset_bindings=request.declared_requirements,
        )
        return ResearchValidationAuthorityResult(
            ready=True,
            code=None,
            reason=None,
            remediation=None,
            evidence=evidence,
        )


class _FailingCreationWriter:
    def create_experiment(self, *_args: object, **_kwargs: object) -> None:
        raise ExperimentPersistenceError(
            "injected experiment creation failure",
            details={"reason_code": "injected_creation_failure"},
        )


def _planning_test_app(
    planning: ExperimentPlanningProcess,
    launch: LaunchExperimentHandler,
) -> tuple[FastAPI, AsyncContainer]:
    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def planning_process(self) -> ExperimentPlanningProcess:
            return planning

        @provide
        def launch_handler(self) -> LaunchExperimentHandler:
            return launch

    container = make_async_container(TestProvider())
    test_app = FastAPI(generate_unique_id_function=_generate_stable_operation_id)
    setup_dishka(container=container, app=test_app)
    test_app.include_router(router, prefix="/api/v1")
    test_app.add_exception_handler(APIError, api_error_handler)
    test_app.openapi = lambda: build_maturity_openapi_schema(test_app)
    return test_app, container


async def _assert_planning_http_state(
    *,
    client: httpx.AsyncClient,
    document: dict[str, object],
    reader: SQLiteExperimentReader,
    connection: Connection,
) -> None:
    experiment_id = str(document["experiment_id"])
    writes_before_preflight = connection.total_changes
    preflight = await client.post(
        f"/api/v1/research/experiments/{experiment_id}/preflight",
        json=document,
    )
    assert preflight.status_code == 200, preflight.text
    assert connection.total_changes == writes_before_preflight
    assert reader.get_experiment_projection(ExperimentId(experiment_id)) is None
    plan_hash = preflight.json()["data"]["plan_hash"]
    assert isinstance(plan_hash, str)
    identity_drift = await client.post(
        "/api/v1/research/experiments/different/preflight",
        json=document,
    )
    stale = await client.post(
        "/api/v1/research/experiments",
        json={**document, "confirmed_plan_hash": "0" * 64},
        headers={"Idempotency-Key": "planning-stale-hash-001"},
    )
    blocked_document = deepcopy(document)
    blocked_budget = cast("dict[str, object]", blocked_document["budget"])
    blocked_budget["disk_byte_limit"] = 1
    blocked = await client.post(
        "/api/v1/research/experiments",
        json={**blocked_document, "confirmed_plan_hash": plan_hash},
        headers={"Idempotency-Key": "planning-budget-blocked-001"},
    )
    assert identity_drift.status_code == 422
    assert identity_drift.json()["error_code"] == "SPEC_INVALID"
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "PLAN_HASH_MISMATCH"
    assert blocked.status_code == 422
    assert blocked.json()["error_code"] == "BUDGET_EXCEEDED"
    assert connection.total_changes == writes_before_preflight
    assert reader.get_experiment_projection(ExperimentId(experiment_id)) is None
    launch_body = {**document, "confirmed_plan_hash": plan_hash}
    launch_headers = {"Idempotency-Key": "planning-launch-001"}
    first = await client.post(
        "/api/v1/research/experiments",
        json=launch_body,
        headers=launch_headers,
    )
    assert first.status_code == 200, first.text
    writes_after_first_launch = connection.total_changes
    assert writes_after_first_launch > writes_before_preflight
    first_projection = reader.get_experiment_projection(ExperimentId(experiment_id))
    assert first_projection is not None
    replay = await client.post(
        "/api/v1/research/experiments",
        json=launch_body,
        headers=launch_headers,
    )
    drifted_document = deepcopy(document)
    drifted_document["seed"] = 43
    drift = await client.post(
        "/api/v1/research/experiments",
        json={**drifted_document, "confirmed_plan_hash": plan_hash},
        headers={"Idempotency-Key": "planning-launch-drift-001"},
    )
    assert replay.status_code == 200, replay.text
    assert connection.total_changes == writes_after_first_launch
    assert first.json() == replay.json()
    assert drift.status_code == 409, drift.text
    assert drift.json()["error_code"] == "EXPERIMENT_ALREADY_EXISTS"
    assert connection.total_changes == writes_after_first_launch
    assert first.json()["data"]["experiment_id"] == experiment_id
    assert first.json()["data"]["status"] == "queued"
    assert first.json()["data"]["plan_hash"] == plan_hash
    assert (
        reader.get_experiment_projection(ExperimentId(experiment_id))
        == first_projection
    )


async def test_planning_routes_are_zero_write_for_preflight_and_replay_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove HTTP preflight is zero-write and exact launch replay is durable."""

    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(research_experiment_routes, "run_blocking", run_inline)
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    planning = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=_CertificationProbe(),
        executor_probe=_ExecutorProbe(),
        authority_probe=_AuthorityProbe(),
    )
    launch = LaunchExperimentHandler(planning)
    document = _planning_document()
    test_app, container = _planning_test_app(planning, launch)

    try:
        connection = database.get_connection()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            await _assert_planning_http_state(
                client=client,
                document=document,
                reader=reader,
                connection=connection,
            )

        schema = test_app.openapi()
        assert (
            schema["paths"]["/api/v1/research/experiments/{experiment_id}/preflight"][
                "post"
            ]["operationId"]
            == "research_preflight_experiment"
        )
        assert (
            schema["paths"]["/api/v1/research/experiments"]["post"]["operationId"]
            == "research_launch_experiment"
        )
    finally:
        await container.close()
        database.close_all()


async def test_partial_draft_identity_drift_is_409_and_zero_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject caller drift against one durable DRAFT root without mutation."""

    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(research_experiment_routes, "run_blocking", run_inline)
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    planning = ExperimentPlanningProcess(
        reader=reader,
        writer=writer,
        certification_probe=_CertificationProbe(),
        executor_probe=_ExecutorProbe(),
        authority_probe=_AuthorityProbe(),
    )
    launch = LaunchExperimentHandler(planning)
    document = _planning_document()
    request = build_experiment_planning_request(document)
    prepared = planning._prepare(request)
    assert prepared.launch is not None
    assert prepared.report.plan_hash is not None
    partial_key = "planning-partial-exact-001"
    transport_request = ExperimentLaunchRequest.model_validate(
        {**document, "confirmed_plan_hash": prepared.report.plan_hash}
    )
    bound_launch = bind_prepared_launch_idempotency(
        prepared.launch,
        launch_mutation_idempotency(transport_request, partial_key),
    )
    writer.create_experiment(
        bound_launch.cycle,
        bound_launch.spec,
        bound_launch.initial_record,
        creation_detail=bound_launch.creation_detail,
    )
    connection = database.get_connection()
    writes_after_partial_draft = connection.total_changes
    drifted_document = deepcopy(document)
    drifted_budget = cast("dict[str, object]", drifted_document["budget"])
    drifted_budget["disk_byte_limit"] = 1
    test_app, container = _planning_test_app(planning, launch)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=test_app,
                raise_app_exceptions=False,
            ),
            base_url="http://testserver",
        ) as client:
            drift = await client.post(
                "/api/v1/research/experiments",
                json={
                    **drifted_document,
                    "confirmed_plan_hash": prepared.report.plan_hash,
                },
                headers={"Idempotency-Key": "planning-partial-drift-001"},
            )

            assert drift.status_code == 409, drift.text
            assert drift.json()["error_code"] == "EXPERIMENT_ALREADY_EXISTS"
            assert connection.total_changes == writes_after_partial_draft

            exact = await client.post(
                "/api/v1/research/experiments",
                json={
                    **document,
                    "confirmed_plan_hash": prepared.report.plan_hash,
                },
                headers={"Idempotency-Key": partial_key},
            )
            assert exact.status_code == 200, exact.text
            assert exact.json()["data"]["status"] == "queued"
            assert connection.total_changes > writes_after_partial_draft
    finally:
        await container.close()
        database.close_all()


async def test_persistence_failure_is_stable_typed_500(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real command path and preserve its typed persistence code."""

    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(research_experiment_routes, "run_blocking", run_inline)
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteExperimentReader(database)
    planning = ExperimentPlanningProcess(
        reader=reader,
        writer=cast("ExperimentWriterProtocol", _FailingCreationWriter()),
        certification_probe=_CertificationProbe(),
        executor_probe=_ExecutorProbe(),
        authority_probe=_AuthorityProbe(),
    )
    launch = LaunchExperimentHandler(planning)
    document = _planning_document()
    test_app, container = _planning_test_app(planning, launch)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=test_app,
                raise_app_exceptions=False,
            ),
            base_url="http://testserver",
        ) as client:
            experiment_id = str(document["experiment_id"])
            preflight = await client.post(
                f"/api/v1/research/experiments/{experiment_id}/preflight",
                json=document,
            )
            assert preflight.status_code == 200, preflight.text
            plan_hash = preflight.json()["data"]["plan_hash"]
            assert isinstance(plan_hash, str)

            failed = await client.post(
                "/api/v1/research/experiments",
                json={**document, "confirmed_plan_hash": plan_hash},
                headers={"Idempotency-Key": "planning-persistence-failure-001"},
            )

            assert failed.status_code == 500
            assert failed.json()["error_code"] == "EXPERIMENT_PERSISTENCE_FAILED"
            assert reader.get_experiment_projection(ExperimentId(experiment_id)) is None
            assert reader.list_status_events(ExperimentId(experiment_id)) == ()
    finally:
        await container.close()
        database.close_all()
