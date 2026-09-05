"""HTTP integration contracts for durable R3 mutation idempotency."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import httpx
import pytest
from apps.backend.tests.integration.api import (
    test_research_experiment_planning_api_integration as planning_support,
)
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_analysis.experiments import ExperimentId
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.commands.experiments import (
    ExperimentControlNotifier,
    ExperimentControlProcess,
    ExperimentControlReceipt,
    LaunchExperimentHandler,
    PauseExperimentHandler,
)
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.commands.strategy_governance import (
    ApproveReviewHandler,
    DeprecateStrategyHandler,
    ReactivateStrategyHandler,
    RejectReviewHandler,
    ReviewPacketReader,
    SubmitReviewHandler,
    reactivate_confirmation_phrase,
)
from ditto_application.commands.strategy_governance_clock import utc_now_iso
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes import research_experiment_routes
from ditto_apps.api.routes import strategy as strategy_routes
from ditto_apps.api.routes.research_experiment_routes import (
    router as research_experiment_router,
)
from ditto_apps.api.routes.strategy import router
from ditto_apps.middleware import (
    api_error_handler,
    general_exception_handler,
    validation_exception_handler,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
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
from fastapi.exceptions import RequestValidationError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SEED = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
_CREATE_BODY = {
    "strategy_id": "r3-idempotency-strategy",
    "name": _SEED.name,
    "spec_json": asdict(_SEED),
    "tags": list(_SEED.tags),
}
_UPDATE_BODY = {
    "name": f"{_SEED.name} v2",
    "spec_json": asdict(_SEED),
    "tags": [*_SEED.tags, "updated"],
    "version": 1,
}
_HEADERS = {"Idempotency-Key": "strategy.create-001"}


@pytest.fixture(autouse=True)
def _inline_blocking_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        strategy_routes,
        "run_blocking",
        run_inline,
    )
    monkeypatch.setattr(
        "ditto_application.commands.strategy_governance.load_verified_promotion_target",
        lambda **_kwargs: SimpleNamespace(
            packet=SimpleNamespace(gate_evaluations=()),
        ),
    )
    monkeypatch.setattr(
        "ditto_application.commands.strategy_governance.hard_gate_contract_blocks_promotion",
        lambda _evaluations: False,
    )


@dataclass(slots=True)
class _Harness:
    client: httpx.AsyncClient
    container: AsyncContainer
    pool: SQLitePool
    governance: GovernanceService
    store: SQLiteStrategyGovernanceStore
    app: FastAPI

    async def close(self) -> None:
        await self.client.aclose()
        await self.container.close()
        self.pool.close_all()


def _build_harness(database_path: Path) -> _Harness:
    pool = SQLitePool(str(database_path))
    spec_writer = SQLiteStrategySpecWriter(pool)
    spec_writer.init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    governance = GovernanceService(store)
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=spec_writer,
        active_pointer_reader=store,
    )
    create = CreateStrategyHandler(governance)
    update = UpdateStrategyHandler(catalog, governance)
    submit = SubmitReviewHandler(governance, MagicMock(spec=ReviewPacketReader))
    approve = ApproveReviewHandler(governance)
    reject = RejectReviewHandler(governance)
    deprecate = DeprecateStrategyHandler(governance)
    reactivate = ReactivateStrategyHandler(governance)

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def create_handler(self) -> CreateStrategyHandler:
            return create

        @provide
        def update_handler(self) -> UpdateStrategyHandler:
            return update

        @provide
        def submit_handler(self) -> SubmitReviewHandler:
            return submit

        @provide
        def approve_handler(self) -> ApproveReviewHandler:
            return approve

        @provide
        def reject_handler(self) -> RejectReviewHandler:
            return reject

        @provide
        def deprecate_handler(self) -> DeprecateStrategyHandler:
            return deprecate

        @provide
        def reactivate_handler(self) -> ReactivateStrategyHandler:
            return reactivate

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    return _Harness(
        client=httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ),
        container=container,
        pool=pool,
        governance=governance,
        store=store,
        app=app,
    )


def _decision_count(harness: _Harness, strategy_id: str) -> int:
    return int(
        harness.pool.get_connection()
        .execute(
            "SELECT count(*) FROM strategy_decision_event WHERE strategy_id=?",
            (strategy_id,),
        )
        .fetchone()[0]
    )


def _all_governance_text(harness: _Harness) -> str:
    connection = harness.pool.get_connection()
    decisions = connection.execute(
        "SELECT event_id, reason FROM strategy_decision_event ORDER BY rowid"
    ).fetchall()
    activations = connection.execute(
        "SELECT event_id, reason FROM strategy_activation_event ORDER BY rowid"
    ).fetchall()
    return repr(tuple(tuple(row) for row in (*decisions, *activations)))


def _assert_required_idempotency_surface(
    schema: dict[str, object],
    mutations: tuple[tuple[str, str, str], ...],
) -> None:
    paths = schema["paths"]
    assert isinstance(paths, dict)
    for path, method, operation_id in mutations:
        operation = paths[path][method]
        headers = [
            item
            for item in operation["parameters"]
            if item["in"] == "header" and item["name"] == "Idempotency-Key"
        ]
        assert len(headers) == 1
        assert headers[0]["required"] is True
        assert headers[0]["schema"]["type"] == "string"
        assert operation["operationId"] == operation_id


def _assert_launch_event_receipt(
    reader: SQLiteExperimentReader,
    *,
    experiment_id: str,
    raw_key: str,
) -> int:
    events = reader.list_status_events(ExperimentId(experiment_id))
    enqueue = next(
        item
        for item in events
        if item.subject_revision == 1 and item.reason_code == "preflight_passed"
    )
    envelope = enqueue.detail["mutation_idempotency"]
    assert isinstance(envelope, dict)
    assert envelope["operation_id"] == "research_launch_experiment"
    assert raw_key not in repr(enqueue.detail)
    return len(events)


def _planning_runtime(
    database: ResearchExperimentDatabase,
) -> tuple[SQLiteExperimentReader, ExperimentPlanningProcess]:
    reader = SQLiteExperimentReader(database)
    process = ExperimentPlanningProcess(
        reader=reader,
        writer=SQLiteExperimentWriter(database),
        certification_probe=planning_support._CertificationProbe(),
        executor_probe=planning_support._ExecutorProbe(),
        authority_probe=planning_support._AuthorityProbe(),
    )
    return reader, process


async def test_create_replays_after_container_restart_and_rejects_key_reuse(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "strategy-idempotency.sqlite"
    first_harness = _build_harness(database_path)
    try:
        first = await first_harness.client.post(
            "/api/v1/strategies",
            json=_CREATE_BODY,
            headers=_HEADERS,
        )
        assert first.status_code == 200, first.text
        assert _decision_count(first_harness, str(_CREATE_BODY["strategy_id"])) == 1
        assert "strategy.create-001" not in _all_governance_text(first_harness)
    finally:
        await first_harness.close()

    restarted = _build_harness(database_path)
    try:
        count_before = _decision_count(restarted, str(_CREATE_BODY["strategy_id"]))
        replay = await restarted.client.post(
            "/api/v1/strategies",
            json=_CREATE_BODY,
            headers=_HEADERS,
        )
        assert replay.status_code == first.status_code, replay.text
        assert replay.json() == first.json()
        assert (
            _decision_count(restarted, str(_CREATE_BODY["strategy_id"])) == count_before
        )

        changed = await restarted.client.post(
            "/api/v1/strategies",
            json={**_CREATE_BODY, "name": "drifted"},
            headers=_HEADERS,
        )
        assert changed.status_code == 409
        assert changed.json()["error_code"] == "IDEMPOTENCY_KEY_REUSED"
        assert (
            _decision_count(restarted, str(_CREATE_BODY["strategy_id"])) == count_before
        )
    finally:
        await restarted.close()


async def test_create_replay_fails_closed_on_timestamp_or_payload_drift(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path / "strategy-corrupt-receipt.sqlite")
    strategy_id = str(_CREATE_BODY["strategy_id"])
    try:
        first = await harness.client.post(
            "/api/v1/strategies",
            json=_CREATE_BODY,
            headers=_HEADERS,
        )
        assert first.status_code == 200, first.text
        connection = harness.pool.get_connection()
        connection.execute(
            "UPDATE strategy_decision_event SET decided_at=? WHERE strategy_id=?",
            ("2026-07-31T23:59:59Z", strategy_id),
        )
        connection.commit()

        replay = await harness.client.post(
            "/api/v1/strategies",
            json=_CREATE_BODY,
            headers=_HEADERS,
        )

        assert replay.status_code == 500
        assert replay.json()["error_code"] == "IDEMPOTENCY_RECEIPT_INVALID"
        assert _decision_count(harness, strategy_id) == 1
    finally:
        await harness.close()


async def test_update_and_deprecate_replay_without_second_durable_event(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path / "strategy-update-idempotency.sqlite")
    strategy_id = str(_CREATE_BODY["strategy_id"])
    try:
        created = await harness.client.post(
            "/api/v1/strategies",
            json=_CREATE_BODY,
            headers=_HEADERS,
        )
        assert created.status_code == 200, created.text
        harness.governance.publish_and_activate(
            strategy_id=strategy_id,
            version=1,
            actor="fixture",
            reason="publish fixture version",
            decided_at=utc_now_iso(),
        )

        update_headers = {"Idempotency-Key": "strategy.update-001"}
        first_update = await harness.client.put(
            f"/api/v1/strategies/{strategy_id}",
            json=_UPDATE_BODY,
            headers=update_headers,
        )
        count_after_update = _decision_count(harness, strategy_id)
        replay_update = await harness.client.put(
            f"/api/v1/strategies/{strategy_id}",
            json=_UPDATE_BODY,
            headers=update_headers,
        )
        assert first_update.status_code == replay_update.status_code == 200
        assert first_update.json() == replay_update.json()
        assert _decision_count(harness, strategy_id) == count_after_update

        deprecate_headers = {"Idempotency-Key": "strategy.deprecate-001"}
        body = {"actor": "reviewer", "reason": "retire v1"}
        first_deprecate = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/deprecate",
            json=body,
            headers=deprecate_headers,
        )
        count_after_deprecate = _decision_count(harness, strategy_id)
        replay_deprecate = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/deprecate",
            json=body,
            headers=deprecate_headers,
        )
        assert first_deprecate.status_code == replay_deprecate.status_code == 200
        assert first_deprecate.json() == replay_deprecate.json()
        assert _decision_count(harness, strategy_id) == count_after_deprecate
    finally:
        await harness.close()


async def test_governance_replay_returns_original_state_after_later_transition(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path / "strategy-state-receipt.sqlite")
    strategy_id = str(_CREATE_BODY["strategy_id"])
    try:
        assert (
            await harness.client.post(
                "/api/v1/strategies",
                json=_CREATE_BODY,
                headers=_HEADERS,
            )
        ).status_code == 200
        submit_headers = {"Idempotency-Key": "strategy.submit-001"}
        submit_body = {
            "bundle_hash": "a" * 64,
            "actor": "reviewer",
            "reason": "ready for review",
        }
        submitted = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/submit-review",
            json=submit_body,
            headers=submit_headers,
        )
        assert submitted.status_code == 200, submitted.text
        approved = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/approve",
            json={"actor": "approver", "reason": "approved"},
            headers={"Idempotency-Key": "strategy.approve-001"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["review_outcome"] == "approved"

        count_before_replay = _decision_count(harness, strategy_id)
        replay = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/submit-review",
            json=submit_body,
            headers=submit_headers,
        )
        assert replay.status_code == submitted.status_code
        assert replay.json() == submitted.json()
        assert replay.json()["data"]["review_outcome"] == "pending"
        assert _decision_count(harness, strategy_id) == count_before_replay
    finally:
        await harness.close()


async def test_reactivate_replay_returns_original_pointer_after_later_activation(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path / "strategy-pointer-receipt.sqlite")
    strategy_id = str(_CREATE_BODY["strategy_id"])
    try:
        assert (
            await harness.client.post(
                "/api/v1/strategies",
                json=_CREATE_BODY,
                headers=_HEADERS,
            )
        ).status_code == 200
        assert (
            await harness.client.put(
                f"/api/v1/strategies/{strategy_id}",
                json=_UPDATE_BODY,
                headers={"Idempotency-Key": "strategy.update-pointer-001"},
            )
        ).status_code == 200
        harness.governance.publish_and_activate(
            strategy_id=strategy_id,
            version=1,
            actor="fixture",
            reason="activate v1",
            decided_at=utc_now_iso(),
        )
        pointer = harness.governance.publish_and_activate(
            strategy_id=strategy_id,
            version=2,
            actor="fixture",
            reason="activate v2",
            decided_at=utc_now_iso(),
        )

        first_body = {
            "actor": "operator",
            "reason": "rollback to v1",
            "impact_summary": "restore the prior production version",
            "expected_pointer_revision": pointer.pointer_revision,
            "confirmation": reactivate_confirmation_phrase(
                strategy_id,
                1,
                pointer.pointer_revision,
            ),
        }
        first_headers = {"Idempotency-Key": "strategy.reactivate-v1-001"}
        first = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/reactivate",
            json=first_body,
            headers=first_headers,
        )
        assert first.status_code == 200, first.text
        first_pointer_revision = first.json()["data"]["pointer_revision"]

        second_body = {
            "actor": "operator",
            "reason": "return to v2",
            "impact_summary": "restore the latest approved version",
            "expected_pointer_revision": first_pointer_revision,
            "confirmation": reactivate_confirmation_phrase(
                strategy_id,
                2,
                first_pointer_revision,
            ),
        }
        second = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/2/reactivate",
            json=second_body,
            headers={"Idempotency-Key": "strategy.reactivate-v2-001"},
        )
        assert second.status_code == 200, second.text
        assert second.json()["data"]["pointer_revision"] > first_pointer_revision

        activation_count = int(
            harness.pool.get_connection()
            .execute(
                "SELECT count(*) FROM strategy_activation_event WHERE strategy_id=?",
                (strategy_id,),
            )
            .fetchone()[0]
        )
        replay = await harness.client.post(
            f"/api/v1/strategies/{strategy_id}/versions/1/reactivate",
            json=first_body,
            headers=first_headers,
        )
        assert replay.status_code == first.status_code
        assert replay.json() == first.json()
        assert (
            int(
                harness.pool.get_connection()
                .execute(
                    "SELECT count(*) FROM strategy_activation_event "
                    "WHERE strategy_id=?",
                    (strategy_id,),
                )
                .fetchone()[0]
            )
            == activation_count
        )
    finally:
        await harness.close()


async def test_launch_receipt_replays_after_database_and_container_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.research_experiment_routes.run_blocking",
        run_inline,
    )
    database_root = tmp_path / "experiment-idempotency"
    database = ResearchExperimentDatabase(database_root)
    database.initialize()
    reader, planning = _planning_runtime(database)
    document = planning_support._planning_document()
    app, container = planning_support._planning_test_app(
        planning,
        LaunchExperimentHandler(planning),
    )
    key = "experiment.launch-001"
    experiment_id = str(document["experiment_id"])
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            preflight = await client.post(
                f"/api/v1/research/experiments/{experiment_id}/preflight",
                json=document,
            )
            assert preflight.status_code == 200, preflight.text
            launch_body = {
                **document,
                "confirmed_plan_hash": preflight.json()["data"]["plan_hash"],
            }
            first = await client.post(
                "/api/v1/research/experiments",
                json=launch_body,
                headers={"Idempotency-Key": key},
            )
            assert first.status_code == 200, first.text
            event_count = _assert_launch_event_receipt(
                reader,
                experiment_id=experiment_id,
                raw_key=key,
            )
    finally:
        await container.close()
        database.close_all()

    restarted_database = ResearchExperimentDatabase(database_root)
    restarted_database.initialize()
    restarted_reader, restarted_planning = _planning_runtime(restarted_database)
    restarted_app, restarted_container = planning_support._planning_test_app(
        restarted_planning,
        LaunchExperimentHandler(restarted_planning),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=restarted_app,
                raise_app_exceptions=False,
            ),
            base_url="http://testserver",
        ) as client:
            replay = await client.post(
                "/api/v1/research/experiments",
                json=launch_body,
                headers={"Idempotency-Key": key},
            )
            assert replay.status_code == first.status_code
            assert replay.json() == first.json()
            legacy_receipt = restarted_planning.launch(
                build_experiment_planning_request(document),
                confirmed_plan_hash=str(launch_body["confirmed_plan_hash"]),
            )
            assert legacy_receipt.experiment_id == first.json()["data"]["experiment_id"]
            assert legacy_receipt.queue_ordinal == first.json()["data"]["queue_ordinal"]
            assert legacy_receipt.plan_hash == first.json()["data"]["plan_hash"]
            assert (
                len(restarted_reader.list_status_events(ExperimentId(experiment_id)))
                == event_count
            )

            drifted = {
                **launch_body,
                "seed": int(launch_body["seed"]) + 1,
            }
            conflict = await client.post(
                "/api/v1/research/experiments",
                json=drifted,
                headers={"Idempotency-Key": key},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error_code"] == "IDEMPOTENCY_KEY_REUSED"
            assert (
                len(restarted_reader.list_status_events(ExperimentId(experiment_id)))
                == event_count
            )

            schema = restarted_app.openapi()
            mutation_paths = (
                (
                    "/api/v1/research/experiments",
                    "post",
                    "research_launch_experiment",
                ),
                (
                    "/api/v1/research/experiments/{experiment_id}/pause",
                    "post",
                    "research_pause_experiment",
                ),
                (
                    "/api/v1/research/experiments/{experiment_id}/cancel",
                    "post",
                    "research_cancel_experiment",
                ),
                (
                    "/api/v1/research/experiments/{experiment_id}/resume",
                    "post",
                    "research_resume_experiment",
                ),
                (
                    "/api/v1/research/experiments/{experiment_id}/retry-fold",
                    "post",
                    "research_retry_fold_experiment",
                ),
            )
            _assert_required_idempotency_surface(schema, mutation_paths)
    finally:
        await restarted_container.close()
        restarted_database.close_all()


async def test_control_notification_failure_still_returns_exact_http_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(research_experiment_routes, "run_blocking", run_inline)

    class ReplayProcess:
        def __init__(self) -> None:
            self.calls = 0
            self.durable_events = 0
            self.identity = None
            self.receipt: ExperimentControlReceipt | None = None

        def pause(self, **values: object) -> ExperimentControlReceipt:
            self.calls += 1
            if self.receipt is None:
                self.durable_events += 1
                self.identity = values["idempotency"]
                self.receipt = ExperimentControlReceipt(
                    experiment_id=str(values["experiment_id"]),
                    status="pause_requested",
                    desired_state="pause",
                    revision=8,
                    occurred_at=cast("datetime", values["occurred_at"]),
                    live_run_ids=("run-1",),
                )
                return self.receipt
            assert values["idempotency"] == self.identity
            return replace(self.receipt, replayed=True)

    class FailingNotifier:
        def __init__(self) -> None:
            self.calls = 0

        def notify_run_stop(self, **_values: object) -> None:
            self.calls += 1
            raise RuntimeError("transport unavailable")

        def notify_scheduler(self, **_values: object) -> None:
            raise AssertionError("pause must not wake the scheduler")

    process = ReplayProcess()
    notifier = FailingNotifier()
    handler = PauseExperimentHandler(
        process=cast("ExperimentControlProcess", process),
        notifier=cast("ExperimentControlNotifier", notifier),
    )

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def pause_handler(self) -> PauseExperimentHandler:
            return handler

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container=container, app=app)
    app.include_router(research_experiment_router, prefix="/api/v1")
    app.add_exception_handler(APIError, api_error_handler)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            first = await client.post(
                "/api/v1/research/experiments/experiment-1/pause",
                json={"expected_revision": 7},
                headers={"Idempotency-Key": "pause.notification-failure-001"},
            )
            replay = await client.post(
                "/api/v1/research/experiments/experiment-1/pause",
                json={"expected_revision": 7},
                headers={"Idempotency-Key": "pause.notification-failure-001"},
            )
    finally:
        await container.close()

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert process.calls == 2
    assert process.durable_events == 1
    assert notifier.calls == 1


async def test_required_header_validation_and_openapi_surface(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path / "strategy-header-validation.sqlite")
    try:
        missing = await harness.client.post(
            "/api/v1/strategies",
            json={**_CREATE_BODY, "strategy_id": "missing-key"},
        )
        blank = await harness.client.post(
            "/api/v1/strategies",
            json={**_CREATE_BODY, "strategy_id": "blank-key"},
            headers={"Idempotency-Key": " "},
        )
        oversized = await harness.client.post(
            "/api/v1/strategies",
            json={**_CREATE_BODY, "strategy_id": "oversized-key"},
            headers={"Idempotency-Key": "x" * 129},
        )
        assert missing.status_code == blank.status_code == oversized.status_code == 422

        schema = harness.app.openapi()
        mutation_paths = (
            (
                "/api/v1/strategies",
                "post",
                "strategies_create_strategy",
            ),
            (
                "/api/v1/strategies/{strategy_id}",
                "put",
                "strategies_update_strategy",
            ),
            (
                "/api/v1/strategies/{strategy_id}/versions/{version}/submit-review",
                "post",
                "strategies_submit_strategy_review",
            ),
            (
                "/api/v1/strategies/{strategy_id}/versions/{version}/approve",
                "post",
                "strategies_approve_strategy_review",
            ),
            (
                "/api/v1/strategies/{strategy_id}/versions/{version}/reject",
                "post",
                "strategies_reject_strategy_review",
            ),
            (
                "/api/v1/strategies/{strategy_id}/versions/{version}/deprecate",
                "post",
                "strategies_deprecate_strategy_version",
            ),
            (
                "/api/v1/strategies/{strategy_id}/versions/{version}/reactivate",
                "post",
                "strategies_reactivate_strategy_version",
            ),
            (
                "/api/v1/strategies/{strategy_id}/versions/{version}/publish",
                "post",
                "strategies_publish_strategy_version",
            ),
        )
        _assert_required_idempotency_surface(schema, mutation_paths)
    finally:
        await harness.close()
