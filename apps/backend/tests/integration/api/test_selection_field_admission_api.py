"""Real HTTP selection admission with isolated SQLite evidence and run stores."""

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
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.selection import router
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
    with certified_selection(selection_request()) as (query, request):
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
        )

        class TestProvider(Provider):
            scope = Scope.APP

            @provide
            def selection_facade(self) -> SelectionWorkspaceFacade:
                return facade

        container = make_async_container(TestProvider())
        app = FastAPI()
        setup_dishka(container=container, app=app)
        app.include_router(router, prefix="/api/v1")
        app.add_exception_handler(APIError, api_error_handler)
        body = orjson.loads(orjson.dumps(asdict(request)))
        body["selection_spec"]["asset_kind"] = "stock"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
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
            body["data_fields"] = []
            blocked = await client.post("/api/v1/selections/admission", json=body)
            assert blocked.status_code == 200
            assert blocked.json()["data"]["allowed"] is False
            rejected = await client.post("/api/v1/selections/runs", json=body)
            assert rejected.status_code == 422
            assert "SELECTION_DATA_ADMISSION_BLOCKED" in rejected.text
            assert len(runs.list_by_spec("admission-test")) == 1
        await container.close()
        pool.close_all()
