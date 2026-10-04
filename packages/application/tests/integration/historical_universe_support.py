"""Recorded synthetic universe evidence in real SQLite and retained Parquet."""

from contextlib import contextmanager
from datetime import UTC, date, datetime

import polars as pl
from ditto_application.queries.historical_universe import HistoricalUniverseSources
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    schema_fingerprint,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore

VISIBLE = datetime(2026, 1, 1, tzinfo=UTC)
START = date(2026, 1, 1)
END = date(2026, 12, 31)


def retain_history(
    client,
    root,
    dataset_id,
    frame,
    *,
    complete=True,
    observed=VISIBLE,
    source="recorded",
):
    payload = FilesystemProviderPayloadStore(root).retain_payload(
        dataset_id=dataset_id,
        source=source,
        payload=frame,
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source=source,
            request_start=START.isoformat(),
            request_end=END.isoformat(),
            schema_version=f"{dataset_id}.history.v1",
            checksum=payload.checksum,
            canonical_asset=DataAssetRef(dataset_id, "metadata"),
            request_parameters_hash="recorded",
            response_metadata=(),
            row_count=frame.height,
            payload_uri=payload.uri,
            payload_retained=True,
            created_at=VISIBLE,
            schema_fingerprint=schema_fingerprint(frame),
        )
    )
    SQLiteProviderSnapshotStore(client, now=lambda: observed).append_snapshot(snapshot)
    lifecycle = SQLitePartitionLifecycleStore(client)
    chunk = snapshot.snapshot_id
    if lifecycle.get_checkpoint(chunk) is None:
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=chunk,
                dataset_id=dataset_id,
                source=source,
                request_start=START.isoformat(),
                request_end=END.isoformat(),
                status=PartitionLifecycleStatus.PLANNED,
                payload_id=None,
                complete_evidence_id=None,
                error_code=None,
                updated_at=VISIBLE,
            )
        )
        for stage in (
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            *((PartitionLifecycleStatus.COMPLETE,) if complete else ()),
        ):
            lifecycle.advance_partition(
                chunk,
                stage,
                occurred_at=VISIBLE,
                evidence_id=(
                    f"payload:{snapshot.checksum}:synthetic:{chunk}"
                    if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                    else chunk
                ),
            )
    return snapshot


def history_frames(ids=(1,), *, asset_kind="stock"):
    common = {
        "instrument_id": list(ids),
        "effective_from": [date(2020, 1, 1)] * len(ids),
        "effective_to": [None] * len(ids),
        "available_at": [VISIBLE] * len(ids),
        "publication_at": [VISIBLE] * len(ids),
    }
    master = pl.DataFrame(
        {
            **common,
            "list_date": [date(2020, 1, 1)] * len(ids),
            "delist_date": [None] * len(ids),
        },
        schema_overrides={"effective_to": pl.Date, "delist_date": pl.Date},
    )
    if asset_kind == "etf":
        master = master.with_columns(pl.lit("csi300").alias("tracking_index"))
    status = pl.DataFrame(
        {**common, "is_suspended": [False] * len(ids)},
        schema_overrides={"effective_to": pl.Date},
    )
    return master, status


def seed_history(
    client,
    root,
    *,
    asset_kind="stock",
    ids=(1,),
    universe_id="universe.cn.all",
    delist_on=None,
    source="recorded",
):
    master, status = history_frames(ids, asset_kind=asset_kind)
    if delist_on is not None:
        master = master.with_columns(pl.lit(delist_on).alias("delist_date"))
    primary = retain_history(client, root, f"{asset_kind}_basic", master, source=source)
    trading = retain_history(
        client,
        root,
        "stock_status" if asset_kind == "stock" else "etf_daily",
        status,
        source=source,
    )
    return HistoricalUniverseSources(
        universe_id,
        asset_kind,
        (primary.snapshot_id,),
        (trading.snapshot_id,),
    )


@contextmanager
def selection_history(request, *, delist_on=None):
    """Provide a real historical pool matching the declared synthetic instruments."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from ditto_application.processes.selection.facade import EtfSelectionSpecDraft
    from ditto_application.queries.historical_universe import HistoricalUniverseQuery
    from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
    from ditto_data.catalog.snapshot_reader import SnapshotReadService
    from ditto_platform.foundation import SQLiteClient, SQLitePool

    with TemporaryDirectory() as directory:
        root = Path(directory)
        pool = SQLitePool(root / "history.sqlite")
        try:
            client = SQLiteClient(pool)
            kind = (
                "etf"
                if isinstance(request.selection_spec, EtfSelectionSpecDraft)
                else "stock"
            )
            sources = seed_history(
                client,
                root,
                asset_kind=kind,
                delist_on=delist_on,
                ids=tuple(int(x.instrument_id) for x in request.instruments),
            )
            snapshots = SQLiteProviderSnapshotStore(client)
            lifecycle = SQLitePartitionLifecycleStore(client)
            query = HistoricalUniverseQuery(
                SnapshotReadService(
                    snapshots, FilesystemProviderPayloadStore(root), lifecycle
                ),
                SnapshotReadinessQuery(snapshots, lifecycle),
            )
            result = query.resolve(
                sources,
                as_of=request.as_of.date(),
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.publication_cutoff,
            )
            yield query, sources, result.snapshot_id
        finally:
            pool.close_all()
