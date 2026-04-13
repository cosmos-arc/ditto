"""Unit tests for cancel / retry route endpoints.

Tests use FastAPI TestClient + Dishka mock DI to exercise the actual
route handlers end-to-end.

Coverage:
  - Cancel: status guards (pending/running allowed, completed/failed/cancelled rejected)
  - Cancel: not found → 404
  - Retry: status guards (failed/cancelled allowed, running/completed/pending rejected)
  - Retry: not found → 404
  - Response field validation
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_app.command.backtest import (
    CancelRunHandler,
    RetryRunHandler,
)
from ditto_app.process.execution.strategy_types import RunLifecycleService
from ditto_app.query.backtest import BacktestQueryFacade
from ditto_interfaces.api.routes.backtest import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cancel_handler() -> MagicMock:
    return MagicMock(spec=CancelRunHandler)


@pytest.fixture
def mock_retry_handler() -> MagicMock:
    return MagicMock(spec=RetryRunHandler)


@pytest.fixture
def mock_query_facade() -> MagicMock:
    return MagicMock(spec=BacktestQueryFacade)


@pytest.fixture
def mock_run_service() -> MagicMock:
    return MagicMock(spec=RunLifecycleService)


@pytest.fixture
def app(
    mock_cancel_handler: MagicMock,
    mock_retry_handler: MagicMock,
    mock_query_facade: MagicMock,
    mock_run_service: MagicMock,
) -> FastAPI:
    """构建测试 FastAPI 应用，注入 mock DI 容器."""
    app = FastAPI()

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def cancel_handler(self) -> CancelRunHandler:
            return mock_cancel_handler

        @provide
        def retry_handler(self) -> RetryRunHandler:
            return mock_retry_handler

        @provide
        def backtest_query_facade(self) -> BacktestQueryFacade:
            return mock_query_facade

        @provide
        def run_lifecycle_service(self) -> RunLifecycleService:
            return mock_run_service

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Cancel: status guards
# ---------------------------------------------------------------------------


class TestCancelStatusGuard:
    """Cancel 端点 — 状态前置校验."""

    def test_cancel_running_succeeds(
        self,
        client: TestClient,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=running → 200, handler.handle 被调用."""
        mock_cancel_handler.handle.return_value = None
        resp = client.post("/api/v1/backtests/runs/run001/cancel")
        assert resp.status_code == 200
        mock_cancel_handler.handle.assert_called_once_with("run001")
        body = resp.json()
        assert body["run_id"] == "run001"
        assert body["status"] == "cancelled"

    def test_cancel_pending_succeeds(
        self,
        client: TestClient,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=pending → 200."""
        mock_cancel_handler.handle.return_value = None
        resp = client.post("/api/v1/backtests/runs/run002/cancel")
        assert resp.status_code == 200

    def test_cancel_completed_rejected(
        self,
        client: TestClient,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=completed → 409 Conflict."""
        mock_cancel_handler.handle.side_effect = ValueError(
            "Cannot cancel run in 'completed' status"
        )
        resp = client.post("/api/v1/backtests/runs/run003/cancel")
        assert resp.status_code == 409
        assert "completed" in resp.json()["detail"]

    def test_cancel_failed_rejected(
        self,
        client: TestClient,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=failed → 409 Conflict."""
        mock_cancel_handler.handle.side_effect = ValueError(
            "Cannot cancel run in 'failed' status"
        )
        resp = client.post("/api/v1/backtests/runs/run004/cancel")
        assert resp.status_code == 409
        assert "failed" in resp.json()["detail"]

    def test_cancel_already_cancelled_rejected(
        self,
        client: TestClient,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """status=cancelled → 409 Conflict."""
        mock_cancel_handler.handle.side_effect = ValueError(
            "Cannot cancel run in 'cancelled' status"
        )
        resp = client.post("/api/v1/backtests/runs/run005/cancel")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Cancel: not found
# ---------------------------------------------------------------------------


class TestCancelNotFound:
    """Cancel 端点 — run_id 不存在 → 404."""

    def test_cancel_not_found(
        self,
        client: TestClient,
        mock_cancel_handler: MagicMock,
    ) -> None:
        """取消不存在的 run → 404."""
        mock_cancel_handler.handle.side_effect = ValueError("Run not found: missing")
        resp = client.post("/api/v1/backtests/runs/missing/cancel")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Retry: status guards
# ---------------------------------------------------------------------------


class TestRetryStatusGuard:
    """Retry 端点 — 状态前置校验."""

    def test_retry_failed_succeeds(
        self,
        client: TestClient,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
    ) -> None:
        """status=failed → 202, handler 返回新 run_id."""
        mock_retry_handler.handle.return_value = "run002"
        mock_query_facade.get_run.return_value = None
        resp = client.post("/api/v1/backtests/runs/run001/retry")
        assert resp.status_code == 202
        mock_retry_handler.handle.assert_called_once_with("run001")
        body = resp.json()
        assert body["run_id"] == "run002"
        assert body["parent_run_id"] == "run001"
        assert body["status"] == "pending"

    def test_retry_cancelled_succeeds(
        self,
        client: TestClient,
        mock_retry_handler: MagicMock,
        mock_query_facade: MagicMock,
    ) -> None:
        """status=cancelled → 202."""
        mock_retry_handler.handle.return_value = "run003"
        mock_query_facade.get_run.return_value = None
        resp = client.post("/api/v1/backtests/runs/run002/retry")
        assert resp.status_code == 202
        body = resp.json()
        assert body["run_id"] == "run003"

    def test_retry_running_rejected(
        self,
        client: TestClient,
        mock_retry_handler: MagicMock,
    ) -> None:
        """status=running → 409 Conflict."""
        mock_retry_handler.handle.side_effect = ValueError(
            "Cannot retry run in 'running' status"
        )
        resp = client.post("/api/v1/backtests/runs/run003/retry")
        assert resp.status_code == 409
        assert "running" in resp.json()["detail"]

    def test_retry_completed_rejected(
        self,
        client: TestClient,
        mock_retry_handler: MagicMock,
    ) -> None:
        """status=completed → 409 Conflict."""
        mock_retry_handler.handle.side_effect = ValueError(
            "Cannot retry run in 'completed' status"
        )
        resp = client.post("/api/v1/backtests/runs/run004/retry")
        assert resp.status_code == 409

    def test_retry_pending_rejected(
        self,
        client: TestClient,
        mock_retry_handler: MagicMock,
    ) -> None:
        """status=pending → 409 Conflict."""
        mock_retry_handler.handle.side_effect = ValueError(
            "Cannot retry run in 'pending' status"
        )
        resp = client.post("/api/v1/backtests/runs/run005/retry")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Retry: not found
# ---------------------------------------------------------------------------


class TestRetryNotFound:
    """Retry 端点 — run_id 不存在 → 404."""

    def test_retry_not_found(
        self,
        client: TestClient,
        mock_retry_handler: MagicMock,
    ) -> None:
        """重试不存在的 run → 404."""
        mock_retry_handler.handle.side_effect = ValueError("Run not found: missing")
        resp = client.post("/api/v1/backtests/runs/missing/retry")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Report endpoint
# ---------------------------------------------------------------------------


class TestGetReport:
    """GET /runs/{run_id}/report 端点测试 (F12)."""

    def test_report_found(
        self,
        client: TestClient,
        mock_query_facade: MagicMock,
    ) -> None:
        """报告存在时返回 200 + JSON data."""
        mock_query_facade.get_report.return_value = {
            "run_id": "run-001",
            "alpha_stats": {"annualized_return": 12.5},
        }
        resp = client.get("/api/v1/backtests/runs/run-001/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["run_id"] == "run-001"
        assert body["data"]["alpha_stats"]["annualized_return"] == 12.5

    def test_report_not_found(
        self,
        client: TestClient,
        mock_query_facade: MagicMock,
    ) -> None:
        """报告不存在时返回 404."""
        mock_query_facade.get_report.return_value = None
        resp = client.get("/api/v1/backtests/runs/nonexistent/report")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_report_delegates_to_facade(
        self,
        client: TestClient,
        mock_query_facade: MagicMock,
    ) -> None:
        """验证正确委托给 facade.get_report."""
        mock_query_facade.get_report.return_value = {"run_id": "run-001"}
        client.get("/api/v1/backtests/runs/run-001/report")
        mock_query_facade.get_report.assert_called_once_with("run-001")
