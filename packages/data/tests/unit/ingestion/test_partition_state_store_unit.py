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


def _planned(*, retry_budget: int = 3) -> PartitionCheckpoint:
    return PartitionCheckpoint(
        chunk_id="chunk:tushare:stock_daily:2026-06",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-06-01",
        request_end="2026-06-30",
        status=PartitionLifecycleStatus.PLANNED,
        last_successful_stage=None,
        attempt=1,
        retry_budget=retry_budget,
        payload_id=None,
        catalog_asset_id=None,
        lineage_run_id=None,
        ingestion_log_id=None,
        error_code=None,
        updated_at=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
    )


class TestSQLitePartitionLifecycleStore:
    def test_records_complete_happy_path_in_order(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()
        stages = (
            PartitionLifecycleStatus.FETCHED,
            PartitionLifecycleStatus.NORMALIZED,
            PartitionLifecycleStatus.PIT_PASSED,
            PartitionLifecycleStatus.DQ_PASSED,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            PartitionLifecycleStatus.CATALOG_ATTESTED,
            PartitionLifecycleStatus.LINEAGE_RECORDED,
            PartitionLifecycleStatus.SUCCESS_RECORDED,
            PartitionLifecycleStatus.COMPLETE,
        )

        try:
            store.plan_partition(planned)
            for offset, stage in enumerate(stages, start=1):
                store.advance_partition(
                    planned.chunk_id,
                    stage,
                    occurred_at=planned.updated_at + timedelta(minutes=offset),
                    evidence_id=f"evidence:{stage.value}",
                )

            current = store.get_checkpoint(planned.chunk_id)
            assert current is not None
            assert current.status is PartitionLifecycleStatus.COMPLETE
            assert current.last_successful_stage is PartitionLifecycleStatus.COMPLETE
            assert current.payload_id == "evidence:PAYLOAD_COMMITTED"
            assert current.catalog_asset_id == "evidence:CATALOG_ATTESTED"
            assert current.lineage_run_id == "evidence:LINEAGE_RECORDED"
            assert current.ingestion_log_id == "evidence:SUCCESS_RECORDED"
            assert len(store.list_events(planned.chunk_id)) == 10
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
                    PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                    occurred_at=planned.updated_at + timedelta(minutes=1),
                    evidence_id="payload:unexpected",
                )
        finally:
            pool.close()

    def test_orphan_payload_resumes_after_payload_without_refetch(
        self, tmp_path: Path
    ) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned()

        try:
            store.plan_partition(planned)
            for offset, stage in enumerate(
                (
                    PartitionLifecycleStatus.FETCHED,
                    PartitionLifecycleStatus.NORMALIZED,
                    PartitionLifecycleStatus.PIT_PASSED,
                    PartitionLifecycleStatus.DQ_PASSED,
                    PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                ),
                start=1,
            ):
                store.advance_partition(
                    planned.chunk_id,
                    stage,
                    occurred_at=planned.updated_at + timedelta(minutes=offset),
                    evidence_id=(
                        "payload:sha256:abc"
                        if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                        else None
                    ),
                )
            store.fail_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.ORPHAN_PAYLOAD,
                error_code="CATALOG_ATTESTATION_FAILED",
                occurred_at=planned.updated_at + timedelta(minutes=6),
            )

            failed = store.get_checkpoint(planned.chunk_id)
            assert failed is not None
            assert failed.status is PartitionLifecycleStatus.ORPHAN_PAYLOAD
            assert (
                failed.last_successful_stage
                is PartitionLifecycleStatus.PAYLOAD_COMMITTED
            )
            assert failed.payload_id == "payload:sha256:abc"

            resumed = store.resume_partition(
                planned.chunk_id,
                occurred_at=planned.updated_at + timedelta(minutes=7),
            )
            assert resumed.status is PartitionLifecycleStatus.PAYLOAD_COMMITTED
            assert resumed.attempt == 2
            assert resumed.payload_id == "payload:sha256:abc"
        finally:
            pool.close()

    def test_retry_budget_blocks_additional_resume(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "runtime.sqlite")
        store = SQLitePartitionLifecycleStore(client)
        planned = _planned(retry_budget=1)

        try:
            store.plan_partition(planned)
            store.fail_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.FAILED,
                error_code="FETCH_TIMEOUT",
                occurred_at=planned.updated_at + timedelta(minutes=1),
            )

            with pytest.raises(ValueError, match="retry budget"):
                store.resume_partition(
                    planned.chunk_id,
                    occurred_at=planned.updated_at + timedelta(minutes=2),
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
                PartitionLifecycleStatus.FETCHED,
                occurred_at=occurred_at,
                evidence_id="request:tushare:1",
            )
            store.advance_partition(
                planned.chunk_id,
                PartitionLifecycleStatus.FETCHED,
                occurred_at=occurred_at,
                evidence_id="request:tushare:1",
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
