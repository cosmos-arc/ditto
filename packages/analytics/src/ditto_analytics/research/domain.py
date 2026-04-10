"""Research dataset and spine models for unified derived snapshots."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import StrEnum

import polars as pl
from ditto_data.errors import (
    DerivedNotImplementedError,
    DerivedValidationError,
)
from ditto_kernel.specs import CalendarId, GrainId

__all__ = [
    "DatasetSnapshot",
    "KnownAtPolicy",
    "LateArrivalError",
    "LateArrivalPolicy",
    "ResearchDatasetSpec",
    "SpineSnapshot",
    "SpineSpec",
    "_apply_late_arrival_policy",
    "_detect_late_arrivals",
]


class LateArrivalError(Exception):
    """Raised when late-arriving data is detected with REQUIRE_REBUILD policy."""


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
            raise DerivedNotImplementedError(
                feature="research spine v1 仅支持 calendar='cn_stock'",
                derived_id=self.spine_id,
            )
        if self.grain != "1d":
            raise DerivedNotImplementedError(
                feature="research spine v1 仅支持 grain='1d'",
                derived_id=self.spine_id,
            )
        if self.entity_key != "instrument_id":
            raise DerivedNotImplementedError(
                feature="research spine v1 仅支持 entity_key='instrument_id'",
                derived_id=self.spine_id,
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
            raise DerivedValidationError(
                field="derived_ids",
                value="()",
                reason="research dataset must include at least one derived_id",
                derived_id=self.dataset_id,
            )
        if self.join_policy != "left_preserving_pit":
            raise DerivedNotImplementedError(
                feature="research dataset v1 仅支持 join_policy='left_preserving_pit'",
                derived_id=self.dataset_id,
            )
        if any(derived_id.startswith("market.") for derived_id in self.derived_ids):
            raise DerivedNotImplementedError(
                feature="research dataset v1 仅支持 derived ids 作为输入",
                derived_id=self.dataset_id,
            )


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


# ============ Late Arrival Detection & Policy ============


def _detect_late_arrivals(frame: pl.DataFrame, derived_id: str) -> pl.DataFrame:
    """
    检测延迟到达的数据行。

    比较 known_at vs {derived_id}_availability_time 列，
    标记 availability_time > known_at 的行。

    Args:
        frame: 研究数据集 DataFrame
        derived_id: 派生数据 ID

    Returns:
        与 frame 结构相同的 DataFrame，包含 is_late 标记列

    """
    availability_col = f"{derived_id}_availability_time"
    if availability_col not in frame.columns:
        return frame.with_columns(pl.lit(False).alias("is_late"))

    return frame.with_columns(
        pl.when(pl.col(availability_col).is_null())
        .then(pl.lit(False))
        .when(pl.col(availability_col) > pl.col("known_at"))
        .then(pl.lit(True))
        .otherwise(pl.lit(False))
        .alias("is_late"),
    )


def _apply_late_arrival_policy(
    frame: pl.DataFrame,
    policy: str,
    late_flags: pl.Series,
) -> pl.DataFrame:
    """
    应用延迟到达策略。

    Args:
        frame: 研究数据集 DataFrame
        policy: 策略名称 (EXCLUDE/SHIFT/REBUILD)
        late_flags: 延迟标记 Series

    Returns:
        处理后的 DataFrame

    Raises:
        LateArrivalError: 当策略为 REQUIRE_REBUILD 且存在延迟行时

    """
    has_late = late_flags.any()

    if not has_late:
        return frame

    if policy == LateArrivalPolicy.EXCLUDE_FROM_CURRENT_SNAPSHOT:
        return frame.filter(~late_flags)

    if policy == LateArrivalPolicy.SHIFT_TO_NEXT_SNAPSHOT:
        warnings.warn(
            (
                "Late arrival detected but SHIFT policy is not "
                "implemented in v1, returning frame unchanged"
            ),
            stacklevel=2,
        )
        return frame

    if policy == LateArrivalPolicy.REQUIRE_REBUILD:
        late_count = int(late_flags.sum())
        raise LateArrivalError(
            f"Late arrival detected ({late_count} rows), snapshot must be rebuilt"
        )

    raise ValueError(f"Unknown late arrival policy: {policy}")
