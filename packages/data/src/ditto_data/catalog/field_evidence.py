"""Field-scoped facts frozen and reviewed with a dataset certification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from typing import Any, Literal
from zoneinfo import ZoneInfo

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
    observed_at: datetime | None = None
    revised_at: datetime | None = None
    date_visible_at: datetime | None = None
    calendar_hash: str | None = None
    calendar_evidence: tuple[str, ...] = ()

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
        for value in (
            self.available_at,
            self.publication_at,
            self.observed_at,
            self.revised_at,
            self.date_visible_at,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("certified field visibility must be timezone-aware")
        if self.time_precision not in {"timestamp", "date", "unknown"}:
            raise ValueError("invalid certified field time precision")
        _validate_calendar_evidence(self)

    def disclosure_date(self) -> date:
        """Date-only publication is interpreted in the market's explicit timezone."""
        if self.publication_at is None:
            raise ValueError("publication evidence is missing")
        return self.publication_at.astimezone(ZoneInfo("Asia/Shanghai")).date()


def field_to_payload(value: CertifiedField) -> dict[str, object]:
    """Serialize evidence without coupling it to the report identity codec."""
    payload: dict[str, object] = {
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

    # Omit unknown additions so legacy report identities remain unchanged.
    for key in ("observed_at", "revised_at", "date_visible_at"):
        timestamp = getattr(value, key)
        if timestamp is not None:
            payload[key] = timestamp.isoformat()
    if value.calendar_hash is not None:
        payload["calendar_hash"] = value.calendar_hash
    if value.calendar_evidence:
        payload["calendar_evidence"] = value.calendar_evidence
    return payload


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
        observed_at=datetime.fromisoformat(value["observed_at"])
        if value.get("observed_at")
        else None,
        revised_at=datetime.fromisoformat(value["revised_at"])
        if value.get("revised_at")
        else None,
        date_visible_at=datetime.fromisoformat(value["date_visible_at"])
        if value.get("date_visible_at")
        else None,
        calendar_hash=value.get("calendar_hash"),
        calendar_evidence=tuple(value.get("calendar_evidence", ())),
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


def _validate_calendar_evidence(field: CertifiedField) -> None:
    if (
        field.date_visible_at is None
        and field.calendar_hash is None
        and not field.calendar_evidence
    ):
        return
    if (
        field.time_precision != "date"
        or field.publication_at is None
        or field.available_at is None
        or not field.calendar_evidence
    ):
        raise ValueError(
            "date visibility requires source times and retained calendar evidence"
        )
    disclosed = field.disclosure_date()
    boundary, digest = publication_calendar_boundary(disclosed, field.calendar_evidence)
    if field.date_visible_at != boundary or field.calendar_hash != digest:
        raise ValueError("date visibility does not match retained calendar evidence")


def publication_calendar_boundary(
    disclosed: date, evidence: tuple[str, ...]
) -> tuple[datetime, str]:
    """Validate and address a complete daily calendar through the next open."""
    if not evidence:
        raise ValueError("publication calendar evidence is missing")
    expected = disclosed + timedelta(days=1)
    for index, item in enumerate(evidence):
        final = index == len(evidence) - 1
        if item != f"{expected.isoformat()}:{int(final)}":
            raise ValueError("publication calendar evidence is incomplete")
        if not final:
            expected += timedelta(days=1)
    boundary = datetime.combine(expected, time(9, 30), ZoneInfo("Asia/Shanghai"))
    digest = sha256(
        ("SSE:Asia/Shanghai:09:30:v1|" + "|".join(evidence)).encode()
    ).hexdigest()
    return boundary, digest
