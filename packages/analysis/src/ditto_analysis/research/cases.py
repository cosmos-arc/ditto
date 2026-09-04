"""Immutable Research Case contracts derived from exact product evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId

__all__ = ["ResearchCase"]

_SHA256_LENGTH = 64
_SCHEMA_VERSION = 1
_ASSET_KINDS = frozenset({"stock", "etf"})
_USABLE_SELECTION_STATUSES = frozenset({"ready", "degraded"})


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty unpadded string")
    return value


def _hash(value: object, *, field_name: str) -> str:
    text = _text(value, field_name=field_name)
    if len(text) != _SHA256_LENGTH or any(
        char not in "0123456789abcdef" for char in text
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _text_set(values: object, *, field_name: str, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    normalized = tuple(
        sorted(
            (
                _text(item, field_name=field_name)
                for item in cast(tuple[object, ...], values)
            ),
            key=str.encode,
        )
    )
    if (not allow_empty and not normalized) or len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must contain unique canonical identities")
    return normalized


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _temporal_lineage(
    as_of: object,
    knowledge_cutoff: object,
    publication_cutoff: object,
) -> tuple[datetime, datetime, datetime]:
    normalized_as_of = _utc(as_of, field_name="as_of")
    normalized_knowledge = _utc(knowledge_cutoff, field_name="knowledge_cutoff")
    normalized_publication = _utc(
        publication_cutoff,
        field_name="publication_cutoff",
    )
    if (
        normalized_knowledge > normalized_as_of
        or normalized_publication > normalized_knowledge
    ):
        raise ValueError("Research Case temporal lineage must be PIT visible")
    return normalized_as_of, normalized_knowledge, normalized_publication


def _candidate_ids(values: object) -> tuple[InstrumentId, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError("candidate_instrument_ids must be a non-empty tuple")
    raw_values = cast(tuple[object, ...], values)
    if any(type(value) is not int for value in raw_values):
        raise ValueError("candidate_instrument_ids must contain integer identities")
    raw_ids = cast(tuple[int, ...], raw_values)
    if any(value <= 0 for value in raw_ids) or len(set(raw_ids)) != len(raw_ids):
        raise ValueError("candidate_instrument_ids must be unique positive identities")
    return tuple(InstrumentId(value) for value in raw_ids)


def _selection_completeness(status: str, missing_inputs: object) -> tuple[str, ...]:
    if status not in _USABLE_SELECTION_STATUSES:
        raise ValueError("selection_status must be ready or degraded")
    missing = _text_set(
        missing_inputs,
        field_name="missing_inputs",
        allow_empty=True,
    )
    if status == "ready" and missing:
        raise ValueError("ready selection cannot carry missing_inputs")
    return missing


@dataclass(frozen=True, slots=True)
class ResearchCase:
    """One hypothesis bound to an immutable SelectionRun evidence boundary."""

    selection_run_id: str
    selection_run_hash: str
    selection_input_hash: str
    selection_spec_hash: str
    objective: str
    asset_kind: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    candidate_instrument_ids: tuple[InstrumentId, ...]
    selection_status: str
    missing_inputs: tuple[str, ...]
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Fail closed on erased selection, PIT, snapshot, or candidate lineage."""
        if (
            type(self.schema_version) is not int
            or self.schema_version != _SCHEMA_VERSION
        ):
            raise ValueError("unsupported Research Case schema_version")
        run_hash = _hash(self.selection_run_hash, field_name="selection_run_hash")
        run_id = _text(self.selection_run_id, field_name="selection_run_id")
        if run_id != f"selection-run:sha256:{run_hash}":
            raise ValueError("selection_run_id does not match selection_run_hash")
        for field_name in ("selection_input_hash", "selection_spec_hash"):
            _hash(getattr(self, field_name), field_name=field_name)
        object.__setattr__(
            self,
            "objective",
            _text(self.objective, field_name="objective"),
        )
        if self.asset_kind not in _ASSET_KINDS:
            raise ValueError("asset_kind must be stock or etf")
        as_of, knowledge_cutoff, publication_cutoff = _temporal_lineage(
            self.as_of,
            self.knowledge_cutoff,
            self.publication_cutoff,
        )
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "knowledge_cutoff", knowledge_cutoff)
        object.__setattr__(self, "publication_cutoff", publication_cutoff)
        object.__setattr__(
            self,
            "universe_snapshot_id",
            _text(self.universe_snapshot_id, field_name="universe_snapshot_id"),
        )
        if self.industry_rotation_snapshot_id is not None:
            object.__setattr__(
                self,
                "industry_rotation_snapshot_id",
                _text(
                    self.industry_rotation_snapshot_id,
                    field_name="industry_rotation_snapshot_id",
                ),
            )
        object.__setattr__(
            self,
            "source_snapshot_ids",
            _text_set(
                self.source_snapshot_ids,
                field_name="source_snapshot_ids",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "candidate_instrument_ids",
            _candidate_ids(self.candidate_instrument_ids),
        )
        object.__setattr__(
            self,
            "missing_inputs",
            _selection_completeness(self.selection_status, self.missing_inputs),
        )

    @property
    def canonical_payload(self) -> dict[str, object]:
        """Return the complete deterministic lineage preimage."""
        return {
            "schema_version": self.schema_version,
            "selection_run_id": self.selection_run_id,
            "selection_run_hash": self.selection_run_hash,
            "selection_input_hash": self.selection_input_hash,
            "selection_spec_hash": self.selection_spec_hash,
            "objective": self.objective,
            "asset_kind": self.asset_kind,
            "as_of": _timestamp(self.as_of),
            "knowledge_cutoff": _timestamp(self.knowledge_cutoff),
            "publication_cutoff": _timestamp(self.publication_cutoff),
            "universe_snapshot_id": self.universe_snapshot_id,
            "industry_rotation_snapshot_id": self.industry_rotation_snapshot_id,
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "candidate_instrument_ids": [
                int(value) for value in self.candidate_instrument_ids
            ],
            "selection_status": self.selection_status,
            "missing_inputs": list(self.missing_inputs),
        }

    @property
    def content_hash(self) -> str:
        """Return the full SHA-256 hash of the canonical lineage payload."""
        encoded = orjson.dumps(self.canonical_payload, option=orjson.OPT_SORT_KEYS)
        return hashlib.sha256(encoded).hexdigest()

    @property
    def case_id(self) -> str:
        """Return the stable content-addressed Research Case identity."""
        return f"research-case:sha256:{self.content_hash}"
