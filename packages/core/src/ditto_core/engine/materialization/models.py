"""Derived runtime and materialization control models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "DerivedPartition",
    "DerivedRun",
    "DerivedRunMode",
    "DerivedRunStatus",
    "DerivedRunTrigger",
    "DerivedState",
    "DerivedVersion",
    "DerivedVersionStatus",
]


class DerivedVersionStatus(StrEnum):
    """Catalog lifecycle status for a derived version."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DerivedRunMode(StrEnum):
    """Materialization run mode."""

    FULL = "full"
    INCREMENTAL = "incremental"


class DerivedRunTrigger(StrEnum):
    """Materialization trigger source."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    CASCADE = "cascade"


class DerivedRunStatus(StrEnum):
    """Materialization run status."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DerivedVersion:
    """Catalog metadata for a spec version."""

    derived_id: str
    version: int
    spec_hash: str
    engine_version: str
    status: DerivedVersionStatus
    is_online: bool
    is_primary: bool
    created_at: str
    updated_at: str | None = None

    def is_active(self) -> bool:
        """Return whether the version is active."""
        return self.status == DerivedVersionStatus.ACTIVE


@dataclass(frozen=True)
class DerivedRun:
    """Single materialization run record."""

    run_id: str
    derived_id: str
    version: int
    mode: DerivedRunMode
    trigger: DerivedRunTrigger
    request_start: str
    request_end: str
    compute_start: str
    compute_end: str
    source_snapshot_id: str | None
    status: DerivedRunStatus
    rows_written: int
    partitions_written: tuple[str, ...]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None

    def is_finished(self) -> bool:
        """Return whether the run has reached a terminal status."""
        return self.status in (DerivedRunStatus.SUCCESS, DerivedRunStatus.FAILED)


@dataclass(frozen=True)
class DerivedPartition:
    """Single partition written by a materialization run."""

    run_id: str
    derived_id: str
    version: int
    partition_key: str
    partition_path: str
    row_count: int
    checksum: str | None
    written_at: str


@dataclass(frozen=True)
class DerivedState:
    """Latest runtime state for a derived entity."""

    derived_id: str
    active_version: int | None
    coverage_start: str | None
    coverage_end: str | None
    watermark: str | None
    latest_run_id: str | None
    latest_run_status: DerivedRunStatus | None
    total_rows: int
    updated_at: str

    def has_coverage(self) -> bool:
        """Return whether the entity has materialized coverage."""
        return self.coverage_start is not None and self.coverage_end is not None
