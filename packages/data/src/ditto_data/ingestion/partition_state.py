"""Durable ingestion partition lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "PartitionCheckpoint",
    "PartitionLifecycleEvent",
    "PartitionLifecycleReader",
    "PartitionLifecycleStatus",
    "PartitionLifecycleWriter",
]


class PartitionLifecycleStatus(StrEnum):
    """Normal and repairable states for one ingestion chunk."""

    PLANNED = "PLANNED"
    FETCHED = "FETCHED"
    NORMALIZED = "NORMALIZED"
    PIT_PASSED = "PIT_PASSED"
    DQ_PASSED = "DQ_PASSED"
    PAYLOAD_COMMITTED = "PAYLOAD_COMMITTED"
    CATALOG_ATTESTED = "CATALOG_ATTESTED"
    LINEAGE_RECORDED = "LINEAGE_RECORDED"
    SUCCESS_RECORDED = "SUCCESS_RECORDED"
    COMPLETE = "COMPLETE"

    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    ORPHAN_PAYLOAD = "ORPHAN_PAYLOAD"
    LOG_ONLY = "LOG_ONLY"
    CATALOG_ONLY = "CATALOG_ONLY"


NORMAL_PARTITION_STAGES: tuple[PartitionLifecycleStatus, ...] = (
    PartitionLifecycleStatus.PLANNED,
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

EXCEPTION_PARTITION_STATES: frozenset[PartitionLifecycleStatus] = frozenset(
    {
        PartitionLifecycleStatus.FAILED,
        PartitionLifecycleStatus.QUARANTINED,
        PartitionLifecycleStatus.ORPHAN_PAYLOAD,
        PartitionLifecycleStatus.LOG_ONLY,
        PartitionLifecycleStatus.CATALOG_ONLY,
    }
)


@dataclass(frozen=True)
class PartitionCheckpoint:
    """Current durable recovery boundary for one provider request chunk."""

    chunk_id: str
    dataset_id: str
    source: str
    request_start: str
    request_end: str
    status: PartitionLifecycleStatus
    last_successful_stage: PartitionLifecycleStatus | None
    attempt: int
    retry_budget: int
    payload_id: str | None
    catalog_asset_id: str | None
    lineage_run_id: str | None
    ingestion_log_id: str | None
    error_code: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        """Reject invalid recovery boundaries before persistence."""
        for field in ("chunk_id", "dataset_id", "source"):
            value = str(getattr(self, field))
            if not value or value.strip() != value:
                raise ValueError(f"Invalid partition checkpoint {field}: {value!r}")
        if self.source != self.source.lower():
            raise ValueError(f"Invalid partition checkpoint source: {self.source!r}")
        try:
            request_start = date.fromisoformat(self.request_start)
            request_end = date.fromisoformat(self.request_end)
        except ValueError as error:
            raise ValueError("partition request interval must use ISO dates") from error
        if request_end < request_start:
            raise ValueError("partition request_end precedes request_start")
        if self.attempt < 1:
            raise ValueError("partition attempt must be positive")
        if self.retry_budget < 1:
            raise ValueError("partition retry_budget must be positive")
        if self.updated_at.tzinfo is None:
            raise ValueError("partition updated_at must be timezone-aware")


@dataclass(frozen=True)
class PartitionLifecycleEvent:
    """Append-only transition audit event."""

    event_id: int
    chunk_id: str
    from_status: PartitionLifecycleStatus | None
    to_status: PartitionLifecycleStatus
    attempt: int
    evidence_id: str | None
    error_code: str | None
    occurred_at: datetime


@runtime_checkable
class PartitionLifecycleReader(Protocol):
    """Read partition recovery boundaries and audit events."""

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        """Return the current recovery boundary for one chunk."""
        ...

    def list_incomplete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        """List non-complete chunks with optional product/provider filters."""
        ...

    def list_complete(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[PartitionCheckpoint, ...]:
        """List complete chunks with optional product/provider filters."""
        ...

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        """List append-only transition events for one chunk."""
        ...


@runtime_checkable
class PartitionLifecycleWriter(Protocol):
    """Create, advance, fail, and resume partition recovery boundaries."""

    def plan_partition(self, checkpoint: PartitionCheckpoint) -> None:
        """Persist an initial PLANNED checkpoint idempotently."""
        ...

    def advance_partition(
        self,
        chunk_id: str,
        to_status: PartitionLifecycleStatus,
        *,
        occurred_at: datetime,
        evidence_id: str | None = None,
    ) -> PartitionCheckpoint:
        """Advance exactly one required normal stage."""
        ...

    def fail_partition(
        self,
        chunk_id: str,
        failure_status: PartitionLifecycleStatus,
        *,
        error_code: str,
        occurred_at: datetime,
    ) -> PartitionCheckpoint:
        """Record one explicit repairable failure state."""
        ...

    def resume_partition(
        self,
        chunk_id: str,
        *,
        occurred_at: datetime,
    ) -> PartitionCheckpoint:
        """Resume at the last durable normal stage within retry budget."""
        ...
