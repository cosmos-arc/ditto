"""ETF exposure and comparable tool evidence from an explicit source snapshot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from itertools import pairwise
from math import isfinite
from re import fullmatch
from statistics import median
from typing import Any

from ditto_backtest.statistics_alpha import compute_total_return_tracking
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.services.metadata_service import MetadataService

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_application.queries.retained_calendar import (
    RetainedCalendarAbsent,
    retained_trading_days,
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
    "lot_size",
    "tick_size",
    "settlement_cycle",
    "price_limit_pct",
    "commission_rate",
    "min_commission",
    "stamp_duty_rate",
    "transfer_fee_rate",
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
        "lot_size",
        "tick_size",
        "settlement_cycle",
        "price_limit_pct",
        "commission_rate",
        "min_commission",
        "stamp_duty_rate",
        "transfer_fee_rate",
        "nav",
        "iopv",
    }
)
_LIQUIDITY_DAYS = 20
_TRACKING_RETURNS = 252


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
    tracking: ETFTracking | None = None


@dataclass(frozen=True)
class ETFTracking:
    """Aligned total-return comparison with explicit qualification status."""

    status: str
    reason: str | None
    tracking_deviation_pct: float | None = None
    tracking_error_pct: float | None = None
    sample_count: int = 0
    start: str | None = None
    end: str | None = None
    currency: str | None = None
    benchmark_id: str | None = None
    source_snapshot_id: str | None = None
    method: str = (
        "dividend-reinvested NAV total return vs same-currency index total return; "
        "formal results require the same UTC valuation time; "
        "252 aligned daily returns; sample std (ddof=1) * sqrt(252)"
    )


class ETFCandidateQuery:
    """Read-only application projection. The result never grants trading eligibility."""

    def __init__(
        self,
        metadata: MetadataService,
        admission: FieldAdmissionQuery | None = None,
        snapshots: ProviderSnapshotReader | None = None,
        payloads: ProviderPayloadReader | None = None,
    ) -> None:
        self._metadata = metadata
        self._admission = admission
        self._snapshots = snapshots
        self._payloads = payloads

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
        parsed_cutoff = _validate_cutoff(cutoff)
        if parsed_cutoff.date() < decision_day:
            raise AppQueryError("knowledge cutoff must not precede as-of date")
        if not source_snapshot_id:
            raise AppQueryError("source snapshot is required")
        if sort_field not in {
            "ticker",
            "aum",
            "management_fee",
            "custody_fee",
            "daily_amount",
            "tracking_error",
        }:
            raise AppQueryError("unsupported ETF sort field")
        calendar = self._retained_calendar(parsed_cutoff)
        tracking_days = _calendar_window(calendar, decision_day, 550)[
            -(_TRACKING_RETURNS + 1) :
        ]
        identities, observations = self._metadata.instrument.find_etf_reference(
            asof=asof,
            cutoff=cutoff,
            source_snapshot_id=source_snapshot_id,
            observed_since=tracking_days[0] if tracking_days else asof,
        )
        sessions = _calendar_window(calendar, decision_day, 60)[-_LIQUIDITY_DAYS:]
        by_instrument: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for row in observations:
            field = str(row["field"])
            if field in _FIELDS or field in {
                "nav_total_return",
                "benchmark_total_return",
            }:
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
                    tracking=self._tracking(
                        rows,
                        tracking_days,
                        fields["tracking_index"],
                        instrument_id=instrument_id,
                        cutoff=cutoff,
                        source_snapshot_id=source_snapshot_id,
                    ),
                )
            )
        return _sort_candidates(candidates, sort_field)

    def _retained_calendar(self, cutoff: datetime) -> list[str]:
        """Read open sessions only from calendar evidence visible at the cutoff."""
        if self._snapshots is None or self._payloads is None:
            raise AppQueryError("ETF evaluation calendar is absent at the cutoff")
        try:
            return retained_trading_days(
                snapshots=self._snapshots, payloads=self._payloads, cutoff=cutoff
            )
        except RetainedCalendarAbsent as exc:
            raise AppQueryError(
                "ETF evaluation calendar is absent at the cutoff"
            ) from exc

    def _tracking(
        self,
        rows: dict[str, list[dict[str, Any]]],
        sessions: list[str],
        relation: ETFField,
        *,
        instrument_id: int,
        cutoff: str,
        source_snapshot_id: str,
    ) -> ETFTracking:
        if not isinstance(relation.value, str):
            return ETFTracking("unavailable", "tracking_index_unavailable")
        if len(sessions) != _TRACKING_RETURNS + 1:
            return ETFTracking("unavailable", "insufficient_trading_sessions")
        if relation.effective_from is None or relation.effective_from > sessions[0]:
            return ETFTracking("unavailable", "tracking_relation_changed")
        fund = {
            str(row["observed_on"]): row for row in rows.get("nav_total_return", [])
        }
        benchmark = {
            str(row["observed_on"]): row
            for row in rows.get("benchmark_total_return", [])
        }
        common = [day in fund and day in benchmark for day in sessions]
        if not all(common):
            missing_fund = any(day not in fund for day in sessions)
            missing_benchmark = any(day not in benchmark for day in sessions)
            reason = (
                "fund_and_benchmark_total_return_missing"
                if missing_fund and missing_benchmark
                else "fund_nav_total_return_missing"
                if missing_fund
                else "benchmark_total_return_missing"
            )
            return ETFTracking(
                "unavailable",
                reason,
                sample_count=sum(left and right for left, right in pairwise(common)),
                start=sessions[1],
                end=sessions[-1],
                benchmark_id=relation.value,
                source_snapshot_id=source_snapshot_id,
            )
        fund_rows = [fund[day] for day in sessions]
        benchmark_rows = [benchmark[day] for day in sessions]
        status, reason = self._tracking_qualification(
            fund_rows,
            benchmark_rows,
            relation,
            instrument_id=instrument_id,
            sessions=sessions,
            cutoff=cutoff,
            source_snapshot_id=source_snapshot_id,
        )
        if status == "unavailable":
            return ETFTracking(
                status,
                reason,
                sample_count=_TRACKING_RETURNS,
                start=sessions[1],
                end=sessions[-1],
                benchmark_id=relation.value,
                source_snapshot_id=source_snapshot_id,
            )
        return self._tracking_result(
            fund_rows,
            benchmark_rows,
            sessions,
            benchmark_id=relation.value,
            status=status,
            reason=reason,
            source_snapshot_id=source_snapshot_id,
        )

    def _tracking_qualification(
        self,
        fund_rows: list[dict[str, Any]],
        benchmark_rows: list[dict[str, Any]],
        relation: ETFField,
        *,
        instrument_id: int,
        sessions: list[str],
        cutoff: str,
        source_snapshot_id: str,
    ) -> tuple[str, str | None]:
        """Only certified provider fields produce formal metrics."""
        combined = (*fund_rows, *benchmark_rows)
        if source_snapshot_id.startswith("snapshot:recorded:") and all(
            row["source"] == "recorded" for row in combined
        ):
            return "reference_only", "RECORDED_REFERENCE_ONLY"
        if self._admission is None or self._snapshots is None:
            return "unavailable", "ADMISSION_UNAVAILABLE"
        snapshot = self._snapshots.get_snapshot(source_snapshot_id)
        if snapshot is None:
            return "unavailable", "SNAPSHOT_NOT_REGISTERED"
        if relation.eligibility != "display_allowed" or any(
            row["source"] != snapshot.source for row in combined
        ):
            return "unavailable", "source_or_display_admission_denied"
        report = self._admission.assess(
            FieldAdmissionRequest(
                fields=tuple(
                    FieldRequirement(snapshot.dataset_id, field, source_snapshot_id)
                    for field in (
                        "tracking_index",
                        "nav_total_return",
                        "benchmark_total_return",
                    )
                ),
                instrument_ids=(instrument_id,),
                required_from=date.fromisoformat(sessions[0]),
                required_to=date.fromisoformat(sessions[-1]),
                knowledge_cutoff=_validate_cutoff(cutoff),
                publication_cutoff=_validate_cutoff(cutoff),
                purpose="formal_research",
            )
        )
        return (
            ("comparable", None)
            if report.allowed
            else ("unavailable", "formal_admission_denied")
        )

    def _tracking_result(
        self,
        fund_rows: list[dict[str, Any]],
        benchmark_rows: list[dict[str, Any]],
        sessions: list[str],
        *,
        benchmark_id: str,
        status: str,
        reason: str | None,
        source_snapshot_id: str,
    ) -> ETFTracking:
        """Compute two 252-return series after qualifying their source."""
        evidence: dict[str, Any] = {
            "sample_count": _TRACKING_RETURNS,
            "start": sessions[1],
            "end": sessions[-1],
            "benchmark_id": benchmark_id,
            "source_snapshot_id": source_snapshot_id,
        }
        if any(
            row["effective_from"] > row["observed_on"]
            or (
                row["effective_to"] is not None
                and row["effective_to"] <= row["observed_on"]
            )
            for row in (*fund_rows, *benchmark_rows)
        ):
            return ETFTracking(
                "unavailable", "series_effective_interval_mismatch", **evidence
            )
        currency, unit_reason = _tracking_units(
            fund_rows, benchmark_rows, benchmark_id, formal=status == "comparable"
        )
        if unit_reason is not None:
            return ETFTracking("unavailable", unit_reason, **evidence)
        values = [
            [_positive_number(row["value"]) for row in series]
            for series in (fund_rows, benchmark_rows)
        ]
        if any(value is None for series in values for value in series):
            return ETFTracking(
                "unavailable",
                "invalid_total_return_level",
                currency=currency,
                **evidence,
            )
        fund_levels = [value for value in values[0] if value is not None]
        benchmark_levels = [value for value in values[1] if value is not None]
        try:
            deviation, error = compute_total_return_tracking(
                fund_levels, benchmark_levels
            )
        except ValueError:
            return ETFTracking(
                "unavailable",
                "invalid_total_return_level",
                currency=currency,
                **evidence,
            )
        return ETFTracking(
            status=status,
            reason=reason,
            tracking_deviation_pct=deviation,
            tracking_error_pct=error,
            sample_count=_TRACKING_RETURNS,
            start=sessions[1],
            end=sessions[-1],
            currency=currency,
            benchmark_id=benchmark_id,
            source_snapshot_id=source_snapshot_id,
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
            return _unregistered(field, "ADMISSION_UNAVAILABLE")
        snapshot = self._snapshots.get_snapshot(field.source_snapshot_id)
        if snapshot is None:
            return _unregistered(field, "SNAPSHOT_NOT_REGISTERED")
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


def _unregistered(field: ETFField, reason: str) -> ETFField:
    if (
        field.source == "recorded"
        and field.source_snapshot_id is not None
        and field.source_snapshot_id.startswith("snapshot:recorded:")
    ):
        return replace(field, eligibility_reasons=("RECORDED_REFERENCE_ONLY",))
    return replace(
        field,
        value=None,
        eligibility="display_denied",
        eligibility_reasons=(reason,),
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


def _calendar_window(days: list[str], asof: date, lookback_days: int) -> list[str]:
    """Cut retained open sessions to the lookback window ending at as-of."""
    start = (asof - timedelta(days=lookback_days)).isoformat()
    return [day for day in days if start <= day <= asof.isoformat()]


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


def _positive_number(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _tracking_units(
    fund_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    benchmark_id: str,
    *,
    formal: bool,
) -> tuple[str | None, str | None]:
    currencies = {
        str(row["unit"]).split(":", 1)[0] for row in (*fund_rows, *benchmark_rows)
    }
    if len(currencies) != 1 or not next(iter(currencies)):
        return None, "currency_or_benchmark_mismatch"
    currency = next(iter(currencies))
    fund_prefix = f"{currency}:nav_total_return"
    benchmark_prefix = f"{currency}:index_total_return:{benchmark_id}"
    fund_units = {str(row["unit"]) for row in fund_rows}
    benchmark_units = {str(row["unit"]) for row in benchmark_rows}
    if any(not unit.startswith(fund_prefix) for unit in fund_units) or any(
        not unit.startswith(benchmark_prefix) for unit in benchmark_units
    ):
        return None, "currency_or_benchmark_mismatch"
    fund_valuations = {unit.removeprefix(fund_prefix) for unit in fund_units}
    benchmark_valuations = {
        unit.removeprefix(benchmark_prefix) for unit in benchmark_units
    }
    if len(fund_valuations) != 1 or fund_valuations != benchmark_valuations:
        return None, "valuation_time_not_aligned"
    valuation = next(iter(fund_valuations))
    if (formal or valuation) and not fullmatch(
        r":valuation=([01][0-9]|2[0-3]):[0-5][0-9]Z", valuation
    ):
        return None, "valuation_time_not_aligned"
    return currency, None


def _sort_candidates(
    candidates: list[ETFCandidate], sort_field: str
) -> list[ETFCandidate]:
    if sort_field == "ticker":
        return sorted(candidates, key=lambda item: (item.ticker, item.instrument_id))
    if sort_field == "tracking_error":
        return sorted(
            candidates,
            key=lambda item: (
                item.tracking is None or item.tracking.status != "comparable",
                item.tracking.tracking_error_pct
                if item.tracking is not None
                and item.tracking.tracking_error_pct is not None
                else float("inf"),
                item.instrument_id,
            ),
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
