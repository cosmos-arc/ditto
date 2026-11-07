"""Historical acceptance must validate catalog identity before reading payloads."""

from __future__ import annotations

import runpy
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation.db.sqlite_pool import SQLitePool
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient


@pytest.mark.parametrize("invalid_identity", [False, True])
def test_retained_stock_source_requires_identity_and_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_identity: bool
) -> None:
    script = (
        Path(__file__).resolve().parents[5]
        / "docs/evidence/stock-paper-20261021/stock_paper_journey.py"
    )
    load_market = runpy.run_path(str(script))["load_market"]
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-10-21",
            request_end="2026-10-21",
            schema_version="market.stock_daily.v1",
            checksum="a" * 32,
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="b" * 32,
            response_metadata=(),
            row_count=1,
            payload_uri="provider_payloads/tushare/stock_daily/must-not-read.parquet",
            payload_retained=True,
            created_at=datetime(2026, 10, 22, tzinfo=UTC),
        )
    )
    metadata = tmp_path / "metadata/metadata.sqlite"
    metadata.parent.mkdir()
    with closing(SQLiteClient(SQLitePool(str(metadata)))) as client:
        snapshots = SQLiteProviderSnapshotStore(client)
        SQLitePartitionLifecycleStore(client)
        snapshots.append_snapshot(snapshot)
        client.execute(
            "CREATE TABLE instrument "
            "(instrument_id INTEGER, ticker TEXT, exchange TEXT)"
        )
        client.execute("INSERT INTO instrument VALUES (1001032, '600825', 'SSE')")
        if invalid_identity:
            client.execute("UPDATE provider_snapshots SET request_end='2026-10-22'")
        client.commit()
    for constant in ("SNAPSHOT_STOCK_DAILY", "SNAPSHOT_STOCK_LIMIT"):
        monkeypatch.setitem(load_market.__globals__, constant, snapshot.snapshot_id)
    expected = "invalid identity" if invalid_identity else "no COMPLETE checkpoint"
    with pytest.raises(ValueError, match=expected):
        load_market(tmp_path)
