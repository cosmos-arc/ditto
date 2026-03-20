"""Tests for DerivedProvider wiring and registry exports."""

from __future__ import annotations

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_datahub.services import DerivedQueryService
from ditto_datahub.sources import ExchangeTransformers
from ditto_datahub.sources.source import DataSources
from ditto_port.registry import ConfigProvider
from ditto_port.registry.datahub import (
    CapitalProvider,
    DerivedProvider,
    MarketProvider,
    MetadataProvider,
    RuntimeProvider,
    get_datahub_providers,
)
from ditto_port.services.derived import (
    DerivedPublicationFacade,
    DerivedQueryFacade,
)


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


class TestDerivedProvider:
    """Tests for DerivedProvider."""

    def test_provider_builds_query_service_and_facade(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedProvider should wire the DataHub service and Port facade."""
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
        facade = container.get(DerivedQueryFacade)
        publication_facade = container.get(DerivedPublicationFacade)

        assert isinstance(query_service, DerivedQueryService)
        assert isinstance(facade, DerivedQueryFacade)
        assert isinstance(publication_facade, DerivedPublicationFacade)
        container.close()

    def test_registry_exports_replace_features_provider(self) -> None:
        """Registry exports should keep DerivedProvider and drop FeaturesProvider."""
        import ditto_port.registry as root_registry
        import ditto_port.registry.datahub as datahub_registry

        provider_names = [
            type(provider).__name__ for provider in get_datahub_providers()
        ]

        assert "DerivedProvider" in provider_names
        assert "FeaturesProvider" not in provider_names
        assert "DerivedProvider" in datahub_registry.__all__
        assert "FeaturesProvider" not in datahub_registry.__all__
        assert "DerivedProvider" in root_registry.__all__
        assert "FeaturesProvider" not in root_registry.__all__

    def test_materialization_orchestrator_has_universe_provider(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedMaterializationOrchestrator should receive UniverseProvider via DI."""
        from ditto_port.services.derived.materialization_orchestrator import (
            DerivedMaterializationOrchestrator,
        )

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

        orchestrator = container.get(DerivedMaterializationOrchestrator)
        assert orchestrator._universe_provider is not None
        container.close()
