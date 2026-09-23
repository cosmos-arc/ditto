"""ETF exposure and comparable tool evidence from an explicit source snapshot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from math import isfinite
from statistics import median
from typing import Any

from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.services.metadata_service import MetadataService

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)

_FIELDS = (
    "tracking_index",
    "asset_class",
    "fund_currency",
    "trading_currency",
    "aum",
    "management_fee",
    "custody_fee",
    "daily_amount",
    "trading_restriction",
    "distribution",
    "price_close",
    "nav",
    "iopv",
)
_NUMERIC = frozenset(
    {
        "aum",
        "management_fee",
        "custody_fee",
        "daily_amount",
        "price_close",
        "nav",
        "iopv",
    }
)
_LIQUIDITY_DAYS = 20


@dataclass(frozen=True)
class ETFField:
    """One field with its visibility and missing-data evidence."""

    value: str | float | None
    unit: str | None
    observed_on: str | None
    published_at: str | None
    source: str | None
    source_snapshot_id: str | None
    eligibility: str | None
    missing_reason: str | None
    eligibility_reasons: tuple[str, ...] = ()
    sample_count: int | None = None
    effective_from: str | None = None
    effective_to: str | None = None


@dataclass(frozen=True)
class ETFCandidate:
    """A real instrument and its comparable reference fields."""

    instrument_id: int
    ticker: str
    name: str
    exchange: str
    is_active: bool
    fields: dict[str, ETFField]


class ETFCandidateQuery:
    """Read-only application projection. The result never grants trading eligibility."""

    def __init__(
        self,
        metadata: MetadataService,
        admission: FieldAdmissionQuery | None = None,
        snapshots: ProviderSnapshotReader | None = None,
    ) -> None:
        self._metadata = metadata
        self._admission = admission
        self._snapshots = snapshots

    def snapshots(self, *, cutoff: str) -> list[str]:
        """List reference snapshot identities visible by the cutoff."""
        _validate_cutoff(cutoff)
        return self._metadata.instrument.list_etf_reference_snapshots(cutoff=cutoff)

    def list_candidates(
        self,
        *,
        asof: str,
        cutoff: str,
        source_snapshot_id: str,
        exposure: str | None = None,
        asset_exposure: str | None = None,
        search: str | None = None,
        sort_field: str = "ticker",
    ) -> list[ETFCandidate]:
        """Project candidates using exact evidence and a fixed research time."""
        decision_day = date.fromisoformat(asof)
        if _validate_cutoff(cutoff).date() < decision_day:
            raise AppQueryError("knowledge cutoff must not precede as-of date")
        if not source_snapshot_id:
            raise AppQueryError("source snapshot is required")
        if sort_field not in {
            "ticker",
            "aum",
            "management_fee",
            "custody_fee",
            "daily_amount",
        }:
            raise AppQueryError("unsupported ETF sort field")
        identities, observations = self._metadata.instrument.find_etf_reference(
            asof=asof, cutoff=cutoff, source_snapshot_id=source_snapshot_id
        )
        sessions = self._metadata.list_trading_days(
            (decision_day - timedelta(days=60)).isoformat(), asof
        )[-_LIQUIDITY_DAYS:]
        by_instrument: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for row in observations:
            field = str(row["field"])
            if field in _FIELDS:
                by_instrument.setdefault(int(row["instrument_id"]), {}).setdefault(
                    field, []
                ).append(row)
        candidates: list[ETFCandidate] = []
        for identity in identities:
            instrument_id = int(identity["instrument_id"])
            name = str(identity["name"] or "")
            ticker = str(identity["ticker"])
            if search and search.casefold() not in f"{ticker} {name}".casefold():
                continue
            rows = by_instrument.get(instrument_id, {})
            fields = {
                field: _field(rows.get(field, []), numeric=field in _NUMERIC)
                for field in _FIELDS
                if field != "daily_amount"
            }
            fields["daily_amount"] = _liquidity(rows.get("daily_amount", []), sessions)
            fields = {
                field_name: self._admit(
                    field_name,
                    field,
                    instrument_id=instrument_id,
                    cutoff=cutoff,
                    liquidity_start=sessions[0]
                    if len(sessions) == _LIQUIDITY_DAYS
                    else None,
                )
                for field_name, field in fields.items()
            }
            tracking = fields["tracking_index"].value
            if (exposure and tracking != exposure) or (
                asset_exposure and fields["asset_class"].value != asset_exposure
            ):
                continue
            candidates.append(
                ETFCandidate(
                    instrument_id=instrument_id,
                    ticker=ticker,
                    name=name,
                    exchange=str(identity["exchange"]),
                    is_active=bool(identity["is_active"]),
                    fields=fields,
                )
            )
        if sort_field == "ticker":
            return sorted(
                candidates, key=lambda item: (item.ticker, item.instrument_id)
            )
        return sorted(
            candidates,
            key=lambda item: (
                item.fields[sort_field].value is None,
                item.fields[sort_field].value
                if item.fields[sort_field].value is not None
                else float("inf"),
                item.instrument_id,
            ),
        )

    def _admit(
        self,
        field_name: str,
        field: ETFField,
        *,
        instrument_id: int,
        cutoff: str,
        liquidity_start: str | None,
    ) -> ETFField:
        """Apply reviewed display permission when an exact catalog snapshot exists."""
        if (
            field.value is None
            or field.source_snapshot_id is None
            or field.observed_on is None
        ):
            return field
        if self._admission is None or self._snapshots is None:
            return replace(field, eligibility_reasons=("ADMISSION_UNAVAILABLE",))
        snapshot = self._snapshots.get_snapshot(field.source_snapshot_id)
        if snapshot is None:
            return replace(field, eligibility_reasons=("SNAPSHOT_NOT_REGISTERED",))
        required_from = (
            date.fromisoformat(liquidity_start)
            if field_name == "daily_amount" and liquidity_start is not None
            else date.fromisoformat(field.observed_on)
        )
        required_to = date.fromisoformat(field.observed_on)
        report = self._admission.assess(
            FieldAdmissionRequest(
                fields=(
                    FieldRequirement(
                        dataset_id=snapshot.dataset_id,
                        field=field_name,
                        snapshot_id=field.source_snapshot_id,
                    ),
                ),
                instrument_ids=(instrument_id,),
                required_from=required_from,
                required_to=required_to,
                knowledge_cutoff=_validate_cutoff(cutoff),
                publication_cutoff=_validate_cutoff(cutoff),
                purpose="display",
            )
        )
        if report.allowed:
            return replace(field, eligibility="display_allowed")
        return replace(
            field,
            value=None,
            eligibility="display_denied",
            eligibility_reasons=report.fields[0].reason_codes,
            missing_reason="display_admission_denied",
        )


def _field(rows: list[dict[str, Any]], *, numeric: bool) -> ETFField:
    if not rows:
        return ETFField(None, None, None, None, None, None, None, "no_observation")
    row = rows[0]
    value = _number(row["value"]) if numeric else str(row["value"])
    if value is None:
        return ETFField(
            None, None, None, None, None, None, None, "invalid_numeric_observation"
        )
    return ETFField(
        value=value,
        unit=str(row["unit"]),
        observed_on=str(row["observed_on"]),
        published_at=str(row["published_at"]),
        source=str(row["source"]),
        source_snapshot_id=str(row["source_snapshot_id"]),
        eligibility="unverified",
        missing_reason=None,
        effective_from=str(row["effective_from"]),
        effective_to=(
            str(row["effective_to"]) if row["effective_to"] is not None else None
        ),
    )


def _validate_cutoff(value: str) -> datetime:
    """Require canonical UTC timestamps so SQLite comparisons preserve time order."""
    parsed = datetime.fromisoformat(value)
    offset = parsed.utcoffset()
    if (
        parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value
        or offset is None
        or offset.total_seconds() != 0
    ):
        raise AppQueryError(
            "knowledge cutoff must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)"
        )
    return parsed


def _liquidity(rows: list[dict[str, Any]], sessions: list[str]) -> ETFField:
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_date.setdefault(str(row["observed_on"]), row)
    sample = [by_date[day] for day in sessions if day in by_date]
    if len(sessions) != _LIQUIDITY_DAYS or len(sample) != _LIQUIDITY_DAYS:
        return ETFField(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "incomplete_20_session_window",
            sample_count=len(sample),
        )
    if len({str(row["unit"]) for row in sample}) != 1:
        return ETFField(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "inconsistent_amount_unit",
            sample_count=_LIQUIDITY_DAYS,
        )
    values = [_number(row["value"]) for row in sample]
    if any(value is None for value in values):
        return ETFField(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "invalid_amount_observation",
            sample_count=sum(value is not None for value in values),
        )
    latest = sample[-1]
    return ETFField(
        value=median(value for value in values if value is not None),
        unit=str(latest["unit"]),
        observed_on=str(latest["observed_on"]),
        published_at=str(latest["published_at"]),
        source=str(latest["source"]),
        source_snapshot_id=str(latest["source_snapshot_id"]),
        eligibility="unverified",
        missing_reason=None,
        sample_count=_LIQUIDITY_DAYS,
    )


def _number(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None
