"""Durable R2 ingestion partition lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
    PartitionLifecycleWriter,
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


class TestSQLitePartitionLifecycleStore:
    def test_records_complete_happy_path_in_order(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()
        snapshot_id = "snapshot:tushare:stock_daily:sha256:abc"
        stages = (
            (
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                f"payload:sha256:abc:stock_daily/2026/06:{snapshot_id}",
            ),
            (PartitionLifecycleStatus.COMPLETE, snapshot_id),
        )

        try:
            store.plan_partition(planned)
            for offset, (stage, evidence_id) in enumerate(stages, start=1):
                store.advance_partition(
                    planned.chunk_id,
                    stage,
                    occurred_at=planned.updated_at + timedelta(minutes=offset),
                    evidence_id=evidence_id,
                )

            current = store.get_checkpoint(planned.chunk_id)
            assert current is not None
            assert current.status is PartitionLifecycleStatus.COMPLETE
            assert (
                current.payload_id
                == f"payload:sha256:abc:stock_daily/2026/06:{snapshot_id}"
            )
            assert current.complete_evidence_id == snapshot_id
            assert len(store.list_events(planned.chunk_id)) == 3
            assert store.list_incomplete(dataset_id="stock_daily") == ()
        finally:
            pool.close()

    def test_rejects_skipping_required_stage(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()

        try:
            store.plan_partition(planned)

            with pytest.raises(ValueError, match="invalid partition transition"):
                store.advance_partition(
                    planned.chunk_id,
                    PartitionLifecycleStatus.COMPLETE,
                    occurred_at=planned.updated_at + timedelta(minutes=1),
                    evidence_id="snapshot:tushare:stock_daily:sha256:unexpected",
                )
        finally:
            pool.close()

    def test_complete_requires_evidence(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()

        try:
            store.plan_partition(planned)
            store.advance_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                occurred_at=planned.updated_at,
                evidence_id="payload:sha256:abc:stock_daily/2026/06:snapshot-1",
            )

            with pytest.raises(ValueError, match="requires evidence_id"):
                store.advance_partition(
                    planned.chunk_id,
                    PartitionLifecycleStatus.COMPLETE,
                    occurred_at=planned.updated_at + timedelta(minutes=1),
                )
        finally:
            pool.close()

    def test_error_recorded_on_stage_without_transition(
        self,
        tmp_path: Path,
    ) -> None:
        """#447: 失败不落独立态——阶段不动、error_code 记录、成功推进清空."""
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()
        snapshot_id = "snapshot:tushare:stock_daily:sha256:abc"

        try:
            store.plan_partition(planned)
            store.advance_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                occurred_at=planned.updated_at,
                evidence_id=f"payload:sha256:abc:stock_daily/2026/06:{snapshot_id}",
            )

            failed = store.record_partition_error(
                planned.chunk_id,
                error_code="SNAPSHOT_WRITE_FAILED",
                occurred_at=planned.updated_at + timedelta(minutes=1),
            )
            assert failed.status is PartitionLifecycleStatus.PAYLOAD_COMMITTED
            assert failed.error_code == "SNAPSHOT_WRITE_FAILED"
            # 无状态转换事件：仍只有 plan+payload 两条
            assert len(store.list_events(planned.chunk_id)) == 2

            # 重跑：同证据幂等推进到 COMPLETE，并清空 error_code
            completed = store.advance_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.COMPLETE,
                occurred_at=planned.updated_at + timedelta(minutes=2),
                evidence_id=snapshot_id,
            )
            assert completed.status is PartitionLifecycleStatus.COMPLETE
            assert completed.error_code is None

            with pytest.raises(ValueError, match="complete partition is immutable"):
                store.record_partition_error(
                    planned.chunk_id,
                    error_code="LATE_FAILURE",
                    occurred_at=planned.updated_at + timedelta(minutes=3),
                )
        finally:
            pool.close()

    def test_duplicate_advance_is_idempotent(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()
        occurred_at = planned.updated_at + timedelta(minutes=1)

        try:
            store.plan_partition(planned)
            store.advance_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                occurred_at=occurred_at,
                evidence_id="payload:sha256:abc:uri:snapshot-1",
            )
            store.advance_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                occurred_at=occurred_at,
                evidence_id="payload:sha256:abc:uri:snapshot-1",
            )

            assert len(store.list_events(planned.chunk_id)) == 2
        finally:
            pool.close()

    def test_persists_and_implements_ports(self, tmp_path: Path) -> None:
        db_path = tmp_path / "runtime.sqlite"
        planned = _planned()
        writer_client, writer_pool = _client(db_path)
        try:
            SQLitePartitionLifecycleStore(writer_client).plan_partition(planned)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            store = SQLitePartitionLifecycleStore(reader_client)
            assert store.get_checkpoint(planned.chunk_id) == planned
            assert store.list_incomplete(dataset_id="stock_daily") == (planned,)
            assert isinstance(store, PartitionLifecycleReader)
            assert isinstance(store, PartitionLifecycleWriter)
        finally:
            reader_pool.close()
