"""Integration proof for the durable R2 ingestion evidence chain."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
)
from ditto_data.catalog import DataAssetRef, DataCatalogEntry, DataSchemaFingerprint
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.catalog.sqlite_store import SQLiteDataCatalog
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.lineage import LineageEvent, LineageInputRef, LineageOutputRef
from ditto_data.lineage.sqlite_store import SQLiteDataLineage
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_data.storage.runtime.ingestion import IngestionLogReader, IngestionLogWriter
from ditto_platform.foundation import SQLiteClient, SQLitePool


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
            source_snapshot_id=snapshot.snapshot_id,
        ),
        lineage_event=LineageEvent(
            run_id="ingest:tushare:stock_daily:2026-07-17:sha256:payload",
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
            checksum="sha256:payload",
            rows=1,
        ),
    )


@pytest.mark.integration
def test_evidence_chain_persists_and_completed_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    """Persist every evidence port, then prove a completed replay writes nothing."""
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
            license_reader=licenses,
            catalog_writer=catalog,
            lineage_recorder=lineage,
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
        assert catalog.get_asset(request.catalog_entry.asset) == request.catalog_entry
        assert lineage.list_events_for_run(request.lineage_event.run_id) == (
            request.lineage_event,
        )
        saved_log = logs.get_log("stock_daily", "tushare", "2026-07-17")
        assert saved_log is not None
        assert saved_log.attempts == 1
    finally:
        pool.close()
