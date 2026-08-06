"""Pure content-addressed manifest contracts for experiment artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast

import orjson

from ditto_analysis.errors import ExperimentIntegrityError, ExperimentSpecError
from ditto_analysis.experiments._validation import require_utc_datetime
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    canonical_payload,
    validate_artifact_relative_path,
)

__all__ = [
    "ArtifactFormat",
    "ArtifactManifest",
    "ArtifactPublicationSpec",
]

_MANIFEST_SCHEMA_VERSION = 1
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "format",
        "artifact_id",
        "artifact_kind",
        "relative_path",
        "created_at",
        "lineage",
        "reproduction_fingerprint",
        "content",
        "audit",
        "manifest_content_hash",
    }
)


def _spec_error(
    message: str, reason_code: str, **details: object
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _integrity_error(
    message: str, reason_code: str, **details: object
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _identity(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _spec_error(
            f"{field_name} must be a non-empty unpadded string",
            "invalid_artifact_identity",
            field_name=field_name,
        )
    return value


def _deep_freeze(value: object) -> object:
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        return MappingProxyType(
            {key: _deep_freeze(mapping[key]) for key in sorted(mapping, key=str.encode)}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in cast("list[object]", value))
    return value


def _require_lineage_path(
    relative_path: str,
    *,
    experiment_id: ExperimentId,
    candidate_id: CandidateId | None,
    fold_id: FoldId | None,
    attempt_id: AttemptId | None,
) -> None:
    canonical = validate_artifact_relative_path(relative_path)
    expected = ["experiments", str(experiment_id)]
    for label, identity in (
        ("candidates", candidate_id),
        ("folds", fold_id),
        ("attempts", attempt_id),
    ):
        if identity is not None:
            expected.extend((label, str(identity)))
    if len(canonical.parts) != len(expected) + 1 or canonical.parts[
        : len(expected)
    ] != tuple(expected):
        raise _spec_error(
            "artifact path does not exactly encode its typed lineage",
            "artifact_path_lineage_mismatch",
            expected_prefix="/".join(expected),
        )
    leaf = canonical.name
    if (
        leaf.startswith(".")
        or leaf.endswith(".ditto-manifest.json")
        or leaf.endswith(".tmp")
    ):
        raise _spec_error(
            "artifact filename overlaps the internal publication namespace",
            "artifact_path_reserved",
            filename=leaf,
        )


def _validate_lineage_contract(
    experiment_id: object,
    candidate_id: object | None,
    fold_id: object | None,
    attempt_id: object | None,
    reproduction_fingerprint: object,
) -> None:
    typed_values = (
        (experiment_id, ExperimentId, "experiment_id"),
        (candidate_id, CandidateId, "candidate_id"),
        (fold_id, FoldId, "fold_id"),
        (attempt_id, AttemptId, "attempt_id"),
    )
    for value, expected_type, field_name in typed_values:
        if value is not None and type(value) is not expected_type:
            raise _spec_error(
                f"{field_name} must use its exact nominal identity type",
                "invalid_artifact_lineage",
            )
    if (fold_id is not None and candidate_id is None) or (
        attempt_id is not None and fold_id is None
    ):
        raise _spec_error(
            "artifact lineage cannot contain a gap",
            "invalid_artifact_lineage",
        )
    if type(reproduction_fingerprint) is not ContentHash:
        raise _spec_error(
            "reproduction fingerprint must be a full content hash",
            "invalid_reproduction_fingerprint",
        )


def _detach_audit(
    audit: object,
    *,
    attempt_scoped: bool,
) -> dict[str, object]:
    if not isinstance(audit, Mapping):
        raise _spec_error(
            "artifact audit manifest must be a JSON object",
            "invalid_artifact_audit",
        )
    try:
        raw_audit = cast("Mapping[object, object]", audit)
        if any(not isinstance(key, str) for key in raw_audit):
            raise TypeError("audit keys must be strings")
        encoded = canonical_payload(cast("Mapping[str, object]", raw_audit)).json_bytes
    except (TypeError, ValueError, ExperimentSpecError) as exc:
        raise _spec_error(
            "artifact audit manifest is not canonical JSON",
            "invalid_artifact_audit",
        ) from exc
    detached = cast("dict[str, object]", orjson.loads(encoded))
    required = {"created_at"}
    if attempt_scoped:
        required.update(("run_id", "attempt_id"))
    missing = sorted(required - detached.keys())
    if missing:
        raise _spec_error(
            "artifact audit manifest omits required identity fields",
            "artifact_audit_identity_missing",
            missing_fields=missing,
        )
    return detached


def _validate_audit_identity(
    audit: Mapping[str, object],
    *,
    experiment_id: ExperimentId,
    candidate_id: CandidateId | None,
    fold_id: FoldId | None,
    attempt_id: AttemptId | None,
    reproduction_fingerprint: ContentHash,
) -> None:
    expected_lineage = {
        "experiment_id": str(experiment_id),
        "candidate_id": None if candidate_id is None else str(candidate_id),
        "fold_id": None if fold_id is None else str(fold_id),
        "attempt_id": None if attempt_id is None else str(attempt_id),
    }
    for field_name, expected in expected_lineage.items():
        if field_name in audit and audit[field_name] != expected:
            raise _spec_error(
                "artifact audit lineage contradicts artifact identity",
                "artifact_audit_lineage_mismatch",
                field_name=field_name,
            )
    if audit.get("reproduction_fingerprint", str(reproduction_fingerprint)) != str(
        reproduction_fingerprint
    ):
        raise _spec_error(
            "artifact audit fingerprint contradicts semantic identity",
            "artifact_audit_fingerprint_mismatch",
        )
    if "run_id" in audit:
        _identity(audit["run_id"], "audit.run_id")


def _normalize_audit_timestamp(
    audit: dict[str, object],
    created_at: datetime,
) -> None:
    raw_created_at = audit["created_at"]
    try:
        if not isinstance(raw_created_at, str):
            raise TypeError("audit timestamp must be a string")
        parsed = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
        require_utc_datetime(parsed, "audit.created_at")
    except (TypeError, ValueError, ExperimentSpecError) as exc:
        raise _spec_error(
            "artifact audit timestamp is not strict UTC RFC3339",
            "invalid_artifact_audit",
        ) from exc
    if parsed != created_at:
        raise _spec_error(
            "artifact audit timestamp contradicts typed timestamp",
            "artifact_audit_timestamp_mismatch",
        )
    audit["created_at"] = created_at.isoformat()


class ArtifactFormat(StrEnum):
    """Supported immutable artifact encodings."""

    JSON = "json"
    PARQUET = "parquet"


@dataclass(frozen=True, slots=True)
class ArtifactPublicationSpec:
    """Lineage, path, audit, and semantic identity frozen before file I/O."""

    artifact_id: str
    experiment_id: ExperimentId
    candidate_id: CandidateId | None
    fold_id: FoldId | None
    attempt_id: AttemptId | None
    artifact_kind: str
    relative_path: str
    reproduction_fingerprint: ContentHash
    audit: Mapping[str, object]
    created_at: datetime

    def __post_init__(self) -> None:
        """Reject incomplete lineage, noncanonical paths, and non-JSON audit data."""
        _identity(self.artifact_id, "artifact_id")
        _identity(self.artifact_kind, "artifact_kind")
        _validate_lineage_contract(
            self.experiment_id,
            self.candidate_id,
            self.fold_id,
            self.attempt_id,
            self.reproduction_fingerprint,
        )
        _require_lineage_path(
            self.relative_path,
            experiment_id=self.experiment_id,
            candidate_id=self.candidate_id,
            fold_id=self.fold_id,
            attempt_id=self.attempt_id,
        )
        require_utc_datetime(self.created_at, "created_at")
        detached = _detach_audit(
            self.audit,
            attempt_scoped=self.attempt_id is not None,
        )
        _validate_audit_identity(
            detached,
            experiment_id=self.experiment_id,
            candidate_id=self.candidate_id,
            fold_id=self.fold_id,
            attempt_id=self.attempt_id,
            reproduction_fingerprint=self.reproduction_fingerprint,
        )
        _normalize_audit_timestamp(detached, self.created_at)
        object.__setattr__(self, "audit", _deep_freeze(detached))


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    """Versioned immutable descriptor persisted beside indexed measurements."""

    spec: ArtifactPublicationSpec
    artifact_format: ArtifactFormat
    content_hash: ContentHash
    schema_hash: ContentHash
    row_count: int
    byte_size: int

    @classmethod
    def create(
        cls,
        *,
        spec: ArtifactPublicationSpec,
        artifact_format: ArtifactFormat,
        content_hash: ContentHash,
        schema_hash: ContentHash,
        row_count: int,
        byte_size: int,
    ) -> ArtifactManifest:
        """Build a validated manifest from measurements of closed file bytes."""
        if type(spec) is not ArtifactPublicationSpec:
            raise _spec_error(
                "artifact publication spec is invalid",
                "invalid_artifact_manifest",
            )
        if type(artifact_format) is not ArtifactFormat:
            raise _spec_error(
                "artifact format is invalid",
                "invalid_artifact_manifest",
            )
        if (
            type(content_hash) is not ContentHash
            or type(schema_hash) is not ContentHash
        ):
            raise _spec_error(
                "artifact hashes must be full SHA-256 identities",
                "invalid_artifact_measurement",
            )
        if (
            type(row_count) is not int
            or row_count < 0
            or type(byte_size) is not int
            or byte_size < 0
        ):
            raise _spec_error(
                "artifact row count and byte size must be nonnegative integers",
                "invalid_artifact_measurement",
            )
        expected_suffix = f".{artifact_format.value}"
        if not spec.relative_path.endswith(expected_suffix):
            raise _spec_error(
                "artifact path suffix does not match its format",
                "artifact_format_path_mismatch",
                expected_suffix=expected_suffix,
            )
        return cls(
            spec=spec,
            artifact_format=artifact_format,
            content_hash=content_hash,
            schema_hash=schema_hash,
            row_count=row_count,
            byte_size=byte_size,
        )

    @property
    def reproduction_fingerprint(self) -> ContentHash:
        """Return the already-authoritative research execution fingerprint."""
        return self.spec.reproduction_fingerprint

    @property
    def audit(self) -> Mapping[str, object]:
        """Return attempt/run/time evidence without mixing it into semantics."""
        return self.spec.audit

    def _base_payload(self) -> dict[str, object]:
        return {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "format": self.artifact_format.value,
            "artifact_id": self.spec.artifact_id,
            "artifact_kind": self.spec.artifact_kind,
            "relative_path": self.spec.relative_path,
            "created_at": self.spec.created_at.isoformat(),
            "lineage": {
                "experiment_id": str(self.spec.experiment_id),
                "candidate_id": None
                if self.spec.candidate_id is None
                else str(self.spec.candidate_id),
                "fold_id": None
                if self.spec.fold_id is None
                else str(self.spec.fold_id),
                "attempt_id": None
                if self.spec.attempt_id is None
                else str(self.spec.attempt_id),
            },
            "reproduction_fingerprint": str(self.spec.reproduction_fingerprint),
            "content": {
                "content_hash": str(self.content_hash),
                "schema_hash": str(self.schema_hash),
                "row_count": self.row_count,
                "byte_size": self.byte_size,
            },
            "audit": orjson.loads(canonical_payload(self.spec.audit).json_bytes),
        }

    @property
    def manifest_content_hash(self) -> ContentHash:
        """Hash the complete manifest body, including audit identity."""
        return canonical_payload(self._base_payload()).content_hash

    @property
    def payload(self) -> Mapping[str, object]:
        """Return the versioned canonical payload stored in Schema v1 JSON."""
        return {
            **self._base_payload(),
            "manifest_content_hash": str(self.manifest_content_hash),
        }

    def to_record(self) -> ArtifactRecord:
        """Create the unpinned revision-zero Schema v1 index record."""
        return ArtifactRecord(
            artifact_id=self.spec.artifact_id,
            experiment_id=self.spec.experiment_id,
            candidate_id=self.spec.candidate_id,
            fold_id=self.spec.fold_id,
            attempt_id=self.spec.attempt_id,
            artifact_kind=self.spec.artifact_kind,
            relative_path=self.spec.relative_path,
            content_hash=self.content_hash,
            schema_hash=self.schema_hash,
            row_count=self.row_count,
            byte_size=self.byte_size,
            reproduction_fingerprint=self.spec.reproduction_fingerprint,
            manifest=self.payload,
            is_pinned=False,
            pinned_at=None,
            created_at=self.spec.created_at,
            revision=0,
        )

    @classmethod
    def from_record(cls, record: ArtifactRecord) -> ArtifactManifest:
        """Cross-check every manifest field against immutable index columns."""
        try:
            payload = record.manifest
            if frozenset(payload) != _MANIFEST_KEYS:
                raise ValueError("unexpected manifest fields")
            if payload["schema_version"] != _MANIFEST_SCHEMA_VERSION:
                raise ValueError("unknown manifest schema")
            raw_lineage = payload["lineage"]
            raw_content = payload["content"]
            raw_audit = payload["audit"]
            if not all(
                isinstance(section, Mapping)
                for section in (raw_lineage, raw_content, raw_audit)
            ):
                raise TypeError("manifest sections must be objects")
            audit = cast("Mapping[str, object]", raw_audit)
            manifest = cls.create(
                spec=ArtifactPublicationSpec(
                    artifact_id=record.artifact_id,
                    experiment_id=record.experiment_id,
                    candidate_id=record.candidate_id,
                    fold_id=record.fold_id,
                    attempt_id=record.attempt_id,
                    artifact_kind=record.artifact_kind,
                    relative_path=record.relative_path,
                    reproduction_fingerprint=record.reproduction_fingerprint,
                    audit=audit,
                    created_at=record.created_at,
                ),
                artifact_format=ArtifactFormat(cast("str", payload["format"])),
                content_hash=record.content_hash,
                schema_hash=record.schema_hash,
                row_count=record.row_count,
                byte_size=record.byte_size,
            )
        except (KeyError, TypeError, ValueError, ExperimentSpecError) as exc:
            raise _integrity_error(
                "persisted artifact manifest is invalid",
                "invalid_artifact_manifest",
                artifact_id=record.artifact_id,
            ) from exc
        if payload != manifest.payload:
            raise _integrity_error(
                "artifact manifest does not match immutable index columns",
                "artifact_manifest_mismatch",
                artifact_id=record.artifact_id,
            )
        return manifest
