"""Unit tests for GET /research/reviews — cross-strategy review queue route."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.contracts import StrategyVersionInfo
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_apps.api.routes.research_review_routes import list_research_reviews
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import StrategyVersionResponse

pytestmark = pytest.mark.asyncio

_ListRoute = Callable[..., Awaitable[APIResponse[list[StrategyVersionResponse]]]]


@pytest.fixture(autouse=True)
def _inline_review_route_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.research_review_routes.run_blocking", run_inline
    )


def _review_info() -> StrategyVersionInfo:
    return StrategyVersionInfo(
        strategy_id="s-1",
        version=2,
        parent_version=1,
        spec_hash="a" * 64,
        state="review",
        review_outcome="pending",
        created_at="2026-07-25T00:00:00Z",
    )


def _unwrap(route: Callable[..., object]) -> Callable[..., object]:
    return cast(Callable[..., object], getattr(route, "__dishka_orig_func__", route))


async def test_list_research_reviews_returns_review_queue() -> None:
    facade = MagicMock(spec=StrategyQueryFacade)
    facade.list_reviews.return_value = [_review_info()]
    route = cast(_ListRoute, _unwrap(list_research_reviews))

    result = await route(facade=facade)

    assert result.data == [
        StrategyVersionResponse(
            strategy_id="s-1",
            version=2,
            parent_version=1,
            spec_hash="a" * 64,
            state="review",
            review_outcome="pending",
            created_at="2026-07-25T00:00:00Z",
        )
    ]
    facade.list_reviews.assert_called_once_with()


async def test_list_research_reviews_empty() -> None:
    facade = MagicMock(spec=StrategyQueryFacade)
    facade.list_reviews.return_value = []
    route = cast(_ListRoute, _unwrap(list_research_reviews))

    result = await route(facade=facade)

    assert result.data == []
