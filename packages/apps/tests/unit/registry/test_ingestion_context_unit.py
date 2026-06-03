"""Tests for ingestion registry context wiring."""

from __future__ import annotations

from contextlib import contextmanager
from typing import cast
from unittest.mock import MagicMock

from ditto_application.processes.ingestion.coordinator_factory import (
    CoordinatorServices,
)
from ditto_apps.registry.contexts import ingestion as ingestion_context
from ditto_data.catalog import (
    DataCatalogReader,
    DataCatalogWriter,
    InMemoryDataCatalog,
)
from ditto_data.lineage import DataLineageRecorder, InMemoryDataLineage
from ditto_data.sources.registry import SourceRegistry


class _FakeContainer:
    def __init__(self, services: dict[type[object], object]) -> None:
        self._services = services
        self.closed = False

    def get(self, key: type[object]) -> object:
        return self._services[key]

    def close(self) -> None:
        self.closed = True


def test_create_ingestion_bundle_passes_lineage_recorder(mocker) -> None:
    """Composition root should wire persistent lineage into ingestion coordinator."""
    lineage = InMemoryDataLineage()
    catalog = InMemoryDataCatalog()
    source_registry = SourceRegistry()
    services = {
        ingestion_context.MetadataService: MagicMock(),
        ingestion_context.MarketService: MagicMock(),
        ingestion_context.MarketWriteService: MagicMock(),
        ingestion_context.FundamentalStore: MagicMock(),
        ingestion_context.CapitalStore: MagicMock(),
        ingestion_context.MacroService: MagicMock(),
        ingestion_context.SourceAccessor: MagicMock(),
        ingestion_context.IngestionLogStore: MagicMock(),
        ingestion_context.IngestionCursorStore: MagicMock(),
        ingestion_context.ExchangeTransformers: MagicMock(),
        ingestion_context.CheckDataQualityHandler: MagicMock(),
        ingestion_context.FreezeStore: MagicMock(),
        SourceRegistry: source_registry,
        DataLineageRecorder: lineage,
        DataCatalogReader: catalog,
        DataCatalogWriter: catalog,
    }
    container = _FakeContainer(services)
    coordinator = MagicMock()
    captured_services: dict[str, object] = {}
    captured_kwargs: dict[str, object] = {}

    @contextmanager
    def fake_create_coordinator(*args: object, **kwargs: object):
        captured_services["services"] = args[0]
        captured_kwargs.update(kwargs)
        yield coordinator

    mocker.patch.object(
        ingestion_context,
        "make_app_container",
        return_value=container,
    )
    mocker.patch.object(
        ingestion_context,
        "create_coordinator",
        side_effect=fake_create_coordinator,
    )
    mocker.patch.object(ingestion_context, "BackfillManager", return_value=MagicMock())
    mocker.patch.object(
        ingestion_context,
        "MetadataQueryFacade",
        return_value=MagicMock(),
    )
    retry_manager_cls = mocker.patch.object(
        ingestion_context,
        "RetryManager",
        return_value=MagicMock(),
    )

    with ingestion_context.create_ingestion_bundle(source="tushare") as bundle:
        assert bundle.coordinator is coordinator

    coordinator_services = cast(CoordinatorServices, captured_services["services"])
    assert coordinator_services.source_registry is source_registry
    assert captured_kwargs["lineage_recorder"] is lineage
    assert captured_kwargs["catalog_reader"] is catalog
    assert captured_kwargs["catalog_writer"] is catalog
    assert retry_manager_cls.call_args.kwargs["data_catalog_reader"] is catalog
    assert container.closed
