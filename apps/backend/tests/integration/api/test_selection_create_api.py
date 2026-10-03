"""Real HTTP selection create with isolated SQLite evidence and run stores."""

from dataclasses import asdict

import httpx
import orjson
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.processes.selection.assemble_facts import (
    AssembleSelectionFacts,
    AssembleSelectionFactsRequest,
)
from ditto_application.processes.selection.facade import SelectionWorkspaceFacade
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.historical_universe import HistoricalUniverseQuery
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.selection import router
from ditto_apps.api.routes.universe import router as universe_router
from ditto_apps.middleware import api_error_handler
from ditto_platform.foundation import SQLitePool
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.storage.sqlite.industry_rotation_store import (
    SQLiteIndustryRotationStore,
)
from ditto_strategy.storage.sqlite.selection_run_store import SQLiteSelectionRunStore
from fastapi import FastAPI
from packages.application.tests.integration.snapshot_readiness_support import (
    ready_selection,
)
from packages.application.tests.integration.test_snapshot_readiness import (
    selection_request,
)

_POLICY_BODY = {
    "universe_id": "universe.cn.all",
    "asset_kind": "stock",
    "as_of": "2026-09-18T09:00:00+00:00",
    "spec_id": "admission-test",
    "spec_version": "1",
    "top_k": 1,
    "min_average_turnover": 0,
    "min_listing_days": 1,
    "factor_weights": [{"name": "liquidity", "weight": 1.0}],
    "seed": 1,
}


@pytest.mark.asyncio
async def test_policy_only_create_replays_and_refuses_client_facts(tmp_path):
    with ready_selection(selection_request()) as (readiness, bound, history):
        pool = SQLitePool(tmp_path / "runs.sqlite")
        runs = SQLiteSelectionRunStore(pool)
        rotations = SQLiteIndustryRotationStore(pool)
        runs.init_schema()
        rotations.init_schema()
        facade = SelectionWorkspaceFacade(
            RunIndustryAndSecuritySelection(
                rotation_service=IndustryRotationService(),
                selection_pipeline=SelectionPipeline(),
                rotation_writer=rotations,
                run_writer=runs,
            ),
            readiness=readiness,
            historical_universe=history,
        )

        class _RecordingAssemble(AssembleSelectionFacts):
            def __init__(self) -> None:
                self.requests: list[AssembleSelectionFactsRequest] = []

            def assemble(self, request: AssembleSelectionFactsRequest):
                self.requests.append(request)
                return bound

        process = _RecordingAssemble()

        class TestProvider(Provider):
            scope = Scope.APP

            @provide
            def selection_facade(self) -> SelectionWorkspaceFacade:
                return facade

            @provide
            def assemble_process(self) -> AssembleSelectionFacts:
                return process

            @provide
            def historical_query(self) -> HistoricalUniverseQuery:
                return history

        container = make_async_container(TestProvider())
        app = FastAPI()
        setup_dishka(container=container, app=app)
        app.include_router(router, prefix="/api/v1")
        app.include_router(universe_router, prefix="/api/v1")
        app.add_exception_handler(APIError, api_error_handler)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await _assert_historical_scope(client, bound)
            first = await client.post("/api/v1/selections/runs", json=_POLICY_BODY)
            assert first.status_code == 201, first.text
            assert (
                first.json()["data"]["selection_run"]["candidates"][0]["instrument_id"]
                == 600000
            )
            second = await client.post("/api/v1/selections/runs", json=_POLICY_BODY)
            assert second.status_code == 201, second.text
            assert (
                first.json()["data"]["selection_run"]["run_id"]
                == second.json()["data"]["selection_run"]["run_id"]
            )
            assert len(runs.list_by_spec("admission-test")) == 1
            assert len(process.requests) == 2
            await _assert_client_facts_refused(client)
        await container.close()
        pool.close_all()


async def _assert_client_facts_refused(client):
    """Client-authored fact packages must not become a trusted write surface."""
    for forged in (
        {"instruments": [{"instrument_id": 600000, "is_st": True}]},
        {"selection_source_snapshot_ids": ["snapshot:forged"]},
        {"data_fields": [{"dataset_id": "stock_daily", "field": "amount"}]},
        {"declared_missing_inputs": []},
        {"universe_snapshot_id": "forged-universe"},
        {"average_turnover": 999999.0},
    ):
        response = await client.post(
            "/api/v1/selections/runs", json={**_POLICY_BODY, **forged}
        )
        assert response.status_code == 422, (forged, response.text)


async def _assert_historical_scope(client, bound):
    body = orjson.loads(orjson.dumps(asdict(bound)))
    historical = await client.post(
        f"/api/v1/universes/{bound.universe_sources.universe_id}/history",
        json={
            "sources": body["universe_sources"],
            "as_of": bound.as_of.date().isoformat(),
            "knowledge_cutoff": body["knowledge_cutoff"],
            "publication_cutoff": body["publication_cutoff"],
        },
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["data"]["snapshot_id"] == bound.universe_snapshot_id
    assert historical.json()["data"]["members"][0]["investable"] is True
