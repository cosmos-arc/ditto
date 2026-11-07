"""固定交易日历与真实来源证据验证发布后刷新及截止归属。"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import orjson
import polars as pl
import pytest
from ditto_application.processes.ingestion.published_refresh import (
    PublishedRefreshProcess,
)
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery
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
from ditto_platform.foundation import SQLiteClient, SQLitePool

SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.mark.parametrize(
    ("target", "session"), [("2026-11-06", "2026-11-09"), ("2024-09-30", "2024-10-08")]
)
@pytest.mark.parametrize("late", [False, True])
def test_completed_source_is_on_time_only_before_deadline(
    tmp_path: Path, target: str, session: str, late: bool
) -> None:
    observed = datetime.fromisoformat(
        session + ("T09:16:00" if late else "T08:40:00")
    ).replace(tzinfo=SHANGHAI)
    client = SQLiteClient(SQLitePool(str(tmp_path / "metadata.sqlite")))
    snapshots = SQLiteProviderSnapshotStore(client, now=lambda: observed)
    lifecycle = SQLitePartitionLifecycleStore(client)
    payloads = FilesystemProviderPayloadStore(tmp_path)
    payload = payloads.retain_payload(
        dataset_id="margin_trading",
        source="tushare",
        payload=pl.DataFrame(
            {
                "source_ticker": ["600000.SH", "000001.SZ"],
                "trade_date": [date.fromisoformat(target)] * 2,
                "margin_buy_balance": [100.0, 200.0],
            }
        ),
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="margin_trading",
            source="tushare",
            schema_version="v1",
            request_parameters_hash="recorded",
            checksum=payload.checksum,
            row_count=2,
            request_start=target,
            request_end=target,
            response_metadata=(),
            canonical_asset=DataAssetRef("margin_trading", "capital"),
            payload_uri=payload.uri,
            payload_retained=True,
            created_at=observed,
            schema_fingerprint=payload.schema_fingerprint,
        )
    )
    snapshots.append_snapshot(snapshot)
    lifecycle.plan_partition(
        PartitionCheckpoint(
            chunk_id=snapshot.snapshot_id,
            dataset_id="margin_trading",
            source="tushare",
            request_start=target,
            request_end=target,
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
    lifecycle.advance_partition(
        snapshot.snapshot_id,
        PartitionLifecycleStatus.COMPLETE,
        occurred_at=observed,
        evidence_id=snapshot.snapshot_id,
    )
    calendar = MagicMock()
    calendar.is_trading_day.return_value = True
    calendar.list_trading_days.return_value = [target, session]
    coordinator = MagicMock()
    process = PublishedRefreshProcess(
        coordinator=coordinator,
        calendar=calendar,
        snapshots=snapshots,
        lifecycle=lifecycle,
        audit=ProviderSnapshotQuery(
            SnapshotReadService(snapshots, payloads, lifecycle), MagicMock()
        ),
        evidence_root=tmp_path / "evidence",
        clock=lambda: observed,
    )
    if late:
        with pytest.raises(RuntimeError, match="not ready by"):
            process.margin(scheduled_day=session, finalize=True)
    else:
        assert process.margin(scheduled_day=session, finalize=False)["ready"] is True
    coordinator.ingest_date.assert_not_called()
    report = orjson.loads(
        next((tmp_path / "evidence" / "margin").glob("*.json")).read_bytes()
    )
    assert report["trade_date"] == target
    assert report["on_time"] is not late
    client.conn.close()


def test_pending_refresh_is_one_attempt_and_final_never_fetches(tmp_path: Path) -> None:
    calendar = MagicMock()
    calendar.is_trading_day.return_value = True
    calendar.list_trading_days.return_value = ["2026-11-06", "2026-11-09"]
    snapshots = MagicMock()
    snapshots.list_snapshots.return_value = ()
    lifecycle = MagicMock()
    lifecycle.list_complete.return_value = ()
    coordinator = MagicMock()
    coordinator.ingest_date.return_value.status = "failed"
    coordinator.ingest_date.return_value.error = "recorded fetch failure"
    now = datetime(2026, 11, 9, 8, 35, tzinfo=SHANGHAI)
    process = PublishedRefreshProcess(
        coordinator=coordinator,
        calendar=calendar,
        snapshots=snapshots,
        lifecycle=lifecycle,
        audit=MagicMock(),
        evidence_root=tmp_path,
        clock=lambda: now,
    )
    report = process.margin(scheduled_day="2026-11-09", finalize=False)
    assert report["attempted"] is True
    assert report["ready"] is False
    coordinator.ingest_date.assert_called_once_with(
        "margin_trading", "2026-11-06", force=True
    )
    with pytest.raises(ValueError, match="cannot precede"):
        process.margin(scheduled_day="2026-11-09", finalize=True)
    now = datetime(2026, 11, 9, 9, 15, tzinfo=SHANGHAI)
    with pytest.raises(RuntimeError, match="not ready by"):
        process.margin(scheduled_day="2026-11-09", finalize=True)
    assert coordinator.ingest_date.call_count == 1
    assert len(list((tmp_path / "margin").glob("*.json"))) == 2
    calendar.is_trading_day.return_value = False
    assert (
        process.margin(scheduled_day="2026-11-09", finalize=False)["status"]
        == "not_trading_day"
    )
    assert coordinator.ingest_date.call_count == 1
