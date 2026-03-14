"""Tests for RuntimeProvider derived catalog wiring."""

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_datahub.services import DerivedCatalogService
from ditto_datahub.sources.source import DataSources
from ditto_port.registry.datahub import RuntimeProvider
from ditto_port.registry.infra import ConfigProvider


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

    return SourcesProvider()


class TestRuntimeProviderDerivedCatalog:
    """Tests for RuntimeProvider derived catalog service wiring."""

    def test_runtime_provider_provides_derived_catalog_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider should build DerivedCatalogService."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(DerivedCatalogService)

        assert isinstance(service, DerivedCatalogService)
        container.close()

    def test_runtime_provider_reuses_derived_catalog_service_singleton(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedCatalogService should be an app-scoped singleton."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service_1 = container.get(DerivedCatalogService)
        service_2 = container.get(DerivedCatalogService)

        assert service_1 is service_2
        container.close()
