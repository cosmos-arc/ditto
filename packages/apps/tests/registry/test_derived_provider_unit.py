"""Tests for FeaturesStorageProvider/AnalysisStorageProvider and App Provider wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_analysis.di import AnalysisStorageProvider
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.queries.derived import DerivedQueryFacade
from ditto_apps.registry import ConfigProvider
from ditto_apps.registry.infra import NotificationProvider
from ditto_data.di import (
    CapitalProvider,
    FundamentalProvider,
    MacroProvider,
    MarketProvider,
    MetadataProvider,
    QualityProvider,
    RuntimeProvider,
)
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_data.sources.tdx.source import TdxSource
from ditto_features.di import FeaturesStorageProvider
from ditto_features.services.derived import DerivedQueryService

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
    from ditto_application.providers import get_app_providers
    from ditto_execution.di import ExecutionStorageProvider
    from ditto_strategy.di import StrategyStorageProvider

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
        FeaturesStorageProvider(),
        AnalysisStorageProvider(),
        ExecutionStorageProvider(),
        NotificationProvider(),
        StrategyStorageProvider(),
        *get_app_providers(),
    )

    """Tests for FeaturesStorageProvider and AnalysisStorageProvider."""

    def test_provider_builds_query_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """FeaturesStorageProvider should wire the DerivedQueryService."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
            MetadataProvider(),
            MarketProvider(),
            CapitalProvider(),
            FeaturesStorageProvider(),
        )

        query_service = container.get(DerivedQueryService)

        assert isinstance(query_service, DerivedQueryService)
        container.close()

    def test_registry_exports_features_storage_provider(self) -> None:
        """FeaturesStorageProvider should be exported from ditto_features.di."""
        import ditto_features.di as features_di

        assert "FeaturesStorageProvider" in features_di.__all__

    def test_registry_exports_analysis_storage_provider(self) -> None:
        """AnalysisStorageProvider should be exported from ditto_analysis.di."""
        import ditto_analysis.di as analysis_di

        assert "AnalysisStorageProvider" in analysis_di.__all__

    def test_features_storage_provider_methods(self) -> None:
        """FeaturesStorageProvider 应包含衍生数据相关方法。"""
        from dishka import Provider as BaseProvider

        provider = FeaturesStorageProvider()
        base_methods = {name for name in dir(BaseProvider) if not name.startswith("_")}
        all_methods = {
            name
            for name in dir(provider)
            if not name.startswith("_") and callable(getattr(provider, name))
        }
        provide_methods = all_methods - base_methods
        expected = {
            "derived_catalog_reader",
            "derived_catalog_writer",
            "derived_catalog_service",
            "derived_query_service",
        }
        assert expected == provide_methods

    def test_analysis_storage_provider_methods(self) -> None:
        """AnalysisStorageProvider 应包含研究相关方法。"""
        from dishka import Provider as BaseProvider

        provider = AnalysisStorageProvider()
        base_methods = {name for name in dir(BaseProvider) if not name.startswith("_")}
        all_methods = {
            name
            for name in dir(provider)
            if not name.startswith("_") and callable(getattr(provider, name))
        }
        provide_methods = all_methods - base_methods
        expected = {
            "research_catalog_reader",
            "research_catalog_writer",
            "research_catalog_service",
            "research_artifact_service",
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
