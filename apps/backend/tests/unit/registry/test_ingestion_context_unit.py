"""Tests for ingestion registry context wiring."""

from __future__ import annotations

from contextlib import contextmanager
from typing import cast
from unittest.mock import MagicMock

from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_application.processes.ingestion.coordinator_factory import (
    CoordinatorRuntimeContext,
    CoordinatorServices,
)
from ditto_application.queries.data_products import DataProductsQueryFacade
from ditto_apps.registry.contexts import ingestion as ingestion_context
from ditto_data.catalog import (
    DataCatalogReader,
    DataCatalogWriter,
    InMemoryDataCatalog,
)
from ditto_data.catalog.fallback_policy import CatalogSourceFallbackPolicyReader
from ditto_data.catalog.provider_payload import ProviderPayloadWriter
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
    source_fallback_policy_reader = MagicMock()
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
        CatalogSourceFallbackPolicyReader: source_fallback_policy_reader,
        ProviderPayloadWriter: MagicMock(),
        BootstrapPlanner: MagicMock(),
        DataProductsQueryFacade: MagicMock(),
        DataProductCertificationCommands: MagicMock(),
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
    reattestation = MagicMock()
    reattestation_cls = mocker.patch.object(
        ingestion_context,
        "SparsePITReattestationProcess",
        create=True,
        return_value=reattestation,
    )

    with ingestion_context.create_ingestion_bundle(source="tushare") as bundle:
        assert bundle.coordinator is coordinator
        assert bundle.sparse_pit_reattestation is reattestation

    coordinator_services = cast(CoordinatorServices, captured_services["services"])
    assert coordinator_services.source_registry is source_registry
    runtime = cast(CoordinatorRuntimeContext, captured_kwargs["runtime"])
    assert runtime.lineage_recorder is lineage
    assert runtime.catalog_reader is catalog
    assert runtime.catalog_writer is catalog
    assert runtime.source_fallback_policy_reader is source_fallback_policy_reader
    assert retry_manager_cls.call_args.kwargs["data_catalog_reader"] is catalog
    assert reattestation_cls.call_args.kwargs["ingestion"] is coordinator
    assert reattestation_cls.call_args.kwargs["catalog"] is catalog
    verifier = reattestation_cls.call_args.kwargs["verifier"]
    assert verifier.reader is catalog
    assert verifier.ingestion_logs is services[ingestion_context.IngestionLogStore]
    assert container.closed
