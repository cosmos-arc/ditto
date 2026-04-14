"""Unit tests for strategy route error handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_app.command.strategy import (
    CreateStrategyHandler,
    PublishStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_app.query.strategy import StrategyQueryFacade
from ditto_interfaces.api.errors import APIError
from ditto_interfaces.api.routes.strategy import router
from ditto_interfaces.middleware import api_error_handler
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


@pytest.fixture
def app(
    mock_update_handler: MagicMock,
    mock_publish_handler: MagicMock,
    mock_create_handler: MagicMock,
    mock_query_facade: MagicMock,
) -> FastAPI:
    """构建测试 FastAPI 应用，注入 mock DI 容器."""
    app = FastAPI()

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def update_handler(self) -> UpdateStrategyHandler:
            return mock_update_handler

        @provide
        def publish_handler(self) -> PublishStrategyHandler:
            return mock_publish_handler

        @provide
        def create_handler(self) -> CreateStrategyHandler:
            return mock_create_handler

        @provide
        def strategy_query_facade(self) -> StrategyQueryFacade:
            return mock_query_facade

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")

    # 注册 APIError 异常处理器，确保 APIError 被正确处理
    app.add_exception_handler(APIError, api_error_handler)

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestUpdateStrategyErrorMapping:
    """PUT /strategies/{id} — ValueError 错误映射."""

    def test_update_not_found_returns_404(
        self,
        client: TestClient,
        mock_update_handler: MagicMock,
    ) -> None:
        """策略不存在 -> 404."""
        mock_update_handler.handle.side_effect = ValueError(
            "Strategy not found: missing"
        )
        resp = client.put(
            "/api/v1/strategies/missing",
            json={"name": "x", "spec_json": {}, "version": 1, "tags": []},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_update_version_conflict_returns_409(
        self,
        client: TestClient,
        mock_update_handler: MagicMock,
    ) -> None:
        """版本冲突 -> 409."""
        mock_update_handler.handle.side_effect = ValueError(
            "Version conflict for strategy s1: expected 2, got 3"
        )
        resp = client.put(
            "/api/v1/strategies/s1",
            json={"name": "x", "spec_json": {}, "version": 3, "tags": []},
        )
        assert resp.status_code == 409
        assert "conflict" in resp.json()["detail"].lower()


class TestPublishStrategyErrorMapping:
    """POST /strategies/{id}/publish — ValueError 错误映射."""

    def test_publish_not_found_returns_404(
        self,
        client: TestClient,
        mock_publish_handler: MagicMock,
    ) -> None:
        """发布不存在的策略 → 404."""
        mock_publish_handler.handle.side_effect = ValueError(
            "Strategy not found: missing v1"
        )
        resp = client.post(
            "/api/v1/strategies/missing/publish",
            json={"version": 1},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
