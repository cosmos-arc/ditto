"""Tests for App 层 DI Provider 结构和容器集成。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_app.builders.strategy import (
    BacktestRuntimeBuilder,
    StrategyRuntimeBuilder,
    StrategyServiceFactory,
    StrategySliceBuilder,
)
from ditto_app.process.materialization import (
    DerivedMaterializationOrchestrator,
    DerivedPublicationFacade,
    InvalidationCascadeOrchestrator,
)
from ditto_app.process.quality import QualityService
from ditto_app.process.strategy import StrategyFacade
from ditto_app.providers import (
    AppBuilderFactory,
    AppProcessProvider,
    AppQueryProvider,
    get_app_providers,
)
from ditto_app.query.derived import DerivedQueryFacade, StaticRuntimeModeResolver
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.sources import ExchangeTransformers
from ditto_datahub.sources.source import DataSources
from ditto_interfaces.registry.core import QualityProvider
from ditto_interfaces.registry.datahub import (
    CapitalProvider,
    DerivedProvider,
    MarketProvider,
    MetadataProvider,
    RuntimeProvider,
)
from ditto_interfaces.registry.infra import ConfigProvider

# ---------------------------------------------------------------------------
# Test fixtures: 辅助 Provider
# ---------------------------------------------------------------------------


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

        @provide
        def exchange_transformers(self) -> ExchangeTransformers:
            return ExchangeTransformers(
                tushare=MagicMock(),
                tdx=MagicMock(),
            )

    return SourcesProvider()


def _runtime_deps_provider() -> Provider:
    class RuntimeDepsProvider(Provider):
        scope = Scope.APP

        @provide
        def metadata_service(self) -> MetadataService:
            return MagicMock(spec=MetadataService)

        @provide
        def market_service(self) -> MarketService:
            return MagicMock(spec=MarketService)

    return RuntimeDepsProvider()


# ---------------------------------------------------------------------------
# 结构测试：验证 Provider 类拥有正确的 provide 方法
# ---------------------------------------------------------------------------


class TestAppProviderStructure:
    """验证 App 层 Provider 结构。"""

    def test_get_app_providers_returns_three_providers(self) -> None:
        """get_app_providers() 应返回 3 个 Provider 实例。"""

        providers = get_app_providers()
        assert len(providers) == 3
        names = [type(p).__name__ for p in providers]
        assert "AppQueryProvider" in names
        assert "AppProcessProvider" in names
        assert "AppBuilderFactory" in names

    def test_app_query_provider_methods(self) -> None:
        """AppQueryProvider 应包含 3 个 provide 方法。"""

        provider = AppQueryProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "runtime_mode_resolver",
            "derived_query_facade",
            "research_dataset_facade",
        }
        assert expected.issubset(method_names)

    def test_app_process_provider_methods(self) -> None:
        """AppProcessProvider 应包含 5 个 provide 方法。"""

        provider = AppProcessProvider()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "derived_input_provider",
            "derived_materialization_orchestrator",
            "derived_invalidation_orchestrator",
            "derived_publication_facade",
            "quality_service",
        }
        assert expected.issubset(method_names)

    def test_app_builder_factory_methods(self) -> None:
        """AppBuilderFactory 应包含 5 个 provide 方法。"""

        provider = AppBuilderFactory()
        method_names = {name for name in dir(provider) if not name.startswith("_")}
        expected = {
            "strategy_runtime_builder",
            "backtest_runtime_builder",
            "strategy_slice_builder",
            "strategy_service_factory",
            "strategy_facade",
        }
        assert expected.issubset(method_names)


# ---------------------------------------------------------------------------
# 集成测试：验证 App Provider 可以在完整容器中正确解析服务
# ---------------------------------------------------------------------------


class TestAppProviderIntegration:
    """验证 App 层 Provider 与完整容器的集成。"""

    @pytest.fixture
    def app_container(self, monkeypatch, tmp_path):
        """构建包含所有层级的完整测试容器。"""

        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())

        container = make_container(
            ConfigProvider(),
            QualityProvider(),
            _sources_provider(),
            RuntimeProvider(),
            MetadataProvider(),
            MarketProvider(),
            CapitalProvider(),
            DerivedProvider(),
            *get_app_providers(),
            _runtime_deps_provider(),
        )
        yield container
        container.close()

    def test_query_services_resolved(self, app_container) -> None:
        """AppQueryProvider 的服务应可从容器解析。"""
        assert isinstance(
            app_container.get(StaticRuntimeModeResolver),
            StaticRuntimeModeResolver,
        )
        assert isinstance(app_container.get(DerivedQueryFacade), DerivedQueryFacade)

    def test_process_services_resolved(self, app_container) -> None:
        """AppProcessProvider 的服务应可从容器解析。"""
        assert isinstance(
            app_container.get(DerivedMaterializationOrchestrator),
            DerivedMaterializationOrchestrator,
        )
        assert isinstance(
            app_container.get(InvalidationCascadeOrchestrator),
            InvalidationCascadeOrchestrator,
        )
        assert isinstance(
            app_container.get(DerivedPublicationFacade),
            DerivedPublicationFacade,
        )
        assert isinstance(app_container.get(QualityService), QualityService)

    def test_builder_services_resolved(self, app_container) -> None:
        """AppBuilderFactory 的服务应可从容器解析。"""
        assert isinstance(
            app_container.get(StrategyRuntimeBuilder),
            StrategyRuntimeBuilder,
        )
        assert isinstance(
            app_container.get(BacktestRuntimeBuilder),
            BacktestRuntimeBuilder,
        )
        assert isinstance(
            app_container.get(StrategySliceBuilder),
            StrategySliceBuilder,
        )
        assert isinstance(
            app_container.get(StrategyServiceFactory),
            StrategyServiceFactory,
        )
        assert isinstance(app_container.get(StrategyFacade), StrategyFacade)
