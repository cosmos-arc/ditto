"""Integration proof for the durable R2 ingestion evidence chain."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_application.processes.ingestion.bootstrap_planner import BootstrapPlanner
from ditto_application.processes.ingestion.config import IngestionCoordinatorConfig
from ditto_application.processes.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionServices,
    MarketServices,
)
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.post_ingest import (
    PostIngestContext,
    RequestWindow,
    process_fetched_data,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.catalog import DataAssetRef, DataCatalogEntry, DataSchemaFingerprint
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    ProviderPayloadArtifact,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.catalog.sqlite_store import SQLiteDataCatalog
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.lineage import LineageEvent, LineageInputRef, LineageOutputRef
from ditto_data.lineage.sqlite_store import SQLiteDataLineage
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_data.observability.metrics import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import MarketWriters
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_data.storage.market.etf.bars import EtfBarsWriter
from ditto_data.storage.market.etf.status import EtfStatusWriter
from ditto_data.storage.market.stock.adj import StockAdjFactorWriter
from ditto_data.storage.market.stock.bars import StockBarsWriter
from ditto_data.storage.market.stock.status import StockStatusWriter
from ditto_data.storage.runtime.ingestion import IngestionLogReader, IngestionLogWriter
from ditto_platform.foundation import (
    FileLockManager,
    ParquetStore,
    SQLiteClient,
    SQLitePool,
)
from ditto_platform.foundation.storage import parquet_store


def _license() -> DatasetLicenseRecord:
    return DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="stock_daily",
            source="tushare",
            terms_version="fixture-v1",
            effective_from=date(2020, 1, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="restricted",
            redistribution="prohibited",
            notes="Integration fixture review only.",
            reviewed_by="test-reviewer",
            reviewed_at=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
        )
    )


def _request(license_record: DatasetLicenseRecord) -> EvidenceCommitRequest:
    now = datetime(2026, 7, 18, 8, 30, tzinfo=UTC)
    asset = DataAssetRef(
        dataset_id="stock_daily",
        namespace="market",
        partition_keys=("trade_date=2026-07-17",),
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-07-17",
            request_end="2026-07-17",
            schema_version="market.stock_daily.v1",
            checksum="sha256:payload",
            canonical_asset=asset,
            request_parameters_hash="sha256:request",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id=license_record.record_id,
            row_count=1,
            payload_uri="stock_daily/2026/07/17.parquet",
            payload_retained=True,
            created_at=now,
        )
    )
    return EvidenceCommitRequest(
        chunk_id="chunk:tushare:stock_daily:2026-07-17",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-07-17",
        request_end="2026-07-17",
        provider_snapshot=snapshot,
        catalog_entry=DataCatalogEntry(
            asset=asset,
            storage_uri="stock_daily/2026/07/17.parquet",
            schema=DataSchemaFingerprint(
                schema_hash="schema:sha256:stock-daily",
                row_count=1,
                created_at=now,
                schema_version="market.stock_daily.v1",
                columns=("instrument_id", "trade_date", "close"),
            ),
            source="tushare",
            freshness_at=now,
            source_snapshot_id=(
                "snapshot:tushare:stock_daily:2026-07-17:sha256:canonical:quality=l1-l2"
            ),
        ),
        lineage_event=LineageEvent(
            run_id="ingest:tushare:stock_daily:2026-07-17:sha256:canonical",
            operation="ingest",
            inputs=(
                LineageInputRef(
                    DataAssetRef(
                        dataset_id="stock_daily",
                        namespace="source",
                        partition_keys=(
                            "source=tushare",
                            "trade_date=2026-07-17",
                        ),
                    ),
                    role="source",
                ),
            ),
            outputs=(LineageOutputRef(asset, role="dataset"),),
            timestamp=now,
        ),
        success_log=IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-17",
            status=IngestionStatus.SUCCESS,
            checksum="sha256:canonical",
            rows=1,
        ),
    )


@pytest.mark.integration
def test_evidence_chain_persists_and_completed_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    """Persist every evidence port, then prove a completed replay writes nothing."""
    register_metrics()
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    client = SQLiteClient(pool)
    lifecycle = SQLitePartitionLifecycleStore(client)
    licenses = SQLiteDatasetLicenseStore(client)
    snapshots = SQLiteProviderSnapshotStore(client)
    catalog = SQLiteDataCatalog(client)
    lineage = SQLiteDataLineage(client)
    logs = IngestionLogStore(IngestionLogReader(client), IngestionLogWriter(client))
    license_record = _license()
    licenses.append_license(license_record)
    request = _request(license_record)
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshots,
            snapshot_reader=snapshots,
            license_reader=licenses,
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        ),
        now=lambda: datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )

    try:
        first = committer.commit(request)
        event_count_after_first = len(lifecycle.list_events(request.chunk_id))
        second = committer.commit(request)

        assert first.completed is True
        assert second.completed is True
        checkpoint = lifecycle.get_checkpoint(request.chunk_id)
        assert checkpoint is not None
        assert checkpoint.status is PartitionLifecycleStatus.COMPLETE
        assert len(lifecycle.list_events(request.chunk_id)) == event_count_after_first
        assert (
            snapshots.get_snapshot(request.provider_snapshot.snapshot_id)
            == request.provider_snapshot
        )
        observed_again = request.provider_snapshot.created_at.replace(hour=10)
        replay = replace(
            request,
            provider_snapshot=replace(
                request.provider_snapshot, created_at=observed_again
            ),
        )
        assert committer.commit(replay).completed
        stored = snapshots.get_snapshot(request.provider_snapshot.snapshot_id)
        assert stored is not None
        assert stored.observations == (observed_again,)
        assert catalog.get_asset(request.catalog_entry.asset) == request.catalog_entry
        assert lineage.list_events_for_run(request.lineage_event.run_id) == (
            request.lineage_event,
        )
        saved_log = logs.get_log("stock_daily", "tushare", "2026-07-17")
        assert saved_log is not None
        assert saved_log.attempts == 1
        IngestionResultHandler(logs, "tushare").handle_unknown_error(
            "stock_daily", "2026-07-17", ValueError("rejected conflicting retry")
        )
        assert committer.commit(request).completed
        restored = logs.get_log("stock_daily", "tushare", "2026-07-17")
        assert restored is not None
        assert restored.status is IngestionStatus.SUCCESS
    finally:
        pool.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "failed_stage",
    [
        PartitionLifecycleStatus.CATALOG_ATTESTED,
        PartitionLifecycleStatus.LINEAGE_RECORDED,
        PartitionLifecycleStatus.SUCCESS_RECORDED,
        PartitionLifecycleStatus.COMPLETE,
    ],
)
def test_retry_after_evidence_write_before_checkpoint_does_not_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: PartitionLifecycleStatus,
) -> None:

    register_metrics()
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    client = SQLiteClient(pool)
    lifecycle = SQLitePartitionLifecycleStore(client)
    licenses = SQLiteDatasetLicenseStore(client)
    snapshots = SQLiteProviderSnapshotStore(client)
    catalog = SQLiteDataCatalog(client)
    lineage = SQLiteDataLineage(client)
    logs = IngestionLogStore(IngestionLogReader(client), IngestionLogWriter(client))
    license_record = _license()
    licenses.append_license(license_record)
    request = _request(license_record)
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshots,
            snapshot_reader=snapshots,
            license_reader=licenses,
            catalog_writer=catalog,
            lineage_recorder=lineage,
            lineage_reader=lineage,
            ingestion_log_store=logs,
        )
    )
    advance = lifecycle.advance_partition
    should_fail = True

    def fail_once(
        chunk_id: str,
        to_status: PartitionLifecycleStatus,
        *,
        occurred_at: datetime,
        evidence_id: str | None = None,
    ):
        nonlocal should_fail
        if should_fail and to_status is failed_stage:
            should_fail = False
            raise OSError("injected checkpoint persistence failure")
        return advance(
            chunk_id, to_status, occurred_at=occurred_at, evidence_id=evidence_id
        )

    monkeypatch.setattr(lifecycle, "advance_partition", fail_once)
    try:
        assert not committer.commit(request).completed
        retry = replace(
            request,
            provider_snapshot=replace(
                request.provider_snapshot, created_at=datetime(2026, 7, 19, tzinfo=UTC)
            ),
        )
        assert committer.commit(retry).completed
        assert len(snapshots.list_snapshots()) == 1
        assert len(lineage.list_events_for_run(request.lineage_event.run_id)) == 1
        log = logs.get_log("stock_daily", "tushare", "2026-07-17")
        assert log is not None
        assert log.attempts == 1
        events = lifecycle.list_events(request.chunk_id)
        assert committer.commit(retry).completed
        assert lifecycle.list_events(request.chunk_id) == events
    finally:
        pool.close()


@dataclass(frozen=True)
class _Pipeline:
    context: PostIngestContext
    writer: IngestionDataWriter
    store: ParquetStore
    market: MarketWriteService
    ports: EvidenceCommitPorts


@contextmanager
def _pipeline(
    tmp_path: Path,
    dataset: str,
    *,
    display: Literal["allowed", "restricted"] = "restricted",
    snapshot_now: Callable[[], datetime] | None = None,
) -> Iterator[_Pipeline]:
    class QualityChecker:
        def handle(self, command: CheckDataQualityCommand) -> tuple[pl.DataFrame, bool]:
            assert command.df["close"].min() > 0
            return command.df, False

    register_metrics()
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    client = SQLiteClient(pool)
    lifecycle = SQLitePartitionLifecycleStore(client)
    licenses = SQLiteDatasetLicenseStore(client)
    snapshots = SQLiteProviderSnapshotStore(client, now=snapshot_now)
    catalog = SQLiteDataCatalog(client)
    lineage = SQLiteDataLineage(client)
    logs = IngestionLogStore(IngestionLogReader(client), IngestionLogWriter(client))
    license_record = replace(_license(), dataset_id=dataset, display=display)
    licenses.append_license(license_record)
    ports = EvidenceCommitPorts(
        lifecycle_reader=lifecycle,
        lifecycle_writer=lifecycle,
        snapshot_writer=snapshots,
        snapshot_reader=snapshots,
        license_reader=licenses,
        catalog_writer=catalog,
        lineage_recorder=lineage,
        lineage_reader=lineage,
        ingestion_log_store=logs,
    )
    committer = IngestionEvidenceCommitter(ports=ports)
    store = ParquetStore(
        tmp_path, key_columns=("instrument_id", "trade_date"), date_column="trade_date"
    )
    market = MarketWriteService(
        MarketWriters(
            stock_bars=StockBarsWriter(store),
            stock_status=StockStatusWriter(store),
            stock_adj=StockAdjFactorWriter(store),
            etf_bars=EtfBarsWriter(store),
            etf_status=EtfStatusWriter(store),
        ),
        FileLockManager(tmp_path / "locks"),
    )
    writer = IngestionDataWriter(
        metadata_service=cast(MetadataService, None),
        market_write_service=market,
        fundamental_store=cast(FundamentalStore, None),
        capital_store=cast(CapitalStore, None),
        macro_service=cast(MacroService, None),
        source_name="tushare",
    )
    payloads = FilesystemProviderPayloadStore(tmp_path)
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(logs, "tushare"),
        data_writer=writer,
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        catalog_reader=catalog,
        quality_checker=QualityChecker(),
        evidence_committer=committer,
        provider_payload_writer=payloads,
        license_record_id=license_record.record_id,
    )
    try:
        yield _Pipeline(ctx, writer, store, market, ports)
    finally:
        pool.close()


def _bars() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1000001, 1000001],
            "trade_date": [date(2026, 7, 16), date(2026, 7, 17)],
            "close": [10.0, 20.0],
        }
    )


@pytest.mark.integration
@pytest.mark.pit
@pytest.mark.parametrize("dataset", ["stock_daily", "etf_daily"])
def test_partial_backfill_recovery_and_revision_preserve_old_payload(
    tmp_path: Path,
    dataset: str,
) -> None:
    with _pipeline(tmp_path, dataset) as runtime:
        snapshots = runtime.ports.snapshot_reader
        lifecycle = runtime.ports.lifecycle_reader
        logs = runtime.ports.ingestion_log_store
        original = _bars()

        def ingest(frame: pl.DataFrame, force: bool = False):
            return process_fetched_data(
                frame,
                dataset,
                "2026-07-16",
                force,
                ctx=runtime.context,
                request_window=RequestWindow(None, "2026-07-17"),
                chunk_id="test-backfill",
            )

        runtime.writer.write_data(dataset, original.head(1), "2026-07-16")
        recovered = ingest(original)
        assert recovered.status == "success", recovered
        assert recovered.row_count == 2
        first = snapshots.list_snapshots()[0]
        first_events = lifecycle.list_events("test-backfill")
        assert ingest(original).checksum == recovered.checksum
        assert lifecycle.list_events("test-backfill") == first_events
        first_log = logs.get_log(dataset, "tushare", "2026-07-16")
        assert first_log is not None
        assert first_log.attempts == 1
        revised = original.with_columns(pl.lit(999.0).alias("close"))
        assert ingest(revised).status == "failed"
        assert ingest(original).status == "success"
        assert ingest(revised, force=True).status == "success"
        assert len(snapshots.list_snapshots()) == 2
        # Recovering A after an uncertain B intent is also a durable recovery.
        assert len(lifecycle.list_complete()) == 3
        assert lifecycle.list_incomplete() == ()
        reobserved = snapshots.get_snapshot(first.snapshot_id)
        assert reobserved is not None
        # 重观察保留内容与首次可见时间，只推进最后观察时间。
        assert replace(reobserved, observations=first.observations) == first
        assert first.payload_uri is not None
        old = FilesystemProviderPayloadStore(tmp_path).read_payload(
            ProviderPayloadArtifact(
                dataset_id=dataset,
                source="tushare",
                checksum=first.checksum,
                row_count=first.row_count,
                uri=first.payload_uri,
            )
        )
        assert old.equals(original)
        current = runtime.store.read(
            "market/stock/bars" if dataset == "stock_daily" else "market/etf/bars"
        )
        assert current.equals(revised)
        assert ingest(original, force=True).status == "success"
        restored = logs.get_log(dataset, "tushare", "2026-07-16")
        assert restored is not None
        assert restored.checksum == recovered.checksum
        assert len(lifecycle.list_complete()) == 4


class _MarketSource:
    def __init__(self) -> None:
        self.payload = _bars()

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        return self.payload.filter(
            pl.col("trade_date") == date.fromisoformat(trade_date)
        )


def _coordinator(runtime: _Pipeline, source: _MarketSource):
    metadata = cast(
        MetadataService,
        SimpleNamespace(
            list_trading_days=lambda start, end: ["2026-07-16", "2026-07-17"],
        ),
    )
    coordinator = IngestionCoordinator(
        IngestionServices(
            metadata=metadata,
            market=MarketServices(
                query=cast(MarketService, None), write=runtime.market
            ),
            fundamental=cast(FundamentalStore, None),
            capital=cast(CapitalStore, None),
            macro=cast(MacroService, None),
        ),
        fetchers=SourceFetchers(
            metadata=Mock(spec=MetadataFetcher),
            market=Mock(spec=MarketFetcher, fetch_stock_daily=source.fetch_stock_daily),
            fundamental=Mock(spec=FundamentalFetcher),
            capital=Mock(spec=CapitalFetcher),
            macro=Mock(spec=MacroFetcher),
        ),
        config=IngestionCoordinatorConfig(
            ingestion_log_store=cast(
                IngestionLogStore, runtime.ports.ingestion_log_store
            ),
            catalog_reader=runtime.context.catalog_reader,
            quality_checker=runtime.context.quality_checker,
            evidence_committer=runtime.context.evidence_committer,
            provider_payload_writer=runtime.context.provider_payload_writer,
            license_record_id=runtime.context.license_record_id,
        ),
    )
    return coordinator, metadata


@pytest.mark.integration
@pytest.mark.parametrize("failure_boundary", ["catalog_checkpoint", "payload_checksum"])
def test_normal_backfill_resumes_failed_revision_after_original_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_boundary: str,
) -> None:
    with _pipeline(tmp_path, "stock_daily") as runtime:
        source = _MarketSource()
        coordinator, metadata = _coordinator(runtime, source)
        manager = BackfillManager(
            coordinator,
            metadata,
            cast(IngestionLogStore, runtime.ports.ingestion_log_store),
            bootstrap_planner=BootstrapPlanner(
                metadata_service=metadata,
                partition_lifecycle_reader=runtime.ports.lifecycle_reader,
            ),
        )
        initial = manager.backfill_range("stock_daily", "2026-07-16", "2026-07-17")
        assert initial.success_count == 1
        chunk_id = runtime.ports.lifecycle_reader.list_complete()[0].chunk_id
        advance = runtime.ports.lifecycle_writer.advance_partition
        should_fail = True

        def fail_once(
            chunk: str,
            stage: PartitionLifecycleStatus,
            *,
            occurred_at: datetime,
            evidence_id: str | None = None,
        ):
            nonlocal should_fail
            if (
                should_fail
                and failure_boundary == "catalog_checkpoint"
                and stage is PartitionLifecycleStatus.CATALOG_ATTESTED
            ):
                should_fail = False
                raise OSError("injected revision checkpoint failure")
            return advance(
                chunk, stage, occurred_at=occurred_at, evidence_id=evidence_id
            )

        monkeypatch.setattr(
            runtime.ports.lifecycle_writer, "advance_partition", fail_once
        )
        digest = parquet_store.file_md5

        def fail_checksum(path: Path) -> str:
            nonlocal should_fail
            if should_fail and failure_boundary == "payload_checksum":
                should_fail = False
                raise OSError("injected failure after atomic payload write")
            return digest(path)

        monkeypatch.setattr(parquet_store, "file_md5", fail_checksum)
        source.payload = source.payload.with_columns(pl.lit(999.0).alias("close"))
        failed = coordinator.ingest_chunk(
            "stock_daily",
            chunk_id=chunk_id,
            request_start="2026-07-16",
            request_end="2026-07-17",
            partition_dates=("2026-07-16", "2026-07-17"),
            force=True,
        )
        assert failed.status == "failed"
        assert len(runtime.ports.lifecycle_reader.list_incomplete()) == 1
        recovered = manager.backfill_range("stock_daily", "2026-07-16", "2026-07-17")
        assert recovered.success_count == 1
        assert recovered.results[0].row_count == 2
        assert runtime.ports.lifecycle_reader.list_incomplete() == ()
        assert len(runtime.ports.snapshot_reader.list_snapshots()) == 2
        assert (
            manager.backfill_range(
                "stock_daily", "2026-07-16", "2026-07-17"
            ).total_dates
            == 0
        )
