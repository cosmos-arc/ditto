"""FRED refresh binds each dataset to its own retained, completed payload."""

from contextlib import nullcontext
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import orjson
import polars as pl
import pytest
from ditto_application.processes.ingestion.published_refresh import (
    PublishedRefreshProcess,
)
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery
from ditto_apps.jobs.flows import repair
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.ingestion.published_refresh_evidence import (
    PublishedRefreshEvidenceStore,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool
from prefect.settings import PREFECT_LOCAL_STORAGE_PATH, temporary_settings


@pytest.mark.usefixtures("prefect_test_session")
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "commodity_missing",
        "wrong_source",
        "incomplete",
        "macro_failed",
        "commodity_failed",
        "commodity_skipped",
        "macro_null",
        "commodity_null",
    ],
)
def test_fred_refresh_requires_both_datasets(
    tmp_path: Path, fault: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    day = "2026-11-07"
    observed = datetime(2026, 11, 7, tzinfo=UTC)
    monkeypatch.setattr(repair, "datetime", SimpleNamespace(now=observed.astimezone))
    client = SQLiteClient(SQLitePool(str(tmp_path / "metadata.sqlite")))
    snapshots = SQLiteProviderSnapshotStore(client, now=lambda: observed)
    lifecycle = SQLitePartitionLifecycleStore(client)
    payloads = FilesystemProviderPayloadStore(tmp_path)
    identities = {}
    for dataset, recorded_frame in (
        (
            "macro_indicators",
            pl.DataFrame(
                {
                    "indicator_code": ["US_GDP_QOQ"],
                    "frequency": ["quarterly"],
                    "date": [date(2026, 7, 1)],
                    "value": [2.5],
                }
            ),
        ),
        (
            "commodity_daily",
            pl.DataFrame(
                {
                    "instrument_id": [5000001, 5000002, 5100001],
                    "trade_date": [
                        date(2026, 11, 5),
                        date(2026, 11, 4),
                        date(2026, 11, 6),
                    ],
                    "close": [60.0, 65.0, 20.0],
                }
            ),
        ),
    ):
        commodity = dataset == "commodity_daily"
        frame = (
            recorded_frame.head(2)
            if commodity and fault == "commodity_missing"
            else recorded_frame
        )
        if fault == ("commodity_null" if commodity else "macro_null"):
            frame = frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("close" if commodity else "value")
            )
        source = "tushare" if commodity and fault == "wrong_source" else "fred"
        payload = payloads.retain_payload(
            dataset_id=dataset, source=source, payload=frame
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset,
                source=source,
                schema_version="v1",
                request_parameters_hash="recorded",
                checksum=payload.checksum,
                row_count=frame.height,
                request_start=day,
                request_end=day,
                response_metadata=(),
                canonical_asset=DataAssetRef(dataset, "market"),
                payload_uri=payload.uri,
                payload_retained=True,
                created_at=observed,
                schema_fingerprint=payload.schema_fingerprint,
            )
        )
        snapshots.append_snapshot(snapshot)
        identities[dataset] = snapshot.snapshot_id
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=snapshot.snapshot_id,
                dataset_id=dataset,
                source=source,
                request_start=day,
                request_end=day,
                status=PartitionLifecycleStatus.PLANNED,
                payload_id=None,
                complete_evidence_id=None,
                error_code=None,
                updated_at=observed,
            )
        )
        lifecycle.advance_partition(
            snapshot.snapshot_id,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            occurred_at=observed,
            evidence_id=f"payload:{snapshot.checksum}:recorded:{snapshot.snapshot_id}",
        )
        if not (commodity and fault == "incomplete"):
            lifecycle.advance_partition(
                snapshot.snapshot_id,
                PartitionLifecycleStatus.COMPLETE,
                occurred_at=observed,
                evidence_id=snapshot.snapshot_id,
            )
    coordinator = MagicMock()

    def ingest(dataset: str, day: str, *, force: bool) -> MagicMock:
        failed = (dataset == "macro_indicators" and fault == "macro_failed") or (
            dataset == "commodity_daily" and fault == "commodity_failed"
        )
        return MagicMock(
            status="skipped"
            if dataset == "commodity_daily" and fault == "commodity_skipped"
            else "failed"
            if failed
            else "success",
            error="recorded source failure",
        )

    coordinator.ingest_date.side_effect = ingest
    process = PublishedRefreshProcess(
        coordinator=coordinator,
        calendar=MagicMock(),
        snapshots=snapshots,
        lifecycle=lifecycle,
        audit=ProviderSnapshotQuery(
            SnapshotReadService(snapshots, payloads, lifecycle), MagicMock()
        ),
        fred_series=("US_GDP_QOQ",),
        evidence=PublishedRefreshEvidenceStore(tmp_path / "evidence"),
    )
    monkeypatch.setattr(
        repair,
        "create_ingestion_bundle",
        lambda **kwargs: nullcontext(SimpleNamespace(published_refresh=process)),
    )
    try:
        with temporary_settings({PREFECT_LOCAL_STORAGE_PATH: tmp_path / "prefect"}):
            state = repair.fred_published_refresh_flow(return_state=True)
        assert state.is_failed() is bool(fault)
        assert state.is_completed() is (fault is None)
        if fault is None:
            report = orjson.loads(orjson.dumps(state.result()))
            assert (
                report["datasets"]["commodity_daily"]["snapshot_id"]
                == identities["commodity_daily"]
            )
            assert (
                report["datasets"]["macro_indicators"]["latest"][0]["latest_date"]
                == "2026-07-01"
            )
        evidence = orjson.loads(
            next((tmp_path / "evidence" / "fred").glob("*.json")).read_bytes()
        )
        assert set(evidence["datasets"]) == {"macro_indicators", "commodity_daily"}
        assert bool(evidence["errors"]) is bool(fault)
        assert coordinator.ingest_date.call_count == 2
    finally:
        client.conn.close()
