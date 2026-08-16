"""Tests for FeaturesStorageProvider/AnalysisStorageProvider and App Provider wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_analysis.di import AnalysisStorageProvider
from ditto_application.commands.catalog_remediation import (
    CatalogRemediationIngestDatePort,
)
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.queries.derived import DerivedQueryFacade
from ditto_application.queries.source import SourceDataPort
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
from ditto_data.lineage import DataLineageRecorder
from ditto_data.lineage.sqlite_store import SQLiteDataLineage
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    TdxSourceProtocol,
)
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_data.sources.tdx.source import TdxSource
from ditto_features.compile_cache import SQLiteCompileCacheBackend
from ditto_features.di import FeaturesStorageProvider
from ditto_features.services import DerivedQueryService

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


class _ProtocolAdapterProvider(Provider):
    """测试用 Protocol 适配器 — 桥接 concrete mock → Protocol 接口."""

    scope = Scope.APP

    @provide
    def tdx_source_protocol(self, source: TdxSource) -> TdxSourceProtocol:
        return source

    @provide
    def comparison_store_protocol(self) -> ComparisonStoreProtocol:
        return MagicMock(spec=ComparisonStoreProtocol)

    @provide
    def instrument_store_protocol(self) -> InstrumentStoreProtocol:
        return MagicMock(spec=InstrumentStoreProtocol)

    @provide
    def compile_cache_backend(self) -> SQLiteCompileCacheBackend:
        return MagicMock(spec=SQLiteCompileCacheBackend)

    @provide
    def source_data_port(self) -> SourceDataPort:
        return MagicMock(spec=SourceDataPort)

    @provide
    def catalog_remediation_ingest_date_port(
        self,
    ) -> CatalogRemediationIngestDatePort:
        return MagicMock()


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
        _ProtocolAdapterProvider(),
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


class TestStorageProviderWiring:
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
            "derived_shadow_slot_reader",
            "derived_shadow_slot_writer",
            "derived_shadow_slot_service",
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
            "research_experiment_database",
            "research_experiment_reader_port",
            "research_experiment_reader",
            "research_experiment_writer_port",
            "research_experiment_writer",
            "research_campaign_reader",
            "research_campaign_reader_port",
            "research_campaign_writer",
            "research_campaign_writer_port",
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

    def test_materialization_orchestrator_receives_persistent_lineage_recorder(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedMaterializationOrchestrator should persist lineage via DI."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = _make_full_container()

        lineage_recorder = container.get(DataLineageRecorder)
        orchestrator = container.get(DerivedMaterializationOrchestrator)

        assert isinstance(lineage_recorder, SQLiteDataLineage)
        assert orchestrator._lineage_recorder is lineage_recorder
        container.close()
