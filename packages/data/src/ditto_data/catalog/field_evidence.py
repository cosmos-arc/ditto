"""Field-scoped facts frozen and reviewed with a dataset certification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Literal

import orjson


@dataclass(frozen=True, slots=True)
class CertifiedField:
    """
    Scope and conservative visibility bounds supported by addressed evidence.

    Timestamps are the latest constraints across this entire certified scope.
    Date-only source evidence must first be resolved using the trading calendar;
    missing bounds remain unknown and cannot authorize historical consumption.
    """

    field: str
    snapshot_id: str
    instrument_ids: tuple[int, ...]
    covered_from: date
    covered_to: date
    available_at: datetime | None
    publication_at: datetime | None
    time_precision: Literal["timestamp", "date", "unknown"]
    evidence_uri: str
    consumer_bindings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Reject ambiguous scope or naive visibility constraints."""
        for value in (self.field, self.snapshot_id, self.evidence_uri):
            if not value or value.strip() != value:
                raise ValueError("certified field identity and evidence are required")
        if self.covered_to < self.covered_from:
            raise ValueError("certified field interval is reversed")
        if not self.instrument_ids or len(set(self.instrument_ids)) != len(
            self.instrument_ids
        ):
            raise ValueError("certified field requires unique explicit instruments")
        if any(isinstance(value, bool) or value <= 0 for value in self.instrument_ids):
            raise ValueError(
                "certified instruments must be positive integer identities"
            )
        _validate_consumer_bindings(self.consumer_bindings)
        for value in (self.available_at, self.publication_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("certified field visibility must be timezone-aware")
        if self.time_precision not in {"timestamp", "date", "unknown"}:
            raise ValueError("invalid certified field time precision")


def field_to_payload(value: CertifiedField) -> dict[str, object]:
    """Serialize evidence without coupling it to the report identity codec."""
    return {
        "consumer_bindings": value.consumer_bindings,
        "field": value.field,
        "snapshot_id": value.snapshot_id,
        "instrument_ids": value.instrument_ids,
        "covered_from": value.covered_from.isoformat(),
        "covered_to": value.covered_to.isoformat(),
        "available_at": value.available_at.isoformat() if value.available_at else None,
        "publication_at": value.publication_at.isoformat()
        if value.publication_at
        else None,
        "time_precision": value.time_precision,
        "evidence_uri": value.evidence_uri,
    }


def field_from_payload(value: dict[str, Any]) -> CertifiedField:
    """Restore frozen field facts; legacy reports have no such facts."""
    if any(not isinstance(item, int) for item in value["instrument_ids"]):
        raise ValueError("certified instruments must be integer identities")
    return CertifiedField(
        consumer_bindings=tuple(
            tuple(item) for item in value.get("consumer_bindings", ())
        ),
        field=value["field"],
        snapshot_id=value["snapshot_id"],
        instrument_ids=tuple(value["instrument_ids"]),
        covered_from=date.fromisoformat(value["covered_from"]),
        covered_to=date.fromisoformat(value["covered_to"]),
        available_at=datetime.fromisoformat(value["available_at"])
        if value["available_at"]
        else None,
        publication_at=datetime.fromisoformat(value["publication_at"])
        if value["publication_at"]
        else None,
        time_precision=value["time_precision"],
        evidence_uri=value["evidence_uri"],
    )


def consumer_input_digest(payload: object) -> str:
    """Address a normalized consumer input and its complete dependency group."""
    return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _validate_consumer_bindings(bindings: tuple[tuple[str, str], ...]) -> None:
    if len(set(bindings)) != len(bindings):
        raise ValueError("duplicate consumer input binding")
    for name, digest in bindings:
        if (
            not name
            or name.strip() != name
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("consumer input binding must have a name and SHA-256")
