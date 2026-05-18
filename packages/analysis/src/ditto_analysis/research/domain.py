"""Research dataset and spine models for unified derived snapshots."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import StrEnum

import orjson
import polars as pl
from ditto_kernel.market import CalendarId, GrainId

from ditto_analysis.errors import (
    AnalysisError,
    ResearchDatasetError,
)

__all__ = [
    "DatasetSnapshot",
    "KnownAtPolicy",
    "LateArrivalError",
    "LateArrivalPolicy",
    "ResearchDatasetSnapshotRecord",
    "ResearchDatasetSpec",
    "ResearchDatasetSpecRecord",
    "ResearchSpineSnapshotRecord",
    "ResearchSpineSpecRecord",
    "SpineSnapshot",
    "SpineSpec",
    "_apply_late_arrival_policy",
    "_detect_late_arrivals",
]


class LateArrivalError(AnalysisError):
    """Raised when late-arriving data is detected with REQUIRE_REBUILD policy."""


class KnownAtPolicy(StrEnum):
    """Known-at resolution policy for research datasets."""

    SAMPLE_TIME = "sample_time"
    EXPLICIT_CUTOFF = "explicit_cutoff"


class LateArrivalPolicy(StrEnum):
    """
    Late-arrival normalization policy for research inputs.

    SHIFT_TO_NEXT_SNAPSHOT is reserved: not implemented in v1.
    Consumers must not rely on shift semantics until promoted.
    """

    EXCLUDE_FROM_CURRENT_SNAPSHOT = "exclude_from_current_snapshot"
    SHIFT_TO_NEXT_SNAPSHOT = "shift_to_next_snapshot"  # reserved: not implemented
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
            raise ResearchDatasetError(
                f"research spine v1 仅支持 calendar='cn_stock': {self.spine_id}",
            )
        if self.grain != "1d":
            raise ResearchDatasetError(
                f"research spine v1 仅支持 grain='1d': {self.spine_id}",
            )
        if self.entity_key != "instrument_id":
            raise ResearchDatasetError(
                f"research spine v1 仅支持 entity_key='instrument_id': {self.spine_id}",
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
            raise ResearchDatasetError(
                f"research dataset needs >=1 derived_id: {self.dataset_id}",
            )
        if self.join_policy != "left_preserving_pit":
            raise ResearchDatasetError(
                f"v1 仅支持 join_policy='left_preserving_pit': {self.dataset_id}",
            )
        if any(derived_id.startswith("market.") for derived_id in self.derived_ids):
            raise ResearchDatasetError(
                f"v1 仅支持 derived ids 作为输入: {self.dataset_id}",
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
                "SHIFT_TO_NEXT_SNAPSHOT is reserved (not implemented). "
                "Late arrival detected but frame returned unchanged."
            ),
            stacklevel=2,
        )
        return frame

    if policy == LateArrivalPolicy.REQUIRE_REBUILD:
        late_count = int(late_flags.sum())
        raise LateArrivalError(
            f"Late arrival detected ({late_count} rows), snapshot must be rebuilt"
        )

    raise ResearchDatasetError(
        f"Unknown late arrival policy: {policy}",
        policy=policy,
        supported=tuple(item.value for item in LateArrivalPolicy),
        supported_policies=tuple(item.value for item in LateArrivalPolicy),
    )


# ============ Runtime Record Models (migrated from ditto_kernel.research) ============


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

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ResearchSpineSpecRecord:
        """从数据库行字典构造记录，验证必填字段."""
        spine_id = row.get("spine_id")
        if not spine_id or not isinstance(spine_id, str):
            raise ResearchDatasetError(
                f"from_row: spine_id is required, got {spine_id!r}",
            )
        _version: object = row.get("version", 1)
        version = _version if isinstance(_version, int) else 1
        return cls(
            spine_id=spine_id,
            universe_id=str(row["universe_id"]),
            calendar=str(row["calendar"]),
            grain=str(row["grain"]),
            entity_key=str(row["entity_key"]),
            description=(
                str(row["description"]) if row.get("description") is not None else None
            ),
            created_at=str(row["created_at"]),
            version=version,
        )


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

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ResearchDatasetSpecRecord:
        """从数据库行字典构造记录，含 orjson 反序列化."""
        dataset_id = row.get("dataset_id")
        if not dataset_id or not isinstance(dataset_id, str):
            raise ResearchDatasetError(
                f"from_row: dataset_id is required, got {dataset_id!r}",
            )
        derived_ids_raw: object = row.get("derived_ids", "[]")
        derived_ids: tuple[str, ...]
        if isinstance(derived_ids_raw, str):
            _di: list[str] = orjson.loads(derived_ids_raw)
            derived_ids = tuple(_di)
        elif isinstance(derived_ids_raw, (tuple, list)):
            _di2: list[str] = orjson.loads(orjson.dumps(derived_ids_raw))
            derived_ids = tuple(_di2)
        else:
            derived_ids = ()
        _version: object = row.get("version", 1)
        version = _version if isinstance(_version, int) else 1
        return cls(
            dataset_id=dataset_id,
            spine_id=str(row["spine_id"]),
            derived_ids=derived_ids,
            join_policy=str(row["join_policy"]),
            known_at_policy=str(row["known_at_policy"]),
            late_arrival_policy=str(row["late_arrival_policy"]),
            description=(
                str(row["description"]) if row.get("description") is not None else None
            ),
            created_at=str(row["created_at"]),
            version=version,
        )


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

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ResearchSpineSnapshotRecord:
        """从数据库行字典构造记录，验证必填字段."""
        spine_snapshot_id = row.get("spine_snapshot_id")
        if not spine_snapshot_id or not isinstance(spine_snapshot_id, str):
            raise ResearchDatasetError(
                f"from_row: spine_snapshot_id is required, got {spine_snapshot_id!r}",
            )
        _row_count: object = row["row_count"]
        row_count = _row_count if isinstance(_row_count, int) else 0
        _version: object = row.get("version", 1)
        version = _version if isinstance(_version, int) else 1
        return cls(
            spine_snapshot_id=spine_snapshot_id,
            spine_id=str(row["spine_id"]),
            snapshot_start=str(row["snapshot_start"]),
            snapshot_end=str(row["snapshot_end"]),
            row_count=row_count,
            data_path=str(row["data_path"]),
            manifest_hash=str(row["manifest_hash"]),
            created_at=str(row["created_at"]),
            version=version,
        )


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

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ResearchDatasetSnapshotRecord:
        """从数据库行字典构造记录，含 orjson 反序列化."""
        snapshot_id = row.get("snapshot_id")
        if not snapshot_id or not isinstance(snapshot_id, str):
            raise ResearchDatasetError(
                f"from_row: snapshot_id is required, got {snapshot_id!r}",
            )
        resolved_versions_raw: object = row.get("resolved_versions", "{}")
        resolved_versions: dict[str, int]
        if isinstance(resolved_versions_raw, str):
            _rv: dict[str, int] = orjson.loads(resolved_versions_raw)
            resolved_versions = _rv
        elif isinstance(resolved_versions_raw, dict):
            _rv2: dict[str, int] = orjson.loads(orjson.dumps(resolved_versions_raw))
            resolved_versions = _rv2
        else:
            resolved_versions = {}

        resolved_inputs_raw: object = row.get("resolved_inputs", "[]")
        resolved_inputs: tuple[dict[str, str | int], ...]
        if isinstance(resolved_inputs_raw, str):
            _ri: list[dict[str, str | int]] = orjson.loads(resolved_inputs_raw)
            resolved_inputs = tuple(_ri)
        elif isinstance(resolved_inputs_raw, (tuple, list)):
            _ri2: list[dict[str, str | int]] = orjson.loads(
                orjson.dumps(resolved_inputs_raw),
            )
            resolved_inputs = tuple(_ri2)
        else:
            resolved_inputs = ()

        source_snapshot_ids_raw: object = row.get("source_snapshot_ids", "[]")
        source_snapshot_ids: tuple[str, ...]
        if isinstance(source_snapshot_ids_raw, str):
            _ss: list[str] = orjson.loads(source_snapshot_ids_raw)
            source_snapshot_ids = tuple(_ss)
        elif isinstance(source_snapshot_ids_raw, (tuple, list)):
            _ss2: list[str] = orjson.loads(orjson.dumps(source_snapshot_ids_raw))
            source_snapshot_ids = tuple(_ss2)
        else:
            source_snapshot_ids = ()

        _spec_ver: object = row["dataset_spec_version"]
        dataset_spec_version = _spec_ver if isinstance(_spec_ver, int) else 0
        _row_count: object = row["row_count"]
        row_count = _row_count if isinstance(_row_count, int) else 0
        _spine_spec_ver: object = row.get("spine_spec_version", 1)
        spine_spec_version = _spine_spec_ver if isinstance(_spine_spec_ver, int) else 1
        return cls(
            snapshot_id=snapshot_id,
            dataset_id=str(row["dataset_id"]),
            dataset_spec_version=dataset_spec_version,
            spine_snapshot_id=str(row["spine_snapshot_id"]),
            snapshot_start=str(row["snapshot_start"]),
            snapshot_end=str(row["snapshot_end"]),
            row_count=row_count,
            data_path=str(row["data_path"]),
            manifest_hash=str(row["manifest_hash"]),
            known_at_policy=str(row["known_at_policy"]),
            effective_cutoff=(
                str(row["effective_cutoff"])
                if row.get("effective_cutoff") is not None
                else None
            ),
            spine_spec_version=spine_spec_version,
            resolved_versions=resolved_versions,
            resolved_inputs=resolved_inputs,
            source_snapshot_ids=source_snapshot_ids,
            builder_version=str(row.get("builder_version", "")),
            created_at=str(row.get("created_at", "")),
        )
