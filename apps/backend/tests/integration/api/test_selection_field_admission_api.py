"""Real HTTP selection admission with isolated SQLite evidence and run stores."""

from copy import deepcopy
from dataclasses import asdict

import httpx
import orjson
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
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
from packages.application.tests.integration.field_admission_support import (
    certified_selection,
)
from packages.application.tests.integration.test_field_admission import (
    selection_request,
)


@pytest.mark.asyncio
async def test_http_admission_and_create_share_the_gate_and_retry_identity(tmp_path):
    with certified_selection(selection_request()) as (query, request, history):
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
            admission=query,
            historical_universe=history,
        )

        class TestProvider(Provider):
            scope = Scope.APP

            @provide
            def selection_facade(self) -> SelectionWorkspaceFacade:
                return facade

            @provide
            def historical_query(self) -> HistoricalUniverseQuery:
                return history

        container = make_async_container(TestProvider())
        app = FastAPI()
        setup_dishka(container=container, app=app)
        app.include_router(router, prefix="/api/v1")
        app.include_router(universe_router, prefix="/api/v1")
        app.add_exception_handler(APIError, api_error_handler)
        body = orjson.loads(orjson.dumps(asdict(request)))
        body["selection_spec"]["asset_kind"] = "stock"
        for field in body["data_fields"]:
            field.pop("consumer_input_hash", None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await _assert_historical_scope(client, request, body)
            preview = await client.post("/api/v1/selections/admission", json=body)
            assert preview.status_code == 200, preview.text
            assert preview.json()["data"]["allowed"] is True
            assert runs.list_by_spec("admission-test") == []
            first = await client.post("/api/v1/selections/runs", json=body)
            assert first.status_code == 201, first.text
            assert (
                first.json()["data"]["selection_run"]["candidates"][0]["instrument_id"]
                == 600000
            )
            second = await client.post("/api/v1/selections/runs", json=body)
            assert second.status_code == 201, second.text
            assert (
                first.json()["data"]["selection_run"]["run_id"]
                == second.json()["data"]["selection_run"]["run_id"]
            )
            assert len(runs.list_by_spec("admission-test")) == 1
            selected = await client.post(
                "/api/v1/selections/admission?instrument_id=600000", json=body
            )
            assert selected.status_code == 200, selected.text
            assert selected.json()["data"]["allowed"] is True
            foreign = await client.post(
                "/api/v1/selections/admission?instrument_id=600001", json=body
            )
            assert foreign.status_code == 422
            await _assert_tampering_rejected(client, body)
            body["data_fields"] = []
            blocked = await client.post("/api/v1/selections/admission", json=body)
            assert blocked.status_code == 200
            assert blocked.json()["data"]["allowed"] is False
            rejected = await client.post("/api/v1/selections/runs", json=body)
            assert rejected.status_code == 422
            assert "SELECTION_DATA_ADMISSION_BLOCKED" in rejected.text
            body.pop("data_from")
            body.pop("data_to")
            legacy = await client.post("/api/v1/selections/runs", json=body)
            assert legacy.status_code == 422, legacy.text
            assert len(runs.list_by_spec("admission-test")) == 1
        await container.close()
        pool.close_all()


async def _assert_tampering_rejected(client, body):
    for field_name, forged in (
        ("average_turnover", 999999.0),
        ("average_turnover", None),
        ("is_st", True),
        ("declared_missing_inputs", ["average_turnover"]),
    ):
        tampered = deepcopy(body)
        tampered["instruments"][0][field_name] = forged
        preview = await client.post("/api/v1/selections/admission", json=tampered)
        assert preview.status_code == 200
        assert preview.json()["data"]["allowed"] is False
        assert "CONSUMER_INPUT_MISMATCH" in preview.text
        denied = await client.post("/api/v1/selections/runs", json=tampered)
        assert denied.status_code == 422
    for field_name, forged in (
        ("universe_snapshot_id", "forged-universe"),
        ("data_from", "2026-09-17"),
        ("industries", []),
        ("rotation_missing_inputs", ["relative_strength_5d"]),
    ):
        tampered = deepcopy(body)
        tampered[field_name] = forged
        denied = await client.post("/api/v1/selections/runs", json=tampered)
        assert denied.status_code == 422
        assert "CONSUMER_INPUT_MISMATCH" in denied.text


async def _assert_historical_scope(client, request, body):
    historical = await client.post(
        f"/api/v1/universes/{request.universe_sources.universe_id}/history",
        json={
            "sources": body["universe_sources"],
            "as_of": request.as_of.date().isoformat(),
            "knowledge_cutoff": body["knowledge_cutoff"],
            "publication_cutoff": body["publication_cutoff"],
        },
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["data"]["snapshot_id"] == request.universe_snapshot_id
    assert historical.json()["data"]["members"][0]["investable"] is True
