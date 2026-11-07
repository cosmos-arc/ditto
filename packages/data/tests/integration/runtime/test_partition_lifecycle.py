"""Real SQLite revision precedence for unfinished ingestion requests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _planned() -> PartitionCheckpoint:
    return PartitionCheckpoint(
        chunk_id="chunk:tushare:stock_daily:2026-06",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-06-01",
        request_end="2026-06-30",
        status=PartitionLifecycleStatus.PLANNED,
        payload_id=None,
        complete_evidence_id=None,
        error_code=None,
        updated_at=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
    )


@pytest.mark.integration
def test_incomplete_uses_latest_event_not_clock_or_revision_name(
    tmp_path: Path,
) -> None:
    client, pool = _client(tmp_path / "runtime.sqlite")
    store = SQLitePartitionLifecycleStore(client)
    base = _planned()
    revision = replace(
        base,
        chunk_id=base.chunk_id + ":revision:retry",
        updated_at=base.updated_at - timedelta(days=1),
    )
    try:
        store.plan_partition(base)
        store.plan_partition(revision)
        assert store.list_incomplete(dataset_id="stock_daily", source="tushare") == (
            revision,
        )
        assert store.list_incomplete(source="fred") == ()
        # Event order wins over wall-clock and revision-name order.
        payload = store.advance_partition(
            base.chunk_id,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            occurred_at=base.updated_at - timedelta(days=2),
            evidence_id="payload:old",
        )
        assert store.get_latest_checkpoint(base.chunk_id) == payload
        assert store.list_incomplete() == (payload,)
        store.advance_partition(
            base.chunk_id,
            PartitionLifecycleStatus.COMPLETE,
            occurred_at=base.updated_at - timedelta(days=2),
            evidence_id="snapshot:old",
        )
        assert store.list_incomplete() == ()
    finally:
        pool.close()
