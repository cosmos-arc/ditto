"""Tests for FastAPI main application async endpoints."""

import importlib.metadata
from types import SimpleNamespace

import ditto_apps.main as main_module
import pytest
from ditto_apps.api.routes.debug import generate_test_logs
from ditto_apps.main import (
    app,
    get_status,
    health_check,
    root,
)
from ditto_data.config.data_store import DataStoreSettings
from ditto_platform.foundation import (
    ConfigInitCoordinator,
    Environment,
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from starlette.requests import Request

ditto_version = importlib.metadata.version("ditto-apps")


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
class TestOpenAPIMaturity:
    """OpenAPI should expose capability maturity honestly."""

    def test_openapi_operations_include_maturity_extension(self):
        """Every documented operation carries x-ditto-maturity."""
        app.openapi_schema = None

        schema = app.openapi()
        missing: list[str] = []
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if method == "parameters":
                    continue
                if "x-ditto-maturity" not in operation:
                    missing.append(f"{method.upper()} {path}")

        assert missing == []

    def test_openapi_maturity_matches_route_scope(self):
        """Route maturity distinguishes initial-focus, experimental, infra and debug."""
        app.openapi_schema = None

        schema = app.openapi()

        assert (
            schema["paths"]["/api/v1/market/bars"]["post"]["x-ditto-maturity"]
            == "initial-focus"
        )
        assert (
            schema["paths"]["/api/v1/macro/indicators"]["post"]["x-ditto-maturity"]
            == "experimental"
        )
        assert (
            "Capability maturity: `experimental`"
            in schema["paths"]["/api/v1/macro/indicators"]["post"]["description"]
        )
        assert (
            schema["paths"]["/api/v1/ingestion/status"]["get"]["x-ditto-maturity"]
            == "infrastructure"
        )
        assert (
            schema["paths"]["/api/v1/logs/test"]["get"]["x-ditto-maturity"] == "debug"
        )


@pytest.mark.unit
class TestTestLogsEndpoint:
    """Tests for test logs endpoint."""

    @pytest.mark.asyncio
    async def test_test_logs_endpoint_returns_expected_message(self):
        """Test test logs endpoint returns expected message."""
        # 环境检查已移到路由注册阶段，函数本身不再检查环境
        response = await generate_test_logs()
        assert response == {"message": "Test logs generated"}


@pytest.mark.unit
class TestLifespan:
    """Tests for application lifespan dependency resolution."""

    @pytest.mark.asyncio
    async def test_uses_container_data_store_settings(self, tmp_path, monkeypatch):
        """Lifespan should initialize with container-owned settings."""

        class FakeCoordinator:
            def __init__(self) -> None:
                self.data_root = None

            def initialize(self, **kwargs):
                self.data_root = kwargs["data_root"]
                return {}

        class FakeContainer:
            def __init__(self) -> None:
                self.coordinator = FakeCoordinator()
                self.data_store_settings = DataStoreSettings(
                    data_root=tmp_path / "container-root"
                )
                self.settings = Settings(
                    system=SystemSettings(environment=Environment.TESTING),
                    observability=ObservabilitySettings(),
                )
                self.closed = False

            async def get(self, dependency_type):
                if dependency_type is ConfigInitCoordinator:
                    return self.coordinator
                if dependency_type is DataStoreSettings:
                    return self.data_store_settings
                if dependency_type is Settings:
                    return self.settings
                raise AssertionError(f"Unexpected dependency: {dependency_type!r}")

            async def close(self) -> None:
                self.closed = True

        loader_settings = DataStoreSettings(data_root=tmp_path / "loader-root")
        monkeypatch.setattr(
            main_module,
            "load_data_store_settings",
            lambda: loader_settings,
            raising=False,
        )

        container = FakeContainer()
        test_app = SimpleNamespace(state=SimpleNamespace(dishka_container=container))

        async with main_module.lifespan(test_app):
            pass

        assert container.coordinator.data_root == tmp_path / "container-root"
        assert test_app.state.settings is container.settings
        assert container.closed is True
