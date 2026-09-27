"""Lifespan 集成性质用例：真实容器设置装配（自 unit 目录按性质归位，2026-09-27）。"""

import hashlib

import ditto_apps.main as main_module
import pytest
from ditto_apps.config.runtime import RuntimePaths
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


@pytest.mark.integration  # 集成性质(真入口/容器/子进程/重数据), 2026-09-27 分层归位
class TestLifespanContainerSettings:
    """Lifespan 集成性质用例：真实容器设置装配。"""

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
