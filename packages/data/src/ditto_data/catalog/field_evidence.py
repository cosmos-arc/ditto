"""Field-scoped facts frozen and reviewed with a dataset certification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal


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
    consumer_fields: tuple[str, ...] = ()

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
        for value in (self.available_at, self.publication_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("certified field visibility must be timezone-aware")
        if self.time_precision not in {"timestamp", "date", "unknown"}:
            raise ValueError("invalid certified field time precision")


def field_to_payload(value: CertifiedField) -> dict[str, object]:
    """Serialize evidence without coupling it to the report identity codec."""
    return {
        "consumer_fields": value.consumer_fields,
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
    return CertifiedField(
        consumer_fields=tuple(value.get("consumer_fields", ())),
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
