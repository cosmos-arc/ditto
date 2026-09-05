"""Tests for FastAPI main application async endpoints."""

import hashlib
import importlib.metadata
import json

import ditto_apps.main as main_module
import pytest
from ditto_apps.api.app_metadata import BuildMetadata
from ditto_apps.api.routes import system as system_routes
from ditto_apps.api.routes.debug import generate_test_logs
from ditto_apps.config.runtime import RuntimePaths
from ditto_apps.main import (
    app,
    get_status,
    health_check,
    root,
)
from ditto_apps.openapi_contract import canonical_openapi_bytes, create_openapi_app
from ditto_apps.registry.infra.observability import ObservabilityLifecycle
from ditto_data.config.data_store import DataStoreSettings
from ditto_platform.foundation import (
    ConfigInitCoordinator,
    Environment,
    ObservabilitySettings,
    Settings,
    SystemSettings,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.requests import Request

ditto_version = importlib.metadata.version("ditto-apps")


def _make_request(*, path: str = "/api/v1/status") -> Request:
    app.state.settings = Settings(
        system=SystemSettings(environment=Environment.TESTING),
        observability=ObservabilitySettings(),
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
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
        app.state.build_metadata = BuildMetadata(
            product_version="2026.9.4",
            git_sha="d" * 40,
            api_contract_version="v1",
            api_contract_sha256="a" * 64,
        )
        response = await get_status(_make_request())
        assert response["status"] == "running"
        assert response["version"] == ditto_version
        assert response["product_version"] == "2026.9.4"
        assert response["git_sha"] == "d" * 40
        assert response["api_contract_version"] == "v1"
        assert response["api_contract_sha256"] == "a" * 64
        assert "environment" in response
        assert response["features"]["data_collection"] is True
        assert response["features"]["data_validation"] is True

    @pytest.mark.asyncio
    async def test_get_status_fails_closed_without_verified_build_metadata(self):
        """The status route must not reconstruct cohort identity from ambient env."""
        if hasattr(app.state, "build_metadata"):
            del app.state.build_metadata

        with pytest.raises(RuntimeError, match="verified build metadata"):
            await get_status(_make_request())

    @pytest.mark.asyncio
    async def test_readiness_requires_initialized_usable_runtime_roots(
        self,
        tmp_path,
    ) -> None:
        """Readiness is stateful and verifies configured filesystem roots."""
        route = next(
            (
                candidate
                for candidate in system_routes.router.routes
                if isinstance(candidate, APIRoute) and candidate.path == "/readyz"
            ),
            None,
        )
        assert route is not None, "/readyz route is not registered"

        config_root = tmp_path / "config"
        state_root = tmp_path / "state"
        cache_root = tmp_path / "cache"
        for root_path in (config_root, state_root, cache_root):
            root_path.mkdir()
        app.state.runtime_paths = RuntimePaths(
            config_root=config_root,
            state_root=state_root,
            cache_root=cache_root,
        )
        app.state.runtime_initialized = True

        response = await route.endpoint(_make_request(path="/readyz"))
        payload = json.loads(response.body)

        assert response.status_code == 200
        assert payload["status"] == "ready"
        assert payload["checks"]["config_root"]["ok"] is True
        assert payload["checks"]["state_root"]["ok"] is True

        state_root.rmdir()
        response = await route.endpoint(_make_request(path="/readyz"))
        payload = json.loads(response.body)

        assert response.status_code == 503
        assert payload["status"] == "not_ready"
        assert payload["checks"]["state_root"]["ok"] is False

        state_root.mkdir()
        app.state.runtime_initialized = False
        response = await route.endpoint(_make_request(path="/readyz"))
        payload = json.loads(response.body)

        assert response.status_code == 503
        assert payload["status"] == "not_ready"
        assert payload["checks"]["startup"]["ok"] is False


@pytest.mark.unit
class TestOpenAPIMaturity:
    """OpenAPI should expose capability maturity honestly."""

    def test_strategy_publish_surface_is_evidence_gated(self):
        """OpenAPI excludes the seed/system fast-path and keeps governed publish."""
        app.openapi_schema = None

        paths = app.openapi()["paths"]

        assert "/api/v1/strategies/{strategy_id}/publish" not in paths
        assert "/api/v1/strategies/{strategy_id}/versions/{version}/publish" in paths

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
        manual_operation = schema["paths"]["/api/v1/manual/daily-decision/v2"]["get"]
        assert manual_operation["x-ditto-maturity"] == "initial-focus"
        assert "Capability maturity: `initial-focus`" in manual_operation["description"]
        manual_tag = next(tag for tag in schema["tags"] if tag["name"] == "manual")
        assert manual_tag["x-ditto-maturity"] == "initial-focus"
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

    def test_openapi_operation_ids_are_frontend_contract_stable(self):
        """Generated clients should see stable tag-scoped method names."""
        app.openapi_schema = None

        schema = app.openapi()

        assert (
            schema["paths"]["/api/v1/backtests/runs"]["post"]["operationId"]
            == "backtests_trigger_backtest"
        )
        assert (
            schema["paths"]["/api/v1/market/bars"]["post"]["operationId"]
            == "market_post_bars"
        )
        assert (
            schema["paths"]["/api/v1/fx/bars"]["post"]["operationId"] == "fx_post_bars"
        )
        assert schema["paths"]["/"]["get"]["operationId"] == "system_root"

        operation_ids = [
            operation["operationId"]
            for methods in schema["paths"].values()
            for method, operation in methods.items()
            if method != "parameters"
        ]
        assert len(operation_ids) == len(set(operation_ids))
        assert not any("_api_v1_" in operation_id for operation_id in operation_ids)


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
                self.runtime_paths = RuntimePaths(
                    config_root=tmp_path / "config",
                    state_root=self.data_store_settings.data_root,
                    cache_root=tmp_path / "cache",
                )
                self.runtime_paths.config_root.mkdir()
                self.runtime_paths.state_root.mkdir()
                self.observability_started = False
                self.closed = False

            async def get(self, dependency_type):
                if dependency_type is ObservabilityLifecycle:
                    self.observability_started = True
                    return object()
                if dependency_type is ConfigInitCoordinator:
                    return self.coordinator
                if dependency_type is DataStoreSettings:
                    return self.data_store_settings
                if dependency_type is Settings:
                    return self.settings
                if dependency_type is RuntimePaths:
                    return self.runtime_paths
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
        test_app = FastAPI()
        test_app.state.dishka_container = container

        async with main_module.lifespan(test_app):
            pass

        assert container.coordinator.data_root == tmp_path / "container-root"
        assert test_app.state.settings is container.settings
        assert container.observability_started is True
        expected_contract_sha256 = hashlib.sha256(
            canonical_openapi_bytes(create_openapi_app().openapi())
        ).hexdigest()
        assert (
            test_app.state.build_metadata.api_contract_sha256
            == expected_contract_sha256
        )
        assert container.closed is True

    @pytest.mark.asyncio
    async def test_production_startup_rejects_missing_cohort_metadata(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Production must never start with development metadata fallbacks."""
        for name in (
            "DITTO_PRODUCT_VERSION",
            "DITTO_GIT_SHA",
            "DITTO_API_CONTRACT_VERSION",
            "DITTO_API_CONTRACT_SHA256",
        ):
            monkeypatch.delenv(name, raising=False)

        class FakeCoordinator:
            def initialize(self, **_kwargs):
                return {}

        class FakeContainer:
            def __init__(self) -> None:
                state_root = tmp_path / "state"
                config_root = tmp_path / "config"
                state_root.mkdir()
                config_root.mkdir()
                self.runtime_paths = RuntimePaths(
                    config_root=config_root,
                    state_root=state_root,
                    cache_root=tmp_path / "cache",
                )
                self.settings = Settings(
                    system=SystemSettings(environment=Environment.PRODUCTION),
                    observability=ObservabilitySettings(),
                )
                self.closed = False

            async def get(self, dependency_type):
                if dependency_type is ObservabilityLifecycle:
                    return object()
                if dependency_type is RuntimePaths:
                    return self.runtime_paths
                if dependency_type is ConfigInitCoordinator:
                    return FakeCoordinator()
                if dependency_type is DataStoreSettings:
                    return DataStoreSettings(data_root=self.runtime_paths.state_root)
                if dependency_type is Settings:
                    return self.settings
                raise AssertionError(f"Unexpected dependency: {dependency_type!r}")

            async def close(self) -> None:
                self.closed = True

        container = FakeContainer()
        test_app = FastAPI()
        test_app.state.dishka_container = container

        with pytest.raises(
            ValueError,
            match="production requires explicit valid cohort metadata",
        ):
            async with main_module.lifespan(test_app):
                pytest.fail("production lifespan yielded without cohort metadata")

        assert test_app.state.runtime_initialized is False
        assert container.closed is True
