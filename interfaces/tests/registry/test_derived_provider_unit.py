"""Tests for DerivedProvider (slimmed) and App Provider wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_app.process.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_app.process.materialization.publication_facade import (
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
    TradeProvider,
    get_data_providers,
)
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.services import DerivedQueryService
from ditto_data.sources import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_data.sources.tdx.source import TdxSource
from ditto_interfaces.registry import ConfigProvider
from ditto_interfaces.registry.infra import NotificationProvider

_tdx_mock = MagicMock(spec=TdxSource)


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


class _TdxMockProvider(Provider):
    scope = Scope.APP

    @provide
    def tdx_source(self) -> TdxSource:
        return _tdx_mock


class _GoldenNoneProvider(Provider):
    scope = Scope.APP

    @provide
    def golden_dataset_spec(self) -> GoldenDatasetSpec | None:
        return None


def _make_full_container():
    """构建包含 Data + App 层 Provider 的完整容器。"""
    from ditto_app.providers import get_app_providers

    return make_container(
        ConfigProvider(),
        QualityProvider(),
        _sources_provider(),
        _TdxMockProvider(),
        _GoldenNoneProvider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        CapitalProvider(),
        FundamentalProvider(),
        MacroProvider(),
        DerivedProvider(),
        TradeProvider(),
        NotificationProvider(),
        *get_app_providers(),
    )


class TestDerivedProvider:
    """Tests for slimmed DerivedProvider (仅 Data 层服务)."""

    def test_provider_builds_query_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedProvider should wire the Data DerivedQueryService."""
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
        """DerivedProvider should be defined in ditto_data.di."""
        import ditto_data.di as data_di

        provider_names = [type(provider).__name__ for provider in get_data_providers()]

        assert "DerivedProvider" in provider_names
        assert "DerivedProvider" in data_di.__all__

    def test_derived_provider_only_has_data_methods(self) -> None:
        """DerivedProvider 应仅包含 Data 层方法。"""
        from dishka import Provider as BaseProvider

        provider = DerivedProvider()
        base_methods = {name for name in dir(BaseProvider) if not name.startswith("_")}
        all_methods = {
            name
            for name in dir(provider)
            if not name.startswith("_") and callable(getattr(provider, name))
        }
        provide_methods = all_methods - base_methods
        expected = {
            "research_artifact_service",
            "derived_query_service",
        }
        assert expected == provide_methods


class TestAppProviderDerivedWiring:
    """Tests for App Provider 提供 Derived 相关的 Facade/Orchestrator。"""

    def test_app_provider_builds_query_facade(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """AppMarketQueryProvider 应提供 DerivedQueryFacade。"""
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
