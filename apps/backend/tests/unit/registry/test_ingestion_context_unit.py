"""Tests for ingestion registry context wiring."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_apps.registry.contexts import ingestion as ingestion_context
from ditto_data.catalog import (
    DataCatalogReader,
    DataCatalogWriter,
    InMemoryDataCatalog,
)
from ditto_data.catalog.provider_payload import ProviderPayloadWriter
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.sources.registry import SourceRegistry


class _FakeContainer:
    def __init__(self, services: dict[type[object], object]) -> None:
        self._services = services
        self.closed = False

    def get(self, key: type[object]) -> object:
        return self._services[key]

    def close(self) -> None:
        self.closed = True


def test_create_ingestion_bundle_wires_runtime_ports(mocker) -> None:
    """Composition root should wire catalog/snapshot/lifecycle ports into evidence."""
    catalog = InMemoryDataCatalog()
    snapshots = MagicMock(spec=ProviderSnapshotReader)
    lifecycle = MagicMock(spec=PartitionLifecycleReader)
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
        ingestion_context.EtfReferenceConfigSource: MagicMock(),
        SourceRegistry: source_registry,
        DataCatalogReader: catalog,
        DataCatalogWriter: catalog,
        ProviderPayloadWriter: MagicMock(),
        ProviderSnapshotReader: snapshots,
        PartitionLifecycleReader: lifecycle,
        BootstrapPlanner: MagicMock(),
        ingestion_context.IngestionEvidenceCommitter: MagicMock(),
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

    coordinator_services = captured_services["services"]
    assert isinstance(coordinator_services, ingestion_context.CoordinatorServices)
    assert coordinator_services.source_registry is source_registry
    runtime = captured_kwargs["runtime"]
    assert isinstance(runtime, ingestion_context.CoordinatorRuntimeContext)
    assert runtime.catalog_reader is catalog
    assert runtime.catalog_writer is catalog
    # #394:证据 saga 恒开启,完成事实端口随协调器下发。
    assert (
        runtime.evidence_committer
        is services[ingestion_context.IngestionEvidenceCommitter]
    )
    assert runtime.snapshot_reader is snapshots
    assert runtime.lifecycle_reader is lifecycle
    assert "data_catalog_reader" not in retry_manager_cls.call_args.kwargs
    assert reattestation_cls.call_args.kwargs["ingestion"] is coordinator
    assert reattestation_cls.call_args.kwargs["snapshots"] is snapshots
    assert reattestation_cls.call_args.kwargs["lifecycle"] is lifecycle
    verifier = reattestation_cls.call_args.kwargs["verifier"]
    assert verifier.snapshots is snapshots
    assert verifier.lifecycle is lifecycle
    assert verifier.ingestion_logs is services[ingestion_context.IngestionLogStore]
    assert container.closed
