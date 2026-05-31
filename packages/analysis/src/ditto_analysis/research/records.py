"""DB row deserialization models for research spine/dataset records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import orjson

from ditto_analysis.errors import ResearchDatasetError

__all__ = [
    "ResearchDatasetSnapshotRecord",
    "ResearchDatasetSpecRecord",
    "ResearchSpineSnapshotRecord",
    "ResearchSpineSpecRecord",
]


def _require_int(value: object, field_name: str) -> int:
    """验证值为 int 类型（排除 bool），否则抛出 ResearchDatasetError."""
    if type(value) is not int:
        raise ResearchDatasetError(
            f"{field_name} 必须是 int, 实际: {type(value).__name__}",
        )
    return value


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
        version = _require_int(row.get("version", 1), "version")
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
            derived_ids = tuple(str(x) for x in cast("list[str]", derived_ids_raw))
        else:
            derived_ids = ()
        version = _require_int(row.get("version", 1), "version")
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
        row_count = _require_int(row["row_count"], "row_count")
        version = _require_int(row.get("version", 1), "version")
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
            resolved_versions = {
                str(k): int(v)
                for k, v in cast("dict[str, int]", resolved_versions_raw).items()
            }
        else:
            resolved_versions = {}

        resolved_inputs_raw: object = row.get("resolved_inputs", "[]")
        resolved_inputs: tuple[dict[str, str | int], ...]
        if isinstance(resolved_inputs_raw, str):
            _ri: list[dict[str, str | int]] = orjson.loads(resolved_inputs_raw)
            resolved_inputs = tuple(_ri)
        elif isinstance(resolved_inputs_raw, (tuple, list)):
            resolved_inputs = tuple(
                {str(k): v for k, v in d.items()}
                for d in cast("list[dict[str, str | int]]", resolved_inputs_raw)
            )
        else:
            resolved_inputs = ()

        source_snapshot_ids_raw: object = row.get("source_snapshot_ids", "[]")
        source_snapshot_ids: tuple[str, ...]
        if isinstance(source_snapshot_ids_raw, str):
            _ss: list[str] = orjson.loads(source_snapshot_ids_raw)
            source_snapshot_ids = tuple(_ss)
        elif isinstance(source_snapshot_ids_raw, (tuple, list)):
            source_snapshot_ids = tuple(
                str(x) for x in cast("list[str]", source_snapshot_ids_raw)
            )
        else:
            source_snapshot_ids = ()

        dataset_spec_version = _require_int(
            row["dataset_spec_version"],
            "dataset_spec_version",
        )
        row_count = _require_int(row["row_count"], "row_count")
        spine_spec_version = _require_int(
            row.get("spine_spec_version", 1),
            "spine_spec_version",
        )
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
