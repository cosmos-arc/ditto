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
    """
    Three-phase fetch log states for one ingestion chunk (#447).

    失败不落独立态：checkpoint 停留在已达到的阶段并以 error_code 标注，
    恢复动作＝同请求重跑（各阶段幂等）。
    """

    PLANNED = "PLANNED"
    PAYLOAD_COMMITTED = "PAYLOAD_COMMITTED"
    COMPLETE = "COMPLETE"


NORMAL_PARTITION_STAGES: tuple[PartitionLifecycleStatus, ...] = (
    PartitionLifecycleStatus.PLANNED,
    PartitionLifecycleStatus.PAYLOAD_COMMITTED,
    PartitionLifecycleStatus.COMPLETE,
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
    payload_id: str | None
    complete_evidence_id: str | None
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
        if self.updated_at.tzinfo is None:
            raise ValueError("partition updated_at must be timezone-aware")


@dataclass(frozen=True)
class PartitionLifecycleEvent:
    """Append-only transition audit event."""

    event_id: int
    chunk_id: str
    from_status: PartitionLifecycleStatus | None
    to_status: PartitionLifecycleStatus
    evidence_id: str | None
    error_code: str | None
    occurred_at: datetime


@runtime_checkable
class PartitionLifecycleReader(Protocol):
    """Read partition recovery boundaries and audit events."""

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        """Return the most recently advanced revision of a planned chunk."""
        ...

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
    """Create and advance partition recovery boundaries."""

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

    def record_partition_error(
        self,
        chunk_id: str,
        *,
        error_code: str,
        occurred_at: datetime,
    ) -> PartitionCheckpoint:
        """Annotate the current stage with a failure code, no state change."""
        ...
