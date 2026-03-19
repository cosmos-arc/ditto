"""Data models for derived catalog garbage collection."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "GcConfig",
    "GcPlan",
    "GcReport",
]


@dataclass(frozen=True)
class GcConfig:
    """Configuration for garbage collection behavior."""

    keep_last_n: int = 3


@dataclass(frozen=True)
class GcReport:
    """Result of a single garbage collection pass for one derived id."""

    derived_id: str
    versions_deleted: int
    files_removed: int
    records_removed: int
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class GcPlan:
    """Describes what would be deleted for one version (dry-run output)."""

    derived_id: str
    version: int
    partition_paths: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
