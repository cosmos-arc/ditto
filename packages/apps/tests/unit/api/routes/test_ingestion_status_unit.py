"""Ingestion 状态 API 路由单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.ingestion_status import (
    DatasetStatus,
    HistoryItem,
    IngestionStatusQueryFacade,
)
from ditto_apps.api.routes.ingestion import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_facade() -> MagicMock:
    return MagicMock(spec=IngestionStatusQueryFacade)


@pytest.fixture
def app(mock_facade: MagicMock) -> FastAPI:
    """构建测试 FastAPI 应用，注入 mock DI 容器."""
    app = FastAPI()

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def ingestion_status_query_facade(self) -> IngestionStatusQueryFacade:
            return mock_facade

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.unit
class TestGetIngestionStatus:
    """GET /ingestion/status — 各数据集最新摄取状态."""

    def test_returns_status_for_known_datasets(
        self,
        client: TestClient,
        mock_facade: MagicMock,
    ) -> None:
        """返回所有已知数据集的摄取状态."""
        mock_facade.get_status.return_value = [
            DatasetStatus(
                dataset="stock_daily",
                latest_date="2024-01-15",
                latest_status="success",
                record_count=5000,
                last_attempt=None,
            ),
            DatasetStatus(
                dataset="etf_daily",
                latest_date="2024-01-14",
                latest_status="failed",
                record_count=0,
                last_attempt=None,
            ),
        ]

        resp = client.get("/api/v1/ingestion/status")

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        datasets = body["data"]["datasets"]
        assert len(datasets) == 2
        assert datasets[0]["dataset"] == "stock_daily"
        assert datasets[0]["latest_date"] == "2024-01-15"
        assert datasets[0]["latest_status"] == "success"
        assert datasets[0]["record_count"] == 5000
        assert datasets[1]["dataset"] == "etf_daily"
        assert datasets[1]["latest_status"] == "failed"

    def test_returns_empty_when_no_data(
        self,
        client: TestClient,
        mock_facade: MagicMock,
    ) -> None:
        """无数据时返回空列表."""
        mock_facade.get_status.return_value = []

        resp = client.get("/api/v1/ingestion/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["datasets"] == []


@pytest.mark.unit
class TestGetIngestionHistory:
    """GET /ingestion/history — 数据集摄取历史."""

    def test_returns_history_for_dataset(
        self,
        client: TestClient,
        mock_facade: MagicMock,
    ) -> None:
        """返回指定数据集的摄取历史."""
        mock_facade.get_history.return_value = [
            HistoryItem(
                dataset="stock_daily",
                trade_date="2024-01-15",
                status="success",
                rows=5000,
                error_message=None,
                attempts=1,
                last_attempt_at="2024-01-15T18:05:00",
            ),
            HistoryItem(
                dataset="stock_daily",
                trade_date="2024-01-14",
                status="failed",
                rows=None,
                error_message="Connection timeout",
                attempts=2,
                last_attempt_at="2024-01-14T18:10:00",
            ),
        ]

        resp = client.get(
            "/api/v1/ingestion/history",
            params={"dataset": "stock_daily", "limit": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        items = body["data"]
        assert len(items) == 2
        assert items[0]["trade_date"] == "2024-01-15"
        assert items[0]["status"] == "success"
        assert items[0]["rows"] == 5000
        assert items[1]["status"] == "failed"
        assert items[1]["error_message"] == "Connection timeout"

    def test_requires_dataset_param(
        self,
        client: TestClient,
    ) -> None:
        """缺少 dataset 参数时返回 422."""
        resp = client.get("/api/v1/ingestion/history")
        assert resp.status_code == 422

    def test_respects_limit_param(
        self,
        client: TestClient,
        mock_facade: MagicMock,
    ) -> None:
        """limit 参数传递到 facade."""
        mock_facade.get_history.return_value = []

        resp = client.get(
            "/api/v1/ingestion/history",
            params={"dataset": "etf_daily", "limit": 5},
        )

        assert resp.status_code == 200
        mock_facade.get_history.assert_called_once_with("etf_daily", 5)


@pytest.mark.unit
class TestGetDQSummary:
    """GET /ingestion/dq-summary — DQ 检查摘要."""

    def test_returns_empty_datasets_placeholder(
        self,
        client: TestClient,
    ) -> None:
        """V1 占位: 返回空 datasets 列表."""
        resp = client.get("/api/v1/ingestion/dq-summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["datasets"] == []
