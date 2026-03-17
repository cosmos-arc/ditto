"""Research dataset and spine models for unified derived snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ditto_core.engine.specs import CalendarId, GrainId

__all__ = [
    "DatasetSnapshot",
    "KnownAtPolicy",
    "LateArrivalPolicy",
    "ResearchDatasetSpec",
    "SpineSnapshot",
    "SpineSpec",
]


class KnownAtPolicy(StrEnum):
    """Known-at resolution policy for research datasets."""

    SAMPLE_TIME = "sample_time"
    EXPLICIT_CUTOFF = "explicit_cutoff"


class LateArrivalPolicy(StrEnum):
    """Late-arrival normalization policy for research inputs."""

    EXCLUDE_FROM_CURRENT_SNAPSHOT = "exclude_from_current_snapshot"
    SHIFT_TO_NEXT_SNAPSHOT = "shift_to_next_snapshot"
    REQUIRE_REBUILD = "require_rebuild"


@dataclass(frozen=True)
class SpineSpec:
    """Frozen definition of a research spine."""

    spine_id: str
    universe_id: str
    version: int = 1
    calendar: CalendarId = "cn_stock"
    grain: GrainId = "1d"
    entity_key: str = "instrument_id"
    description: str | None = None

    def validate_spec(self) -> None:
        """Validate current v1 boundaries."""
        if self.calendar != "cn_stock":
            raise NotImplementedError("research spine v1 仅支持 calendar='cn_stock'")
        if self.grain != "1d":
            raise NotImplementedError("research spine v1 仅支持 grain='1d'")
        if self.entity_key != "instrument_id":
            raise NotImplementedError(
                "research spine v1 仅支持 entity_key='instrument_id'"
            )


@dataclass(frozen=True)
class ResearchDatasetSpec:
    """Frozen definition of a research dataset build."""

    dataset_id: str
    spine_id: str
    derived_ids: tuple[str, ...]
    version: int = 1
    join_policy: str = "left_preserving_pit"
    known_at_policy: KnownAtPolicy = KnownAtPolicy.SAMPLE_TIME
    late_arrival_policy: LateArrivalPolicy = LateArrivalPolicy.REQUIRE_REBUILD
    description: str | None = None

    def validate_spec(self) -> None:
        """Validate current v1 boundaries."""
        if not self.derived_ids:
            raise ValueError("research dataset must include at least one derived_id")
        if self.join_policy != "left_preserving_pit":
            raise NotImplementedError(
                "research dataset v1 仅支持 join_policy='left_preserving_pit'"
            )
        if any(derived_id.startswith("market.") for derived_id in self.derived_ids):
            raise NotImplementedError("research dataset v1 仅支持 derived ids 作为输入")


@dataclass(frozen=True)
class SpineSnapshot:
    """Immutable frozen spine snapshot."""

    spine_snapshot_id: str
    spine_id: str
    start: str
    end: str
    row_count: int
    data_path: str
    manifest_hash: str
    created_at: str
    version: int = 1


@dataclass(frozen=True)
class DatasetSnapshot:
    """Immutable frozen dataset snapshot."""

    snapshot_id: str
    dataset_id: str
    dataset_spec_version: int
    spine_snapshot_id: str
    start: str
    end: str
    row_count: int
    data_path: str
    manifest_hash: str
    known_at_policy: KnownAtPolicy
    effective_cutoff: str | None
    spine_spec_version: int = 1
    resolved_versions: dict[str, int] = field(default_factory=dict)
    resolved_inputs: tuple[dict[str, str | int], ...] = field(default_factory=tuple)
    source_snapshot_ids: tuple[str, ...] = field(default_factory=tuple)
    builder_version: str = ""
    created_at: str = ""
