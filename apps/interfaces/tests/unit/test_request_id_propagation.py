"""request_id 传播测试."""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient


@pytest.fixture
def test_app() -> FastAPI:
    """创建测试用的 FastAPI 应用."""
    app = FastAPI()

    @app.get("/test-endpoint")
    async def test_endpoint(request: Request) -> dict:
        """测试端点，返回 request.state 中的 request_id."""
        return {
            "request_id": getattr(request.state, "request_id", None),
        }

    @app.get("/error-endpoint")
    async def error_endpoint() -> None:
        """测试端点，抛出异常."""
        raise ValueError("Test error")

    return app


def test_request_id_stored_in_state(test_app: FastAPI) -> None:
    """middleware 应将 request_id 存储到 request.state."""
    captured_request_id: list[str] = []

    @test_app.middleware("http")
    async def mock_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """模拟 log_requests middleware."""
        request_id = str(uuid.uuid4())
        # 关键步骤：存储到 request.state
        request.state.request_id = request_id
        captured_request_id.append(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    client = TestClient(test_app)
    response = client.get("/test-endpoint")

    assert response.status_code == 200
    # 验证 request.state 中存储了 request_id
    assert response.json()["request_id"] == captured_request_id[0]


def test_request_id_in_response_header(test_app: FastAPI) -> None:
    """middleware 应在响应头中返回 X-Request-ID."""
    captured_request_id: list[str] = []

    @test_app.middleware("http")
    async def mock_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """模拟 log_requests middleware."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        captured_request_id.append(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    client = TestClient(test_app)
    response = client.get("/test-endpoint")

    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36  # UUID 格式
    assert request_id == captured_request_id[0]


def test_exception_handler_can_access_request_id(test_app: FastAPI) -> None:
    """异常处理器应能从 request.state 获取 request_id."""
    captured_request_id: list[str] = []
    exception_request_id: list[str] = []

    @test_app.middleware("http")
    async def mock_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """模拟 log_requests middleware."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        captured_request_id.append(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @test_app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> Response:
        """模拟 ditto_exception_handler 行为."""
        req_id = getattr(request.state, "request_id", None)
        exception_request_id.append(req_id)
        return Response(
            content='{"error": "test"}',
            status_code=500,
            media_type="application/json",
            headers={"X-Request-ID": req_id or "unknown"},
        )

    client = TestClient(test_app)
    response = client.get("/error-endpoint")

    assert response.status_code == 500
    # 验证异常处理器能获取 request_id
    assert exception_request_id[0] == captured_request_id[0]
    assert response.headers["X-Request-ID"] == captured_request_id[0]
