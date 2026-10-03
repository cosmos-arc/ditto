"""Shared provider-snapshot/lifecycle evidence fixtures for #394 unit tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import SQLiteClient, SQLitePool


class _MutableClock:
    """Fixture clock; commit_snapshot pins it to each observation time."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class EvidenceStores:
    """SQLite-backed durable facts: snapshots, lifecycle and ingestion logs."""

    snapshots: SQLiteProviderSnapshotStore
    lifecycle: SQLitePartitionLifecycleStore
    logs: _MemoryIngestionLogs
    clock: _MutableClock
    pool: SQLitePool


class _MemoryIngestionLogs:
    """Minimal ingestion log store double used by evidence fixtures."""

    def __init__(self) -> None:
        self._logs: dict[tuple[str, str, str], IngestionLog] = {}

    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        return self._logs.get((dataset, source, trade_date))

    def list_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
        status: IngestionStatus | None = None,
    ) -> list[str]:
        return sorted(
            trade_date
            for key, log in self._logs.items()
            if key[:2] == (dataset, source) and (status is None or log.status is status)
            for trade_date in (key[2],)
        )

    def save_log(self, log: IngestionLog) -> IngestionLog:
        self._logs[(log.dataset, log.source, log.trade_date)] = log
        return log


@contextmanager
def evidence_stores() -> Iterator[EvidenceStores]:
    """Isolated SQLite evidence stores; nothing persists beyond the context."""
    directory = TemporaryDirectory(prefix="ditto-evidence-unit-")
    pool = SQLitePool(str(Path(directory.name) / "evidence.sqlite"))
    client = SQLiteClient(pool)
    clock = _MutableClock()
    try:
        yield EvidenceStores(
            snapshots=SQLiteProviderSnapshotStore(client, now=clock),
            lifecycle=SQLitePartitionLifecycleStore(client),
            logs=_MemoryIngestionLogs(),
            clock=clock,
            pool=pool,
        )
    finally:
        pool.close_all()
        directory.cleanup()


def commit_snapshot(
    stores: EvidenceStores,
    *,
    dataset: str,
    source: str = "tushare",
    request_start: str,
    request_end: str,
    checksum: str,
    row_count: int,
    schema_version: str,
    namespace: str = "market",
    observed_at: datetime | None = None,
    payload_retained: bool = True,
    source_ticker: str | None = None,
    complete: bool = True,
) -> ProviderSnapshot:
    """Append one snapshot and drive its lifecycle to COMPLETE (or stop short)."""
    observed = observed_at or datetime(2026, 7, 1, 9, tzinfo=UTC)
    stores.clock.now = observed
    metadata = (
        ("snapshot_layer", "normalized_provider_payload"),
        ("canonical_checksum", checksum),
        ("canonical_row_count", str(row_count)),
    )
    if source_ticker is not None:
        metadata = (*metadata, ("source_ticker", source_ticker))
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset,
            source=source,
            request_start=request_start,
            request_end=request_end,
            schema_version=schema_version,
            checksum=checksum,
            canonical_asset=DataAssetRef(dataset_id=dataset, namespace=namespace),
            request_parameters_hash=f"request:{dataset}:{source}:{request_start}:{request_end}:{source_ticker}",
            response_metadata=tuple(sorted(metadata)),
            row_count=row_count,
            payload_uri=(
                f"provider_payloads/{source}/{dataset}/{checksum}.parquet"
                if payload_retained
                else None
            ),
            payload_retained=payload_retained,
            created_at=observed,
        )
    )
    stores.snapshots.append_snapshot(snapshot)
    # The observation ledger is attached on read; return the durable form.
    persisted = stores.snapshots.get_snapshot(snapshot.snapshot_id)
    chunk = f"unit:{dataset}:{source}:{request_start}:{request_end}:{checksum}"
    if stores.lifecycle.get_checkpoint(chunk) is not None:
        assert persisted is not None
        return persisted
    stores.lifecycle.plan_partition(
        PartitionCheckpoint(
            chunk_id=chunk,
            dataset_id=dataset,
            source=source,
            request_start=request_start,
            request_end=request_end,
            status=PartitionLifecycleStatus.PLANNED,
            last_successful_stage=None,
            attempt=1,
            retry_budget=3,
            payload_id=None,
            complete_evidence_id=None,
            error_code=None,
            updated_at=observed,
        )
    )
    stages = (
        PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        *((PartitionLifecycleStatus.COMPLETE,) if complete else ()),
    )
    for stage in stages:
        stores.lifecycle.advance_partition(
            chunk,
            stage,
            occurred_at=observed,
            evidence_id=(
                f"payload:{checksum}:{chunk}:{snapshot.snapshot_id}"
                if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                else snapshot.snapshot_id
            ),
        )
    return persisted if persisted is not None else snapshot


def record_success(
    stores: EvidenceStores,
    *,
    dataset: str,
    source: str = "tushare",
    trade_date: str,
    checksum: str,
    rows: int,
) -> IngestionLog:
    log = IngestionLog(
        dataset=dataset,
        source=source,
        trade_date=trade_date,
        status=IngestionStatus.SUCCESS,
        checksum=checksum,
        rows=rows,
    )
    stores.logs.save_log(log)
    return log
