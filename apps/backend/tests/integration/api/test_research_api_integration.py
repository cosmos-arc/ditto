"""Test-owned HTTP/OpenAPI contract for the R3 experiment read surface."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import MappingProxyType
from unittest.mock import MagicMock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.experiments import (
    ExperimentCandidateReadModel,
    ExperimentDetailReadModel,
    ExperimentFoldReadModel,
    ExperimentQueryFacade,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.maturity import build_maturity_openapi_schema
from ditto_apps.api.routes.research_experiment_routes import router
from ditto_apps.main import _generate_stable_operation_id
from ditto_apps.middleware import api_error_handler
from fastapi import FastAPI

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _detail() -> ExperimentDetailReadModel:
    candidate = ExperimentCandidateReadModel(
        candidate_id="candidate-1",
        ordinal=1,
        is_baseline=False,
        parameters=MappingProxyType({"lookback": 20, "weights": (0.4, 0.6)}),
    )
    fold = ExperimentFoldReadModel(
        candidate_id="candidate-1",
        fold_id="fold-1",
        ordinal=1,
        role="walk_forward",
        status="completed",
        train_start=date(2018, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        purge_sessions=5,
        embargo_sessions=2,
        claim_owner_token=None,
        revision=2,
        updated_at=datetime(2026, 7, 28, 1, 0, tzinfo=UTC),
    )
    return ExperimentDetailReadModel(
        experiment_id="exp-1",
        research_cycle_id="cycle-1",
        research_cycle_hash="cycle-hash",
        strategy_version="1",
        strategy_spec_hash="spec-hash",
        snapshot_id="snapshot-1",
        status="completed",
        desired_state="run",
        stage="completed",
        failure_code=None,
        queue_ordinal=None,
        revision=3,
        created_at=datetime(2026, 7, 28, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 28, 1, 0, tzinfo=UTC),
        seed=42,
        worker_count=2,
        failure_policy="continue",
        candidate_limit=128,
        fold_run_limit=24,
        fold_protocol_id="r3-walk-forward",
        fold_protocol_version=1,
        fold_protocol_hash="fold-hash",
        candidates=(candidate,),
        folds=(fold,),
    )


async def test_candidate_http_and_live_openapi_contract_are_test_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real router without starting the production app lifespan."""

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
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.side_effect = lambda experiment_id: (
        _detail() if experiment_id == "exp-1" else None
    )

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def experiment_query_facade(self) -> ExperimentQueryFacade:
            return facade

    container = make_async_container(TestProvider())
    test_app = FastAPI(generate_unique_id_function=_generate_stable_operation_id)
    setup_dishka(container=container, app=test_app)
    test_app.include_router(router, prefix="/api/v1")
    test_app.add_exception_handler(APIError, api_error_handler)
    test_app.openapi = lambda: build_maturity_openapi_schema(test_app)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/research/experiments/exp-1/candidates")
            missing = await client.get(
                "/api/v1/research/experiments/missing/candidates"
            )

        assert response.status_code == 200
        assert response.json()["data"] == [
            {
                "candidate_id": "candidate-1",
                "ordinal": 1,
                "is_baseline": False,
                "parameters": {"lookback": 20, "weights": [0.4, 0.6]},
            }
        ]
        assert missing.status_code == 404

        schema = test_app.openapi()
        operation = schema["paths"][
            "/api/v1/research/experiments/{experiment_id}/candidates"
        ]["get"]
        assert operation["operationId"] == "research_list_experiment_candidates"
        assert operation["x-ditto-maturity"] == "experimental"

        operation_ids = [
            item["operationId"]
            for methods in schema["paths"].values()
            for method, item in methods.items()
            if method != "parameters"
        ]
        assert len(operation_ids) == len(set(operation_ids))
    finally:
        await container.close()
