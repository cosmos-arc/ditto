"""Real SQLite research/governance HTTP fixture with deterministic evidence.

The app mounts production routers and application handlers. Its two fixture
endpoints expose a deterministic planning request and install a review packet
after the request has been launched over HTTP. It refuses non-testing use and
state outside ``/tmp``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

# These deterministic builders already back the focused backend integration
# suites. Reusing them keeps system evidence aligned with those PIT and hard-gate
# fixtures instead of inventing a second, weaker research truth.
from apps.backend.tests.integration.api import (
    test_r3_strategy_publish_api_integration as publish_support,
)
from apps.backend.tests.integration.api import (
    test_research_experiment_planning_api_integration as planning_support,
)
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_analysis.experiments import ExperimentId, encode_launch_spec
from ditto_analysis.experiments.persistence import LeaseFence
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.commands.experiments import (
    CancelExperimentHandler,
    LaunchExperimentHandler,
)
from ditto_application.commands.strategy_governance import (
    ApproveReviewHandler,
    PublishStrategyVersionHandler,
    ReactivateStrategyHandler,
    SubmitReviewHandler,
)
from ditto_application.processes.experiments._control_runtime import (
    CONTROL_COORDINATOR_LEASE_DURATION,
    CONTROL_COORDINATOR_OWNER_TOKEN,
    ControlOnlyFirstAttemptFactory,
    LoggingExperimentControlNotifier,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStore,
)
from ditto_application.processes.strategy.promotion import StrategyPromotionProcess
from ditto_application.queries.experiments import ExperimentQueryFacade
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_apps.api.app_metadata import BuildMetadata
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.research_experiment_routes import (
    router as experiment_router,
)
from ditto_apps.api.routes.strategy import router as strategy_router
from ditto_apps.api.routes.system import router as system_router
from ditto_apps.config.runtime import resolve_cors_origins
from ditto_apps.middleware import api_error_handler
from ditto_apps.openapi_contract import canonical_contract_sha256
from ditto_platform.foundation import (
    Environment,
    ObservabilitySettings,
    Settings,
    SQLitePool,
    SystemSettings,
)
from ditto_strategy.governance.service import GovernanceService
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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _data_root() -> Path:
    if os.environ.get("DITTO_ENVIRONMENT") != "testing":
        raise RuntimeError("research system fixture requires testing mode")
    raw = os.environ.get("DITTO_ACCEPTANCE_DATA_ROOT")
    if raw is None:
        raise RuntimeError("DITTO_ACCEPTANCE_DATA_ROOT is required")
    root = Path(raw).resolve()
    if not root.is_relative_to(Path("/tmp").resolve()):
        raise RuntimeError("research system fixture state must be inside /tmp")
    root.mkdir(parents=True, exist_ok=True)
    return root


_root = _data_root()
_document = planning_support._planning_document()
_experiment_id = str(_document["experiment_id"])
_strategy_document = _document["strategy"]
if not isinstance(_strategy_document, dict):
    raise RuntimeError("deterministic strategy identity is invalid")
_strategy_id = str(_strategy_document["strategy_id"])
_strategy_version = int(_strategy_document["version"])

_research_database = ResearchExperimentDatabase(_root / "research")
_research_database.initialize()
_research_reader = SQLiteExperimentReader(_research_database)
_research_writer = SQLiteExperimentWriter(_research_database)
_planning = ExperimentPlanningProcess(
    reader=_research_reader,
    writer=_research_writer,
    certification_probe=planning_support._CertificationProbe(),
    executor_probe=planning_support._ExecutorProbe(),
    authority_probe=planning_support._AuthorityProbe(),
)

_governance_pool = SQLitePool(str(_root / "strategy.sqlite"))
_spec_writer = SQLiteStrategySpecWriter(_governance_pool)
_spec_writer.init_schema()
_governance_store = SQLiteStrategyGovernanceStore(_governance_pool)
_governance_store.init_schema()
_governance = GovernanceService(_governance_store)
_catalog = StrategyCatalogService(
    reader=SQLiteStrategySpecReader(_governance_pool),
    writer=_spec_writer,
    active_pointer_reader=_governance_store,
)

_launch_handler = LaunchExperimentHandler(_planning)
_experiment_scheduler_store = ExperimentSchedulerStore(
    reader=_research_reader,
    writer=_research_writer,
)
_experiment_control = ExperimentExecutionCoordinator(
    store=_experiment_scheduler_store,
    first_attempt_factory=ControlOnlyFirstAttemptFactory(),
    owner_token=CONTROL_COORDINATOR_OWNER_TOKEN,
    lease_duration=CONTROL_COORDINATOR_LEASE_DURATION,
)
_cancel_handler = CancelExperimentHandler(
    process=_experiment_control,
    notifier=LoggingExperimentControlNotifier(),
)
_submit_handler = SubmitReviewHandler(_governance, _research_reader)
_approve_handler = ApproveReviewHandler(_governance)
_publish_handler = PublishStrategyVersionHandler(
    process=StrategyPromotionProcess(_governance),
    reader=_research_reader,
)
_reactivate_handler = ReactivateStrategyHandler(_governance)
_experiment_queries = ExperimentQueryFacade(reader=_research_reader)
_strategy_queries = StrategyQueryFacade(
    _catalog,
    version_state_reader=_governance_store,
    governance_version_reader=_governance_store,
    governance_event_reader=_governance_store,
    experiment_resolver=_experiment_queries,
)


class _FixtureProvider(Provider):
    scope = Scope.APP

    @provide
    def planning(self) -> ExperimentPlanningProcess:
        return _planning

    @provide
    def launch(self) -> LaunchExperimentHandler:
        return _launch_handler

    @provide
    def cancel(self) -> CancelExperimentHandler:
        return _cancel_handler

    @provide
    def experiments(self) -> ExperimentQueryFacade:
        return _experiment_queries

    @provide
    def strategies(self) -> StrategyQueryFacade:
        return _strategy_queries

    @provide
    def submit_review(self) -> SubmitReviewHandler:
        return _submit_handler

    @provide
    def approve_review(self) -> ApproveReviewHandler:
        return _approve_handler

    @provide
    def publish_version(self) -> PublishStrategyVersionHandler:
        return _publish_handler

    @provide
    def reactivate_version(self) -> ReactivateStrategyHandler:
        return _reactivate_handler


_container = make_async_container(_FixtureProvider())


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await _container.close()
    _research_database.close_all()
    _governance_pool.close_all()


app = FastAPI(title="Ditto governed research system fixture", lifespan=_lifespan)
app.state.build_metadata = BuildMetadata.from_environment(
    generated_contract_sha256=canonical_contract_sha256()
)
app.state.settings = Settings(
    system=SystemSettings(environment=Environment.TESTING),
    observability=ObservabilitySettings(
        log_level="WARNING",
        tracing_enabled=False,
        tracing_exporter="none",
        metrics_enabled=False,
        metrics_exporter="none",
    ),
)
setup_dishka(container=_container, app=app)
app.include_router(experiment_router, prefix="/api/v1")
app.include_router(strategy_router, prefix="/api/v1")
app.add_exception_handler(APIError, api_error_handler)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "environment": "testing",
        "data_root": str(_root),
        "experiment_id": _experiment_id,
    }


@app.get("/system-fixture/research-plan")
async def research_plan() -> dict[str, object]:
    """Expose only the exact request input; all outcomes come from real routes."""
    return {"document": _document}


@app.post("/system-fixture/prepare-review")
async def prepare_review() -> dict[str, object]:
    """Install deterministic evidence after the HTTP launch has committed."""
    launch = _research_reader.get_launch_spec(ExperimentId(_experiment_id))
    if launch is None:
        raise APIError(
            "experiment must be launched before review preparation",
            status_code=409,
            error_code="SYSTEM_FIXTURE_LAUNCH_REQUIRED",
        )
    candidate = next(item for item in launch.candidates if not item.is_baseline)
    packet = publish_support._deterministic_packet(
        experiment_id=launch.experiment_id,
        candidate_id=str(candidate.candidate_id),
        launch_spec_hash=encode_launch_spec(launch).content_hash,
    )
    if _research_reader.get_review_packet(str(packet.bundle_hash)) is None:
        _research_writer.publish_review_packet(
            packet,
            lease_fence=LeaseFence(
                experiment_id=launch.experiment_id,
                owner_token="system-http-acceptance",
                revision=0,
                lease_until_epoch_us=publish_support._NOW_US - 1,
            ),
            now_epoch_us=publish_support._NOW_US,
            created_at=publish_support._NOW,
        )

    if _governance_store.get_state(_strategy_id, 1) is None:
        active = publish_support._strategy_record(
            strategy_id=_strategy_id,
            version=1,
            parent_version=None,
            created_at="2026-07-30T00:00:00Z",
        )
        candidate_record = publish_support._strategy_record(
            strategy_id=_strategy_id,
            version=_strategy_version,
            parent_version=1,
            created_at="2026-07-30T00:00:10Z",
        )
        if str(launch.strategy_spec_hash) != candidate_record.spec_hash:
            raise RuntimeError("strategy and experiment evidence identity drifted")
        _governance.create_draft(
            strategy_id=_strategy_id,
            version=1,
            spec_record=active,
            created_at=active.created_at,
        )
        _governance.publish_and_activate(
            strategy_id=_strategy_id,
            version=1,
            actor="system-fixture-bootstrap",
            reason="initial published version for reactivation proof",
            decided_at="2026-07-30T00:00:01Z",
        )
        _governance.create_draft(
            strategy_id=_strategy_id,
            version=_strategy_version,
            spec_record=candidate_record,
            created_at=candidate_record.created_at,
        )
    pointer = _governance_store.get_active_pointer(_strategy_id)
    if pointer is None:
        raise RuntimeError("fixture active pointer is unavailable")
    return {
        "experiment_id": _experiment_id,
        "bundle_hash": str(packet.bundle_hash),
        "strategy_id": _strategy_id,
        "candidate_version": _strategy_version,
        "initial_active_version": pointer.active_version,
        "initial_pointer_revision": pointer.pointer_revision,
    }


app.include_router(system_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(resolve_cors_origins()),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Trace-ID"],
)
