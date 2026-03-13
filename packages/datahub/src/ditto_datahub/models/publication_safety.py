"""Runtime record models for derived publication safety."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
type JsonDict = dict[str, JsonValue]

__all__ = [
    "CertificationReportRecord",
    "CompatibilityManifestRecord",
    "JsonDict",
    "JsonValue",
    "ShadowDiffReportRecord",
    "ShadowTraceRecordRecord",
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


def _require_payload(data: Mapping[str, JsonValue], key: str) -> JsonDict:
    """Extract a required JSON object field from payload."""
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a JSON object")
    return cast(JsonDict, value)


@dataclass(frozen=True)
class CompatibilityManifestRecord:
    """Stored compatibility manifest runtime record."""

    derived_id: str
    version: int
    manifest_hash: str
    payload: JsonDict
    created_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "derived_id": self.derived_id,
            "version": self.version,
            "manifest_hash": self.manifest_hash,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json_dict(
        cls,
        data: Mapping[str, JsonValue],
    ) -> CompatibilityManifestRecord:
        """Create record from JSON dictionary."""
        return cls(
            derived_id=_require_str(data, "derived_id"),
            version=_require_int(data, "version"),
            manifest_hash=_require_str(data, "manifest_hash"),
            payload=_require_payload(data, "payload"),
            created_at=_require_str(data, "created_at"),
        )


@dataclass(frozen=True)
class ShadowDiffReportRecord:
    """Stored shadow diff runtime record."""

    report_id: str
    derived_id: str
    candidate_version: int
    baseline_version: int
    error_count: int
    warning_count: int
    info_count: int
    payload: JsonDict
    created_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "report_id": self.report_id,
            "derived_id": self.derived_id,
            "candidate_version": self.candidate_version,
            "baseline_version": self.baseline_version,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json_dict(
        cls,
        data: Mapping[str, JsonValue],
    ) -> ShadowDiffReportRecord:
        """Create record from JSON dictionary."""
        return cls(
            report_id=_require_str(data, "report_id"),
            derived_id=_require_str(data, "derived_id"),
            candidate_version=_require_int(data, "candidate_version"),
            baseline_version=_require_int(data, "baseline_version"),
            error_count=_require_int(data, "error_count"),
            warning_count=_require_int(data, "warning_count"),
            info_count=_require_int(data, "info_count"),
            payload=_require_payload(data, "payload"),
            created_at=_require_str(data, "created_at"),
        )


@dataclass(frozen=True)
class ShadowTraceRecordRecord:
    """Stored shadow trace runtime record."""

    trace_id: str
    report_id: str
    derived_id: str
    payload: JsonDict
    sampled_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "report_id": self.report_id,
            "derived_id": self.derived_id,
            "payload": self.payload,
            "sampled_at": self.sampled_at,
        }

    @classmethod
    def from_json_dict(
        cls,
        data: Mapping[str, JsonValue],
    ) -> ShadowTraceRecordRecord:
        """Create record from JSON dictionary."""
        return cls(
            trace_id=_require_str(data, "trace_id"),
            report_id=_require_str(data, "report_id"),
            derived_id=_require_str(data, "derived_id"),
            payload=_require_payload(data, "payload"),
            sampled_at=_require_str(data, "sampled_at"),
        )


@dataclass(frozen=True)
class CertificationReportRecord:
    """Stored certification runtime record."""

    report_id: str
    derived_id: str
    version: int
    stage: str
    pack_id: str
    manifest_hash: str
    payload: JsonDict
    created_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "report_id": self.report_id,
            "derived_id": self.derived_id,
            "version": self.version,
            "stage": self.stage,
            "pack_id": self.pack_id,
            "manifest_hash": self.manifest_hash,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json_dict(
        cls,
        data: Mapping[str, JsonValue],
    ) -> CertificationReportRecord:
        """Create record from JSON dictionary."""
        return cls(
            report_id=_require_str(data, "report_id"),
            derived_id=_require_str(data, "derived_id"),
            version=_require_int(data, "version"),
            stage=_require_str(data, "stage"),
            pack_id=_require_str(data, "pack_id"),
            manifest_hash=_require_str(data, "manifest_hash"),
            payload=_require_payload(data, "payload"),
            created_at=_require_str(data, "created_at"),
        )
