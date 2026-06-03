"""Unit tests for strategy route error handling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    PublishStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.strategy import publish_strategy, update_strategy
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import (
    PublishStrategyRequest,
    StrategyResponse,
    UpdateStrategyRequest,
)

pytestmark = pytest.mark.asyncio

_UpdateRoute = Callable[..., Awaitable[APIResponse[StrategyResponse]]]
_PublishRoute = Callable[..., Awaitable[APIResponse[bool]]]


@pytest.fixture
def mock_update_handler() -> MagicMock:
    return MagicMock(spec=UpdateStrategyHandler)


@pytest.fixture
def mock_publish_handler() -> MagicMock:
    return MagicMock(spec=PublishStrategyHandler)


@pytest.fixture
def mock_create_handler() -> MagicMock:
    return MagicMock(spec=CreateStrategyHandler)


@pytest.fixture
def mock_query_facade() -> MagicMock:
    return MagicMock(spec=StrategyQueryFacade)


@pytest.fixture(autouse=True)
def _inline_strategy_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr("ditto_apps.api.routes.strategy.run_blocking", run_inline)


async def _call_update(
    strategy_id: str,
    request: UpdateStrategyRequest,
    handler: UpdateStrategyHandler,
) -> APIResponse[StrategyResponse]:
    route = cast(
        _UpdateRoute, getattr(update_strategy, "__dishka_orig_func__", update_strategy)
    )
    return await route(strategy_id=strategy_id, request=request, handler=handler)


async def _call_publish(
    strategy_id: str,
    request: PublishStrategyRequest,
    handler: PublishStrategyHandler,
) -> APIResponse[bool]:
    route = cast(
        _PublishRoute,
        getattr(publish_strategy, "__dishka_orig_func__", publish_strategy),
    )
    return await route(strategy_id=strategy_id, request=request, handler=handler)


class TestUpdateStrategyErrorMapping:
    """PUT /strategies/{id} — ValueError 错误映射."""

    async def test_update_not_found_returns_404(
        self,
        mock_update_handler: MagicMock,
    ) -> None:
        """策略不存在 -> 404."""
        mock_update_handler.handle.side_effect = AppCommandError(
            "Strategy not found: missing"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_update(
                "missing",
                UpdateStrategyRequest(name="x", spec_json={}, version=1, tags=[]),
                mock_update_handler,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

    async def test_update_version_conflict_returns_409(
        self,
        mock_update_handler: MagicMock,
    ) -> None:
        """版本冲突 -> 409."""
        mock_update_handler.handle.side_effect = AppCommandError(
            "Version conflict for strategy s1: expected 2, got 3"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_update(
                "s1",
                UpdateStrategyRequest(name="x", spec_json={}, version=3, tags=[]),
                mock_update_handler,
            )
        assert exc_info.value.status_code == 409
        assert "conflict" in exc_info.value.message.lower()


class TestPublishStrategyErrorMapping:
    """POST /strategies/{id}/publish — ValueError 错误映射."""

    async def test_publish_not_found_returns_404(
        self,
        mock_publish_handler: MagicMock,
    ) -> None:
        """发布不存在的策略 → 404."""
        mock_publish_handler.handle.side_effect = AppCommandError(
            "Strategy not found: missing v1"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_publish(
                "missing",
                PublishStrategyRequest(version=1),
                mock_publish_handler,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()
