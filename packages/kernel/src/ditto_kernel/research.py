"""Runtime record models for research spine and dataset snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ResearchDatasetSnapshotRecord",
    "ResearchDatasetSpecRecord",
    "ResearchSpineSnapshotRecord",
    "ResearchSpineSpecRecord",
]


@dataclass(frozen=True)
class ResearchSpineSpecRecord:
    """Stored research spine spec record."""

    spine_id: str
    universe_id: str
    calendar: str
    grain: str
    entity_key: str
    description: str | None
    created_at: str
    version: int = 1


@dataclass(frozen=True)
class ResearchDatasetSpecRecord:
    """Stored research dataset spec record."""

    dataset_id: str
    spine_id: str
    derived_ids: tuple[str, ...]
    join_policy: str
    known_at_policy: str
    late_arrival_policy: str
    description: str | None
    created_at: str
    version: int = 1


@dataclass(frozen=True)
class ResearchSpineSnapshotRecord:
    """Stored research spine snapshot record."""

    spine_snapshot_id: str
    spine_id: str
    snapshot_start: str
    snapshot_end: str
    row_count: int
    data_path: str
    manifest_hash: str
    created_at: str
    version: int = 1


@dataclass(frozen=True)
class ResearchDatasetSnapshotRecord:
    """Stored research dataset snapshot record."""

    snapshot_id: str
    dataset_id: str
    dataset_spec_version: int
    spine_snapshot_id: str
    snapshot_start: str
    snapshot_end: str
    row_count: int
    data_path: str
    manifest_hash: str
    known_at_policy: str
    effective_cutoff: str | None
    spine_spec_version: int = 1
    resolved_versions: dict[str, int] = field(default_factory=dict)
    resolved_inputs: tuple[dict[str, str | int], ...] = field(default_factory=tuple)
    source_snapshot_ids: tuple[str, ...] = field(default_factory=tuple)
    builder_version: str = ""
    created_at: str = ""
