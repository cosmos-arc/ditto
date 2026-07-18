"""SQLite current-state and append-only events for ingestion partitions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from itertools import pairwise
from typing import Any

from ditto_platform.foundation import SQLiteClient

from ditto_data.ingestion.partition_state import (
    EXCEPTION_PARTITION_STATES,
    NORMAL_PARTITION_STAGES,
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)

__all__ = ["SQLitePartitionLifecycleStore"]

_NEXT_STAGE: dict[PartitionLifecycleStatus, PartitionLifecycleStatus] = dict(
    pairwise(NORMAL_PARTITION_STAGES)
)

_EVIDENCE_FIELD: dict[PartitionLifecycleStatus, str] = {
    PartitionLifecycleStatus.PAYLOAD_COMMITTED: "payload_id",
    PartitionLifecycleStatus.CATALOG_ATTESTED: "catalog_asset_id",
    PartitionLifecycleStatus.LINEAGE_RECORDED: "lineage_run_id",
    PartitionLifecycleStatus.SUCCESS_RECORDED: "ingestion_log_id",
}


class SQLitePartitionLifecycleStore:
    """Durable R2 partition lifecycle and recovery checkpoint store."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_partition_checkpoints (
                chunk_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                source TEXT NOT NULL,
                request_start TEXT NOT NULL,
                request_end TEXT NOT NULL,
                status TEXT NOT NULL,
                last_successful_stage TEXT,
                attempt INTEGER NOT NULL,
                retry_budget INTEGER NOT NULL,
                payload_id TEXT,
                catalog_asset_id TEXT,
                lineage_run_id TEXT,
                ingestion_log_id TEXT,
                error_code TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_partition_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                evidence_id TEXT,
                error_code TEXT,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(chunk_id)
                    REFERENCES ingestion_partition_checkpoints(chunk_id)
            )
            """
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ingestion_partition_repair
            ON ingestion_partition_checkpoints(dataset_id, source, status)
            """
        )
        self._client.commit()

    def plan_partition(self, checkpoint: PartitionCheckpoint) -> None:
        """Create a PLANNED checkpoint and initial audit event."""
        if checkpoint.status is not PartitionLifecycleStatus.PLANNED:
            raise ValueError("new partition checkpoint must start at PLANNED")
        if checkpoint.last_successful_stage is not None:
            raise ValueError("new partition checkpoint cannot have a successful stage")
        existing = self.get_checkpoint(checkpoint.chunk_id)
        if existing is not None:
            if existing == checkpoint:
                return
            raise ValueError(f"partition checkpoint conflict: {checkpoint.chunk_id}")
        try:
            self._insert_checkpoint(checkpoint)
            self._insert_event(
                chunk_id=checkpoint.chunk_id,
                from_status=None,
                to_status=checkpoint.status,
                attempt=checkpoint.attempt,
                evidence_id=None,
                error_code=None,
                occurred_at=checkpoint.updated_at,
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def advance_partition(
        self,
        chunk_id: str,
        to_status: PartitionLifecycleStatus,
        *,
        occurred_at: datetime,
        evidence_id: str | None = None,
    ) -> PartitionCheckpoint:
        """Advance exactly one normal lifecycle stage."""
        current = self._require_checkpoint(chunk_id)
        if current.status is to_status:
            field = _EVIDENCE_FIELD.get(to_status)
            if field is None or getattr(current, field) == evidence_id:
                return current
            raise ValueError("idempotent partition transition evidence mismatch")
        expected = _NEXT_STAGE.get(current.status)
        if expected is not to_status:
            raise ValueError(
                f"invalid partition transition: {current.status} -> {to_status}"
            )
        evidence_field = _EVIDENCE_FIELD.get(to_status)
        if evidence_field is not None and not evidence_id:
            raise ValueError(f"partition stage {to_status} requires evidence_id")
        changes: dict[str, object] = {
            "status": to_status,
            "last_successful_stage": to_status,
            "error_code": None,
            "updated_at": occurred_at,
        }
        if evidence_field is not None:
            changes[evidence_field] = evidence_id
        updated = replace(current, **changes)
        self._persist_transition(
            current=current,
            updated=updated,
            evidence_id=evidence_id,
            error_code=None,
            occurred_at=occurred_at,
        )
        return updated

    def fail_partition(
        self,
        chunk_id: str,
        failure_status: PartitionLifecycleStatus,
        *,
        error_code: str,
        occurred_at: datetime,
    ) -> PartitionCheckpoint:
        """Record one explicit repairable exception state."""
        if failure_status not in EXCEPTION_PARTITION_STATES:
            raise ValueError(f"invalid partition failure state: {failure_status}")
        if not error_code or error_code.strip() != error_code:
            raise ValueError("partition failure requires error_code")
        current = self._require_checkpoint(chunk_id)
        if current.status is PartitionLifecycleStatus.COMPLETE:
            raise ValueError("complete partition is immutable")
        last_stage = (
            current.last_successful_stage
            if current.status in EXCEPTION_PARTITION_STATES
            else current.status
        )
        updated = replace(
            current,
            status=failure_status,
            last_successful_stage=last_stage,
            error_code=error_code,
            updated_at=occurred_at,
        )
        self._persist_transition(
            current=current,
            updated=updated,
            evidence_id=None,
            error_code=error_code,
            occurred_at=occurred_at,
        )
        return updated

    def resume_partition(
        self,
        chunk_id: str,
        *,
        occurred_at: datetime,
    ) -> PartitionCheckpoint:
        """Resume from the last durable normal stage without repeating prior work."""
        current = self._require_checkpoint(chunk_id)
        if current.status not in EXCEPTION_PARTITION_STATES:
            raise ValueError("only failed partition checkpoints can resume")
        if current.attempt >= current.retry_budget:
            raise ValueError("partition retry budget exhausted")
        resume_stage = current.last_successful_stage or PartitionLifecycleStatus.PLANNED
        updated = replace(
            current,
            status=resume_stage,
            attempt=current.attempt + 1,
            error_code=None,
            updated_at=occurred_at,
        )
        self._persist_transition(
            current=current,
            updated=updated,
            evidence_id=None,
            error_code=None,
            occurred_at=occurred_at,
        )
        return updated

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        """Return the current recovery boundary for one chunk."""
        row = self._client.fetchone(
            "SELECT * FROM ingestion_partition_checkpoints WHERE chunk_id = ?",
            [chunk_id],
        )
        return None if row is None else _checkpoint_from_row(row)

    def list_incomplete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        """List every non-COMPLETE chunk eligible for continuation or repair."""
        rows = self._client.fetchall(
            """
            SELECT * FROM ingestion_partition_checkpoints
            WHERE status != ?
              AND (? IS NULL OR dataset_id = ?)
              AND (? IS NULL OR source = ?)
            ORDER BY request_start, request_end, chunk_id
            """,
            [
                PartitionLifecycleStatus.COMPLETE.value,
                dataset_id,
                dataset_id,
                source,
                source,
            ],
        )
        return tuple(_checkpoint_from_row(row) for row in rows)

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        """Return append-only lifecycle events in transition order."""
        rows = self._client.fetchall(
            """
            SELECT * FROM ingestion_partition_events
            WHERE chunk_id = ?
            ORDER BY event_id
            """,
            [chunk_id],
        )
        return tuple(_event_from_row(row) for row in rows)

    def _require_checkpoint(self, chunk_id: str) -> PartitionCheckpoint:
        checkpoint = self.get_checkpoint(chunk_id)
        if checkpoint is None:
            raise ValueError(f"unknown partition checkpoint: {chunk_id}")
        return checkpoint

    def _insert_checkpoint(self, checkpoint: PartitionCheckpoint) -> None:
        self._client.execute(
            """
            INSERT INTO ingestion_partition_checkpoints (
                chunk_id, dataset_id, source, request_start, request_end, status,
                last_successful_stage, attempt, retry_budget, payload_id,
                catalog_asset_id, lineage_run_id, ingestion_log_id, error_code,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _checkpoint_params(checkpoint),
        )

    def _update_checkpoint(self, checkpoint: PartitionCheckpoint) -> None:
        params = list(_checkpoint_params(checkpoint))
        self._client.execute(
            """
            UPDATE ingestion_partition_checkpoints
            SET dataset_id = ?, source = ?, request_start = ?, request_end = ?,
                status = ?, last_successful_stage = ?, attempt = ?, retry_budget = ?,
                payload_id = ?, catalog_asset_id = ?, lineage_run_id = ?,
                ingestion_log_id = ?, error_code = ?, updated_at = ?
            WHERE chunk_id = ?
            """,
            [*params[1:], params[0]],
        )

    def _persist_transition(
        self,
        *,
        current: PartitionCheckpoint,
        updated: PartitionCheckpoint,
        evidence_id: str | None,
        error_code: str | None,
        occurred_at: datetime,
    ) -> None:
        try:
            self._update_checkpoint(updated)
            self._insert_event(
                chunk_id=updated.chunk_id,
                from_status=current.status,
                to_status=updated.status,
                attempt=updated.attempt,
                evidence_id=evidence_id,
                error_code=error_code,
                occurred_at=occurred_at,
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def _insert_event(
        self,
        *,
        chunk_id: str,
        from_status: PartitionLifecycleStatus | None,
        to_status: PartitionLifecycleStatus,
        attempt: int,
        evidence_id: str | None,
        error_code: str | None,
        occurred_at: datetime,
    ) -> None:
        self._client.execute(
            """
            INSERT INTO ingestion_partition_events (
                chunk_id, from_status, to_status, attempt, evidence_id,
                error_code, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                chunk_id,
                from_status.value if from_status is not None else None,
                to_status.value,
                attempt,
                evidence_id,
                error_code,
                occurred_at.isoformat(),
            ],
        )


def _checkpoint_params(checkpoint: PartitionCheckpoint) -> list[object]:
    return [
        checkpoint.chunk_id,
        checkpoint.dataset_id,
        checkpoint.source,
        checkpoint.request_start,
        checkpoint.request_end,
        checkpoint.status.value,
        (
            checkpoint.last_successful_stage.value
            if checkpoint.last_successful_stage is not None
            else None
        ),
        checkpoint.attempt,
        checkpoint.retry_budget,
        checkpoint.payload_id,
        checkpoint.catalog_asset_id,
        checkpoint.lineage_run_id,
        checkpoint.ingestion_log_id,
        checkpoint.error_code,
        checkpoint.updated_at.isoformat(),
    ]


def _optional_status(value: object) -> PartitionLifecycleStatus | None:
    return None if value is None else PartitionLifecycleStatus(str(value))


def _checkpoint_from_row(row: dict[str, Any]) -> PartitionCheckpoint:
    return PartitionCheckpoint(
        chunk_id=str(row["chunk_id"]),
        dataset_id=str(row["dataset_id"]),
        source=str(row["source"]),
        request_start=str(row["request_start"]),
        request_end=str(row["request_end"]),
        status=PartitionLifecycleStatus(str(row["status"])),
        last_successful_stage=_optional_status(row["last_successful_stage"]),
        attempt=int(row["attempt"]),
        retry_budget=int(row["retry_budget"]),
        payload_id=str(row["payload_id"]) if row["payload_id"] is not None else None,
        catalog_asset_id=(
            str(row["catalog_asset_id"])
            if row["catalog_asset_id"] is not None
            else None
        ),
        lineage_run_id=(
            str(row["lineage_run_id"]) if row["lineage_run_id"] is not None else None
        ),
        ingestion_log_id=(
            str(row["ingestion_log_id"])
            if row["ingestion_log_id"] is not None
            else None
        ),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _event_from_row(row: dict[str, Any]) -> PartitionLifecycleEvent:
    return PartitionLifecycleEvent(
        event_id=int(row["event_id"]),
        chunk_id=str(row["chunk_id"]),
        from_status=_optional_status(row["from_status"]),
        to_status=PartitionLifecycleStatus(str(row["to_status"])),
        attempt=int(row["attempt"]),
        evidence_id=(
            str(row["evidence_id"]) if row["evidence_id"] is not None else None
        ),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
    )
