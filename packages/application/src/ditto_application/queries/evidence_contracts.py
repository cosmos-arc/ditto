"""Application-owned contracts for immutable, PIT-bound evidence reads."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import cast

import orjson

from ditto_application.exceptions import AppQueryError

__all__ = [
    "EvidenceArtifactReference",
    "EvidencePayloadReadModel",
    "EvidenceTemporalContext",
    "EvidenceValue",
]

type EvidenceScalar = str | bool | int | float | None
type EvidenceValue = (
    EvidenceScalar | tuple[EvidenceValue, ...] | Mapping[str, EvidenceValue]
)

_SHA256_HEX_LENGTH = 64


def _evidence_error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"evidence query failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _evidence_error(
            "EVIDENCE_IDENTITY_REQUIRED",
            "missing_or_noncanonical_identity",
            field=field_name,
        )
    return value


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _evidence_error(
            "EVIDENCE_TEMPORAL_INVALID",
            "timestamp_must_be_utc",
            field=field_name,
        )
    return value.astimezone(UTC)


def _sha256_hex(value: object, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name)
    if len(text) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise _evidence_error(
            "EVIDENCE_PROVENANCE_INCOMPLETE",
            "invalid_sha256",
            field=field_name,
        )
    return text


@dataclass(frozen=True, slots=True)
class EvidenceTemporalContext:
    """Exact visibility boundary supplied by the trusted application caller."""

    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_id: str

    def __post_init__(self) -> None:
        """Normalize UTC boundaries and reject incomplete snapshot identity."""
        decision = _utc(self.decision_time, field_name="decision_time")
        knowledge = _utc(self.knowledge_cutoff, field_name="knowledge_cutoff")
        publication = _utc(
            self.publication_cutoff,
            field_name="publication_cutoff",
        )
        if not publication <= knowledge <= decision:
            raise _evidence_error(
                "EVIDENCE_TEMPORAL_INVALID",
                "publication_cutoff_must_precede_knowledge_and_decision",
            )
        object.__setattr__(self, "decision_time", decision)
        object.__setattr__(self, "knowledge_cutoff", knowledge)
        object.__setattr__(self, "publication_cutoff", publication)
        object.__setattr__(
            self,
            "source_snapshot_id",
            _required_text(
                self.source_snapshot_id,
                field_name="source_snapshot_id",
            ),
        )


@dataclass(frozen=True, slots=True)
class EvidenceArtifactReference:
    """Content-addressed artifact reference without a physical storage path."""

    artifact_id: str
    artifact_kind: str
    content_hash: str
    schema_hash: str | None = None

    def __post_init__(self) -> None:
        """Validate content-addressed identity without accepting storage paths."""
        object.__setattr__(
            self,
            "artifact_id",
            _required_text(self.artifact_id, field_name="artifact_id"),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            _required_text(self.artifact_kind, field_name="artifact_kind"),
        )
        object.__setattr__(
            self,
            "content_hash",
            _sha256_hex(self.content_hash, field_name="content_hash"),
        )
        if self.schema_hash is not None:
            object.__setattr__(
                self,
                "schema_hash",
                _sha256_hex(self.schema_hash, field_name="schema_hash"),
            )


@dataclass(frozen=True, slots=True)
class EvidencePayloadReadModel:
    """Deep-frozen JSON payload plus its deterministic content digest."""

    schema_version: int
    value: Mapping[str, EvidenceValue]
    payload_hash: str

    @classmethod
    def seal(
        cls,
        *,
        schema_version: int,
        value: Mapping[str, object],
    ) -> EvidencePayloadReadModel:
        """Normalize, hash, and deep-freeze an application evidence payload."""
        if isinstance(schema_version, bool) or schema_version < 1:
            raise _evidence_error(
                "EVIDENCE_PAYLOAD_INVALID",
                "invalid_schema_version",
            )
        normalized = _normalize_value(value, field_name="payload")
        if not isinstance(normalized, Mapping):
            raise _evidence_error(
                "EVIDENCE_PAYLOAD_INVALID",
                "payload_must_be_mapping",
            )
        mutable = _mutable_value(normalized)
        digest = sha256(
            orjson.dumps(
                {
                    "schema_version": schema_version,
                    "value": mutable,
                },
                option=orjson.OPT_SORT_KEYS,
            )
        ).hexdigest()
        return cls(
            schema_version=schema_version,
            value=cast("Mapping[str, EvidenceValue]", normalized),
            payload_hash=digest,
        )


def _normalize_value(value: object, *, field_name: str) -> EvidenceValue:
    if value is None or isinstance(value, (str, bool, int)):
        normalized: EvidenceValue = value
    elif isinstance(value, float):
        normalized = _finite_float(value, field_name=field_name)
    elif isinstance(value, datetime):
        normalized = (
            _utc(value, field_name=field_name).isoformat().replace("+00:00", "Z")
        )
    elif isinstance(value, date):
        normalized = value.isoformat()
    elif isinstance(value, Enum):
        normalized = _normalize_value(value.value, field_name=field_name)
    elif is_dataclass(value) and not isinstance(value, type):
        normalized = _normalize_value(
            {item.name: getattr(value, item.name) for item in fields(value)},
            field_name=field_name,
        )
    elif isinstance(value, Mapping):
        normalized = _normalize_mapping(
            cast("Mapping[object, object]", value),
            field_name=field_name,
        )
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        sequence = cast("Sequence[object]", value)
        normalized = tuple(
            _normalize_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(sequence)
        )
    else:
        raise _evidence_error(
            "EVIDENCE_PAYLOAD_INVALID",
            "unsupported_payload_value",
            field=field_name,
            value_type=type(value).__name__,
        )
    return normalized


def _finite_float(value: float, *, field_name: str) -> float:
    if not math.isfinite(value):
        raise _evidence_error(
            "EVIDENCE_PAYLOAD_INVALID",
            "non_finite_number",
            field=field_name,
        )
    return value


def _normalize_mapping(
    value: Mapping[object, object],
    *,
    field_name: str,
) -> Mapping[str, EvidenceValue]:
    frozen: dict[str, EvidenceValue] = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        if not isinstance(key, str) or not key:
            raise _evidence_error(
                "EVIDENCE_PAYLOAD_INVALID",
                "invalid_mapping_key",
                field=field_name,
            )
        frozen[key] = _normalize_value(item, field_name=f"{field_name}.{key}")
    return MappingProxyType(frozen)


def _mutable_value(value: EvidenceValue) -> object:
    if isinstance(value, Mapping):
        return {key: _mutable_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable_value(item) for item in value]
    return value
