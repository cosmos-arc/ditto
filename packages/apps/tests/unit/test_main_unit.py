"""Tests for FastAPI main application async endpoints."""

import pytest
from ditto_apps.api.routes.debug import generate_test_logs
from ditto_apps.main import (
    app,
    get_status,
    health_check,
    root,
)
from ditto_kernel import __version__ as ditto_version
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from starlette.requests import Request


def _make_request() -> Request:
    app.state.settings = Settings(
        system=SystemSettings(environment=Environment.TESTING),
        observability=ObservabilitySettings(),
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/status",
        "headers": [],
        "app": app,
    }
    return Request(scope)


@pytest.mark.unit
class TestFastAPIEndpoints:
    """Tests for FastAPI async endpoint functions."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test root endpoint returns expected message."""
        response = await root()
        assert response == {"message": "Ditto Quant API", "version": ditto_version}

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self):
        """Test health check endpoint returns ok status."""
        response = await health_check()
        assert response["status"] == "ok"
        assert response["service"] == "ditto-api"
        assert "timestamp" in response
        assert response["features"]["prefect"] is True
        assert response["features"]["observability"] is True

    @pytest.mark.asyncio
    async def test_get_status_endpoint(self):
        """Test get status endpoint returns system status."""
        response = await get_status(_make_request())
        assert response["status"] == "running"
        assert response["version"] == ditto_version
        assert "environment" in response
        assert response["features"]["data_collection"] is True
        assert response["features"]["data_validation"] is True


@pytest.mark.unit
class TestTestLogsEndpoint:
    """Tests for test logs endpoint."""

    @pytest.mark.asyncio
    async def test_test_logs_endpoint_returns_expected_message(self):
        """Test test logs endpoint returns expected message."""
        # 环境检查已移到路由注册阶段，函数本身不再检查环境
        response = await generate_test_logs()
        assert response == {"message": "Test logs generated"}
