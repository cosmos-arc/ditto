"""Unit tests for GET /research/experiments — experiment list route."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.experiments import (
    ExperimentQueryFacade,
    ExperimentSummaryReadModel,
)
from ditto_apps.api.routes.research_experiment_routes import list_research_experiments
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import ExperimentSummaryResponse

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_ListRoute = Callable[..., Awaitable[APIResponse[list[ExperimentSummaryResponse]]]]


@pytest.fixture(autouse=True)
def _inline_experiment_route_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.research_experiment_routes.run_blocking", run_inline
    )


def _summary_info() -> ExperimentSummaryReadModel:
    return ExperimentSummaryReadModel(
        experiment_id="exp-1",
        status="running",
        desired_state="run",
        stage="preflight",
        failure_code=None,
        queue_ordinal=2,
        revision=1,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _unwrap(route: Callable[..., object]) -> Callable[..., object]:
    return cast(Callable[..., object], getattr(route, "__dishka_orig_func__", route))


async def test_list_research_experiments_returns_summaries() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.list_experiments.return_value = [_summary_info()]
    route = cast(_ListRoute, _unwrap(list_research_experiments))

    result = await route(facade=facade)

    assert result.data == [
        ExperimentSummaryResponse(
            experiment_id="exp-1",
            status="running",
            desired_state="run",
            stage="preflight",
            failure_code=None,
            queue_ordinal=2,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
    ]


async def test_list_research_experiments_empty() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.list_experiments.return_value = []
    route = cast(_ListRoute, _unwrap(list_research_experiments))

    result = await route(facade=facade)

    assert result.data == []
