"""Runtime record models for derived catalog metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
type JsonDict = dict[str, JsonValue]

__all__ = [
    "CompiledExpressionCacheRecord",
    "CompiledExpressionOperatorRecord",
    "DerivedCheckpointRecord",
    "DerivedDependencyRecord",
    "DerivedInvalidationRecord",
    "DerivedPartitionRecord",
    "DerivedRunRecord",
    "DerivedSpecRecord",
    "DerivedStateRecord",
    "DerivedVersionRecord",
    "JsonDict",
    "JsonValue",
    "PartitionInfo",
]


def _require_str(data: Mapping[str, JsonValue], key: str) -> str:
    """Extract a required string field from JSON payload."""
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _require_int(data: Mapping[str, JsonValue], key: str) -> int:
    """Extract a required int field from JSON payload."""
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int")
    return value


def _optional_str(data: Mapping[str, JsonValue], key: str) -> str | None:
    """Extract an optional string field from JSON payload."""
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string or null")
    return value


def _require_bool(data: Mapping[str, JsonValue], key: str) -> bool:
    """Extract a required bool field from JSON payload."""
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a bool")
    return value


def _require_payload(data: Mapping[str, JsonValue], key: str) -> JsonDict:
    """Extract a required JSON object field from payload."""
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a JSON object")
    return cast(JsonDict, value)


def _require_str_tuple(data: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    """Extract a required list of strings from payload."""
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a list of strings")
    return tuple(cast(Sequence[str], value))


@dataclass(frozen=True)
class DerivedSpecRecord:
    """Stored derived spec runtime record."""

    derived_id: str
    version: int
    role: str
    materialization_profile: str
    spec_hash: str
    spec_json: JsonDict
    created_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to JSON dictionary."""
        return {
            "derived_id": self.derived_id,
            "version": self.version,
            "role": self.role,
            "materialization_profile": self.materialization_profile,
            "spec_hash": self.spec_hash,
            "spec_json": self.spec_json,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json_dict(cls, data: Mapping[str, JsonValue]) -> DerivedSpecRecord:
        """Create record from JSON dictionary."""
        return cls(
            derived_id=_require_str(data, "derived_id"),
            version=_require_int(data, "version"),
            role=_require_str(data, "role"),
            materialization_profile=_require_str(data, "materialization_profile"),
            spec_hash=_require_str(data, "spec_hash"),
            spec_json=_require_payload(data, "spec_json"),
            created_at=_require_str(data, "created_at"),
        )


@dataclass(frozen=True)
class DerivedVersionRecord:
    """Stored derived version runtime record."""

    derived_id: str
    version: int
    status: str
    engine_version: str
    is_online: bool
    is_primary: bool
    created_at: str
    updated_at: str | None

    def to_json_dict(self) -> JsonDict:
        """Convert record to JSON dictionary."""
        return {
            "derived_id": self.derived_id,
            "version": self.version,
            "status": self.status,
            "engine_version": self.engine_version,
            "is_online": self.is_online,
            "is_primary": self.is_primary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json_dict(cls, data: Mapping[str, JsonValue]) -> DerivedVersionRecord:
        """Create record from JSON dictionary."""
        return cls(
            derived_id=_require_str(data, "derived_id"),
            version=_require_int(data, "version"),
            status=_require_str(data, "status"),
            engine_version=_require_str(data, "engine_version"),
            is_online=_require_bool(data, "is_online"),
            is_primary=_require_bool(data, "is_primary"),
            created_at=_require_str(data, "created_at"),
            updated_at=_optional_str(data, "updated_at"),
        )


@dataclass(frozen=True)
class DerivedRunRecord:
    """Stored derived materialization run record."""

    run_id: str
    derived_id: str
    version: int
    mode: str
    trigger: str
    request_start: str
    request_end: str
    compute_start: str
    compute_end: str
    source_snapshot_id: str | None
    status: str
    rows_written: int
    partitions_written: tuple[str, ...]
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    def to_json_dict(self) -> JsonDict:
        """Convert record to JSON dictionary."""
        return {
            "run_id": self.run_id,
            "derived_id": self.derived_id,
            "version": self.version,
            "mode": self.mode,
            "trigger": self.trigger,
            "request_start": self.request_start,
            "request_end": self.request_end,
            "compute_start": self.compute_start,
            "compute_end": self.compute_end,
            "source_snapshot_id": self.source_snapshot_id,
            "status": self.status,
            "rows_written": self.rows_written,
            "partitions_written": list(self.partitions_written),
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_json_dict(cls, data: Mapping[str, JsonValue]) -> DerivedRunRecord:
        """Create record from JSON dictionary."""
        return cls(
            run_id=_require_str(data, "run_id"),
            derived_id=_require_str(data, "derived_id"),
            version=_require_int(data, "version"),
            mode=_require_str(data, "mode"),
            trigger=_require_str(data, "trigger"),
            request_start=_require_str(data, "request_start"),
            request_end=_require_str(data, "request_end"),
            compute_start=_require_str(data, "compute_start"),
            compute_end=_require_str(data, "compute_end"),
            source_snapshot_id=_optional_str(data, "source_snapshot_id"),
            status=_require_str(data, "status"),
            rows_written=_require_int(data, "rows_written"),
            partitions_written=_require_str_tuple(data, "partitions_written"),
            error_message=_optional_str(data, "error_message"),
            created_at=_require_str(data, "created_at"),
            started_at=_optional_str(data, "started_at"),
            finished_at=_optional_str(data, "finished_at"),
        )


@dataclass(frozen=True)
class DerivedPartitionRecord:
    """Stored derived partition runtime record."""

    run_id: str
    derived_id: str
    version: int
    partition_key: str
    partition_path: str
    row_count: int
    checksum: str | None
    written_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to JSON dictionary."""
        return {
            "run_id": self.run_id,
            "derived_id": self.derived_id,
            "version": self.version,
            "partition_key": self.partition_key,
            "partition_path": self.partition_path,
            "row_count": self.row_count,
            "checksum": self.checksum,
            "written_at": self.written_at,
        }

    @classmethod
    def from_json_dict(cls, data: Mapping[str, JsonValue]) -> DerivedPartitionRecord:
        """Create record from JSON dictionary."""
        return cls(
            run_id=_require_str(data, "run_id"),
            derived_id=_require_str(data, "derived_id"),
            version=_require_int(data, "version"),
            partition_key=_require_str(data, "partition_key"),
            partition_path=_require_str(data, "partition_path"),
            row_count=_require_int(data, "row_count"),
            checksum=_optional_str(data, "checksum"),
            written_at=_require_str(data, "written_at"),
        )


@dataclass(frozen=True)
class DerivedStateRecord:
    """Stored derived latest state runtime record."""

    derived_id: str
    active_version: int | None
    coverage_start: str | None
    coverage_end: str | None
    watermark: str | None
    latest_run_id: str | None
    latest_run_status: str | None
    total_rows: int
    updated_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to JSON dictionary."""
        return {
            "derived_id": self.derived_id,
            "active_version": self.active_version,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "watermark": self.watermark,
            "latest_run_id": self.latest_run_id,
            "latest_run_status": self.latest_run_status,
            "total_rows": self.total_rows,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json_dict(cls, data: Mapping[str, JsonValue]) -> DerivedStateRecord:
        """Create record from JSON dictionary."""
        active_version = data.get("active_version")
        if active_version is not None and (
            not isinstance(active_version, int) or isinstance(active_version, bool)
        ):
            raise TypeError("active_version must be an int or null")
        total_rows = data.get("total_rows")
        if not isinstance(total_rows, int) or isinstance(total_rows, bool):
            raise TypeError("total_rows must be an int")

        return cls(
            derived_id=_require_str(data, "derived_id"),
            active_version=active_version,
            coverage_start=_optional_str(data, "coverage_start"),
            coverage_end=_optional_str(data, "coverage_end"),
            watermark=_optional_str(data, "watermark"),
            latest_run_id=_optional_str(data, "latest_run_id"),
            latest_run_status=_optional_str(data, "latest_run_status"),
            total_rows=total_rows,
            updated_at=_require_str(data, "updated_at"),
        )


@dataclass(frozen=True)
class DerivedCheckpointRecord:
    """Stored checkpoint metadata for durable partitions."""

    derived_id: str
    version: int
    partition_key: str
    status: str
    rows_written: int
    checksum: str | None
    error_message: str | None
    started_at: str
    completed_at: str | None


@dataclass(frozen=True)
class DerivedDependencyRecord:
    """Stored dependency edge between derived specs and upstream inputs."""

    derived_id: str
    version: int
    dependency_kind: str
    dependency_ref: str
    created_at: str


@dataclass(frozen=True)
class DerivedInvalidationRecord:
    """Stored invalidation task created from a source change."""

    invalidation_id: str
    derived_id: str
    version: int
    source_domain: str
    source_dataset: str
    change_date: str
    affected_start: str
    affected_end: str
    source_snapshot_id: str | None
    root_dependency_ref: str
    status: str
    created_at: str
    processed_at: str | None
    depth: int = 0
    retry_count: int = 0
    error_message: str | None = None
    dead_letter_at: str | None = None
    role: str = "factor"


@dataclass(frozen=True)
class CompiledExpressionCacheRecord:
    """Stored compile cache metadata."""

    cache_key: str
    derived_id: str
    version: int
    compiler_fingerprint: str
    compile_input_hash: str
    analysis_json: JsonDict
    compile_identity_json: JsonDict
    expression_repr: str
    created_at: str


@dataclass(frozen=True)
class CompiledExpressionOperatorRecord:
    """Stored operator versions participating in a compile cache entry."""

    cache_key: str
    operator_name: str
    operator_version: str


@dataclass(frozen=True)
class PartitionInfo:
    """Metadata for a single artifact partition."""

    partition_key: str
    partition_path: str
    row_count: int
    checksum: str | None
