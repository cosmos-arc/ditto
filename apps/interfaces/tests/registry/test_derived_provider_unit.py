"""Tests for DerivedProvider (slimmed) and App Provider wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_app.process.materialization import (
    DerivedMaterializationOrchestrator,
    DerivedPublicationFacade,
)
from ditto_app.query.derived import DerivedQueryFacade
from ditto_data.di import (
    CapitalProvider,
    DerivedProvider,
    FundamentalProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    QualityProvider,
    RuntimeProvider,
    get_data_providers,
)
from ditto_data.services import DerivedQueryService
from ditto_data.sources import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_interfaces.registry import ConfigProvider


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


def _make_full_container():
    """构建包含 DataHub + App 层 Provider 的完整容器。"""
    from ditto_app.providers import get_app_providers

    return make_container(
        ConfigProvider(),
        QualityProvider(),
        _sources_provider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        CapitalProvider(),
        FundamentalProvider(),
        MacroProvider(),
        DerivedProvider(),
        *get_app_providers(),
    )


class TestDerivedProvider:
    """Tests for slimmed DerivedProvider (仅 DataHub 层服务)."""

    def test_provider_builds_query_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedProvider should wire the DataHub DerivedQueryService."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
            MetadataProvider(),
            MarketProvider(),
            CapitalProvider(),
            DerivedProvider(),
        )

        query_service = container.get(DerivedQueryService)

        assert isinstance(query_service, DerivedQueryService)
        container.close()

    def test_registry_exports_derived_provider(self) -> None:
        """Registry exports should keep DerivedProvider."""
        import ditto_data.di as data_di
        import ditto_interfaces.registry as root_registry

        provider_names = [type(provider).__name__ for provider in get_data_providers()]

        assert "DerivedProvider" in provider_names
        assert "DerivedProvider" in data_di.__all__
        assert "DerivedProvider" in root_registry.__all__

    def test_derived_provider_only_has_datahub_methods(self) -> None:
        """DerivedProvider 应仅包含 DataHub 层方法。"""
        from dishka import Provider as BaseProvider

        provider = DerivedProvider()
        # 过滤掉 Provider 基类的方法，仅保留实例的 @provide 方法
        base_methods = {name for name in dir(BaseProvider) if not name.startswith("_")}
        all_methods = {
            name
            for name in dir(provider)
            if not name.startswith("_") and callable(getattr(provider, name))
        }
        provide_methods = all_methods - base_methods
        # 应仅包含 3 个 DataHub 层方法
        expected = {
            "research_artifact_service",
            "derived_query_service",
            "compile_cache_service",
        }
        assert expected == provide_methods


class TestAppProviderDerivedWiring:
    """Tests for App Provider 提供 Derived 相关的 Facade/Orchestrator。"""

    def test_app_provider_builds_query_facade(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppQueryProvider 应提供 DerivedQueryFacade。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_full_container()

        facade = container.get(DerivedQueryFacade)
        assert isinstance(facade, DerivedQueryFacade)
        container.close()

    def test_app_provider_builds_publication_facade(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppProcessProvider 应提供 DerivedPublicationFacade。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_full_container()

        publication_facade = container.get(DerivedPublicationFacade)
        assert isinstance(publication_facade, DerivedPublicationFacade)
        container.close()

    def test_materialization_orchestrator_has_universe_provider(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedMaterializationOrchestrator should receive UniverseProvider via DI."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_full_container()

        orchestrator = container.get(DerivedMaterializationOrchestrator)
        assert orchestrator._universe_provider is not None
        container.close()
