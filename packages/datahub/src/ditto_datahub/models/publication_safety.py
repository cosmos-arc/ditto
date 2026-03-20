"""Runtime record models for derived publication safety."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_datahub.models.common import (
    JsonDict,
    JsonValue,
    require_bool,
    require_int,
    require_payload,
    require_str,
)

__all__ = [
    "CertificationReportRecord",
    "CompatibilityManifestRecord",
    "DerivedMinimalDQSummaryRecord",
    "DerivedShadowSlotRecord",
    "JsonDict",
    "JsonValue",
    "ShadowDiffReportRecord",
    "ShadowTraceRecordRecord",
]


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
            derived_id=require_str(data, "derived_id"),
            version=require_int(data, "version"),
            manifest_hash=require_str(data, "manifest_hash"),
            payload=require_payload(data, "payload"),
            created_at=require_str(data, "created_at"),
        )


@dataclass(frozen=True)
class DerivedMinimalDQSummaryRecord:
    """Stored minimal DQ summary for one derived materialization run."""

    derived_id: str
    version: int
    run_id: str
    passed: bool
    error_count: int
    payload: JsonDict
    created_at: str

    def to_json_dict(self) -> JsonDict:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "derived_id": self.derived_id,
            "version": self.version,
            "run_id": self.run_id,
            "passed": self.passed,
            "error_count": self.error_count,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json_dict(
        cls,
        data: Mapping[str, JsonValue],
    ) -> DerivedMinimalDQSummaryRecord:
        """Create record from JSON dictionary."""
        return cls(
            derived_id=require_str(data, "derived_id"),
            version=require_int(data, "version"),
            run_id=require_str(data, "run_id"),
            passed=require_bool(data, "passed"),
            error_count=require_int(data, "error_count"),
            payload=require_payload(data, "payload"),
            created_at=require_str(data, "created_at"),
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
            report_id=require_str(data, "report_id"),
            derived_id=require_str(data, "derived_id"),
            candidate_version=require_int(data, "candidate_version"),
            baseline_version=require_int(data, "baseline_version"),
            error_count=require_int(data, "error_count"),
            warning_count=require_int(data, "warning_count"),
            info_count=require_int(data, "info_count"),
            payload=require_payload(data, "payload"),
            created_at=require_str(data, "created_at"),
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
            trace_id=require_str(data, "trace_id"),
            report_id=require_str(data, "report_id"),
            derived_id=require_str(data, "derived_id"),
            payload=require_payload(data, "payload"),
            sampled_at=require_str(data, "sampled_at"),
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
            report_id=require_str(data, "report_id"),
            derived_id=require_str(data, "derived_id"),
            version=require_int(data, "version"),
            stage=require_str(data, "stage"),
            pack_id=require_str(data, "pack_id"),
            manifest_hash=require_str(data, "manifest_hash"),
            payload=require_payload(data, "payload"),
            created_at=require_str(data, "created_at"),
        )


@dataclass(frozen=True)
class DerivedShadowSlotRecord:
    """Stored active shadow candidate slot for one derived id."""

    derived_id: str
    candidate_version: int
    baseline_version: int | None
    activated_at: str
    disabled_at: str | None
