"""Source-bound market candles for the instrument chart."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo

from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.retained_calendar import (
    RetainedCalendarAbsent,
    RetainedCalendarWindow,
    calendar_has_complete_authority,
    retained_calendar_window,
)
from ditto_application.queries.technical_analysis_source import (
    AdjustmentFactor,
    ProviderPayloadTechnicalAnalysisSource,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_MAX_CHART_RANGE_DAYS = 3660


@dataclass(frozen=True)
class MarketChartRequest:
    """One chart identity and its server-supplied decision clock."""

    instrument_id: int
    asset_class: str
    start_date: date
    end_date: date
    period: str
    adjustment: str
    allow_experimental_data: bool
    now: datetime
    listed_on: date | None = None
    delisted_on: date | None = None


@dataclass(frozen=True)
class MarketChartBar:
    """One calendar-bound price period with exact source revisions."""

    trade_date: str
    first_trade_date: str
    last_trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source_snapshot_ids: tuple[str, ...]
    available_at: datetime
    published_at: datetime
    partial: bool


@dataclass(frozen=True)
class MarketChartView:
    """Chart result and the complete cutoff and calendar identity."""

    instrument_id: int
    period: str
    adjustment: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    timezone: str
    calendar_snapshot_ids: tuple[str, ...]
    source_snapshot_ids: tuple[str, ...]
    sources: tuple[str, ...]
    latest_price_date: str | None
    stale_reason: str | None
    missing_sessions: tuple[str, ...]
    bars: tuple[MarketChartBar, ...]


def _period_key(day: date, period: str) -> tuple[int, int]:
    if period == "weekly":
        iso = day.isocalendar()
        return iso.year, iso.week
    if period == "monthly":
        return day.year, day.month
    return day.year, day.toordinal()


def _period_bounds(day: date, period: str) -> tuple[date, date]:
    if period == "weekly":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        start = day.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, next_month - timedelta(days=1)
    return day, day


def _snapshot_range(value: str) -> str:
    return value.replace("-", "")


def _chart_rows(
    raw: tuple[TechnicalBar, ...],
    selected: tuple[ProviderSnapshot, ...],
    calendar: RetainedCalendarWindow,
    request: MarketChartRequest,
    as_of: datetime,
    factors: dict[str, AdjustmentFactor],
    suspensions: dict[str, str],
) -> tuple[tuple[MarketChartBar, ...], tuple[str, ...], str | None]:
    """Select visible sessions, then aggregate complete or partial periods."""
    days = set(calendar.days)
    by_day: dict[str, TechnicalBar] = {}
    observed = {item.snapshot_id: item for item in selected}
    for bar in raw:
        day = bar.occurred_at.astimezone(_SHANGHAI).date().isoformat()
        if (
            day
            < max(
                request.start_date, request.listed_on or request.start_date
            ).isoformat()
            or day
            > min(
                request.end_date,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else request.end_date,
            ).isoformat()
        ):
            continue
        if day not in days:
            raise AppQueryError("chart bar is outside the retained trading calendar")
        previous = by_day.get(day)
        if (
            previous is None
            or observed[bar.source_snapshot_id].created_at
            > observed[previous.source_snapshot_id].created_at
        ):
            by_day[day] = bar
    coverage_start = min(_snapshot_range(item.request_start) for item in selected)
    visible_days = [
        day
        for day in calendar.days
        if max(request.start_date, request.listed_on or request.start_date).isoformat()
        <= day
        and day.replace("-", "") >= coverage_start
        and day
        <= min(
            request.end_date.isoformat(),
            as_of.astimezone(_SHANGHAI).date().isoformat(),
            (
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else request.end_date
            ).isoformat(),
        )
    ]
    missing = tuple(
        day
        for day in visible_days
        if day not in by_day
        and day not in suspensions
        and datetime.combine(date.fromisoformat(day), time(15), _SHANGHAI).astimezone(
            UTC
        )
        <= as_of
    )
    grouped: dict[tuple[int, int], list[tuple[str, TechnicalBar]]] = {}
    for day, bar in sorted(by_day.items()):
        grouped.setdefault(
            _period_key(date.fromisoformat(day), request.period), []
        ).append((day, bar))
    if request.adjustment != "none" and any(day not in factors for day in by_day):
        raise AppQueryError("exact adjustment factor missing for a chart price day")
    baseline = factors[max(by_day)].value if by_day and factors else 1.0

    def multiplier(day: str) -> float:
        if request.adjustment == "none":
            return 1.0
        factor = factors[day].value
        return factor / baseline if request.adjustment == "qfq" else factor

    result: list[MarketChartBar] = []
    for group in grouped.values():
        first_day, first = group[0]
        last_day, last = group[-1]
        period_start, period_end = _period_bounds(
            date.fromisoformat(first_day), request.period
        )
        expected = [
            day
            for day in calendar.days
            if max(period_start, request.listed_on or period_start).isoformat()
            <= day
            <= min(
                period_end,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else period_end,
            ).isoformat()
            and day not in suspensions
        ]
        complete_calendar = calendar_has_complete_authority(
            calendar, period_start.isoformat(), period_end.isoformat()
        )
        partial = (
            not complete_calendar
            or any(day not in by_day for day in expected)
            or (
                datetime.combine(
                    date.fromisoformat(expected[-1]), time(15), _SHANGHAI
                ).astimezone(UTC)
                > as_of
                if expected
                else True
            )
        )
        result.append(
            MarketChartBar(
                trade_date=last_day,
                first_trade_date=first_day,
                last_trade_date=last_day,
                open=first.open * multiplier(first_day),
                high=max(bar.high * multiplier(day) for day, bar in group),
                low=min(bar.low * multiplier(day) for day, bar in group),
                close=last.close * multiplier(last_day),
                volume=sum(bar.volume for _, bar in group),
                amount=sum(bar.turnover for _, bar in group),
                source_snapshot_ids=tuple(
                    sorted(
                        {bar.source_snapshot_id for _, bar in group}
                        | (
                            {factors[day].snapshot_id for day, _ in group}
                            if request.adjustment != "none"
                            else set()
                        )
                    )
                ),
                available_at=max(
                    [bar.knowledge_at for _, bar in group]
                    + (
                        [factors[day].available_at for day, _ in group]
                        if request.adjustment != "none"
                        else []
                    )
                ),
                published_at=max(
                    [bar.publication_at for _, bar in group]
                    + (
                        [factors[day].published_at for day, _ in group]
                        if request.adjustment != "none"
                        else []
                    )
                ),
                partial=partial,
            )
        )
    return tuple(result), missing, max(by_day, default=None)


class MarketChartQueryFacade:
    """Read exact retained bars and calendar under one server-owned cutoff."""

    def __init__(
        self,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        metadata: MetadataQueryFacade,
        market: MarketQueryFacade,
    ) -> None:
        self._snapshots = snapshots
        self._payloads = payloads
        self._metadata = metadata
        self._market = market
        self._bars = ProviderPayloadTechnicalAnalysisSource(
            snapshot_reader=snapshots, payload_reader=payloads
        )

    def _select_snapshots(
        self,
        dataset_id: str,
        start_date: date,
        end_date: date,
        cutoff: datetime,
        source: str | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        candidates = [
            item
            for item in self._snapshots.list_snapshots(dataset_id=dataset_id)
            if item.payload_retained
            and item.payload_uri
            and item.created_at <= cutoff
            and (source is None or item.source == source)
            and _snapshot_range(item.request_start) <= end_date.strftime("%Y%m%d")
            and _snapshot_range(item.request_end) >= start_date.strftime("%Y%m%d")
        ]
        if not candidates:
            raise AppQueryError(
                f"retained chart {dataset_id} snapshots are unavailable at cutoff"
            )
        latest = max(candidates, key=lambda item: item.created_at)
        return tuple(
            item
            for item in candidates
            if item.schema_version == latest.schema_version
            and item.source == latest.source
        )

    def _load_suspensions(
        self,
        request: MarketChartRequest,
        source: str,
        cutoff: datetime,
        instrument_code: Callable[[date], str | None],
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        suspensions: dict[str, str] = {}
        snapshot_ids: tuple[str, ...] = ()
        if request.asset_class == "stock" and any(
            item.payload_retained
            and item.payload_uri
            and item.created_at <= cutoff
            and item.source == source
            and _snapshot_range(item.request_start)
            <= request.end_date.strftime("%Y%m%d")
            and _snapshot_range(item.request_end)
            >= request.start_date.strftime("%Y%m%d")
            for item in self._snapshots.list_snapshots(dataset_id="stock_status")
        ):
            status_snapshots = self._select_snapshots(
                "stock_status", request.start_date, request.end_date, cutoff, source
            )
            snapshot_ids = tuple(item.snapshot_id for item in status_snapshots)
            status_context = PITQueryContext(
                as_of=cutoff,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
                source_snapshots=(
                    DatasetSnapshot(
                        dataset_id="stock_status",
                        dataset_version=status_snapshots[0].schema_version,
                        source_snapshot_ids=tuple(
                            item.snapshot_id for item in status_snapshots
                        ),
                        created_at=max(item.created_at for item in status_snapshots),
                    ),
                ),
            )
            suspensions = self._bars.load_suspensions(
                status_context,
                instrument_id=InstrumentId(request.instrument_id),
                instrument_code=instrument_code,
            )
        return suspensions, snapshot_ids

    def get_chart(self, request: MarketChartRequest) -> MarketChartView:
        """Return only bars visible in retained payloads at the chart cutoff."""
        instrument_id = request.instrument_id
        asset_class = request.asset_class
        start_date = request.start_date
        end_date = request.end_date
        period = request.period
        adjustment = request.adjustment
        allow_experimental_data = request.allow_experimental_data
        now = request.now
        if period not in {"daily", "weekly", "monthly"}:
            raise AppQueryError("unsupported chart period")
        if adjustment not in {"none", "qfq", "hfq"} or (
            asset_class == "etf" and adjustment != "none"
        ):
            raise AppQueryError("unsupported source-bound chart adjustment")
        if asset_class not in {"stock", "etf"}:
            raise AppQueryError("source-bound chart supports stock and ETF only")
        if (
            start_date > end_date
            or (end_date - start_date).days > _MAX_CHART_RANGE_DAYS
        ):
            raise AppQueryError("invalid chart date range")
        if now.tzinfo is None:
            raise AppQueryError("chart decision time must include UTC offset")
        self._market.assert_bars_allowed(
            asset_class=asset_class,
            instrument_id=instrument_id,
            allow_experimental_data=allow_experimental_data,
        )
        as_of = now.astimezone(UTC)
        cutoff = as_of
        selected = self._select_snapshots(
            f"{asset_class}_daily", start_date, end_date, cutoff
        )
        latest = max(selected, key=lambda item: item.created_at)
        queried_snapshot_ids = {item.snapshot_id for item in selected}

        @cache
        def instrument_code(day: date) -> str | None:
            return self._metadata.get_source_ticker(
                instrument_id,
                source=latest.source,
                asof=day.isoformat(),
                cutoff=cutoff.isoformat(),
            )

        context = PITQueryContext(
            as_of=as_of,
            knowledge_cutoff=cutoff,
            publication_cutoff=cutoff,
            source_snapshots=(
                DatasetSnapshot(
                    dataset_id=f"{asset_class}_daily",
                    dataset_version=latest.schema_version,
                    source_snapshot_ids=tuple(item.snapshot_id for item in selected),
                    created_at=max(item.created_at for item in selected),
                ),
            ),
        )
        raw = self._bars.load(
            context,
            instrument_id=InstrumentId(instrument_id),
            instrument_code=instrument_code,
        )
        factors: dict[str, AdjustmentFactor] = {}
        if adjustment != "none":
            self._market.assert_adjustment_allowed(
                allow_experimental_data=allow_experimental_data
            )
            factor_snapshots = self._select_snapshots(
                "adj_factor", start_date, end_date, cutoff, latest.source
            )
            queried_snapshot_ids.update(item.snapshot_id for item in factor_snapshots)
            factor_context = PITQueryContext(
                as_of=as_of,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
                source_snapshots=(
                    DatasetSnapshot(
                        dataset_id="adj_factor",
                        dataset_version=factor_snapshots[0].schema_version,
                        source_snapshot_ids=tuple(
                            item.snapshot_id for item in factor_snapshots
                        ),
                        created_at=max(item.created_at for item in factor_snapshots),
                    ),
                ),
            )
            factors = self._bars.load_adjustment_factors(
                factor_context,
                instrument_id=InstrumentId(instrument_id),
                instrument_code=instrument_code,
            )
        suspensions, status_ids = self._load_suspensions(
            request, latest.source, cutoff, instrument_code
        )
        queried_snapshot_ids.update(status_ids)
        first_period_start = _period_bounds(start_date, period)[0]
        last_period_end = _period_bounds(end_date, period)[1]
        try:
            calendar = retained_calendar_window(
                snapshots=self._snapshots,
                payloads=self._payloads,
                cutoff=cutoff,
                first_day=first_period_start.isoformat(),
                last_day=last_period_end.isoformat(),
            )
        except RetainedCalendarAbsent as error:
            raise AppQueryError(
                "retained chart calendar is unavailable at cutoff"
            ) from error
        if not calendar_has_complete_authority(
            calendar, first_period_start.isoformat(), end_date.isoformat()
        ):
            raise AppQueryError("retained chart calendar has incomplete authority")
        result, missing, latest_price_date = _chart_rows(
            raw, selected, calendar, request, as_of, factors, suspensions
        )
        used_calendar_ids = tuple(
            sorted(
                {
                    calendar.authority[day]
                    for day in calendar.authority
                    if first_period_start.isoformat()
                    <= day
                    <= last_period_end.isoformat()
                }
            )
        )
        stale_reason = (
            "no_visible_price"
            if latest_price_date is None and missing
            else "missing_expected_session"
            if latest_price_date and any(day > latest_price_date for day in missing)
            else None
        )
        return MarketChartView(
            instrument_id=instrument_id,
            period=period,
            adjustment=adjustment,
            as_of=as_of,
            knowledge_cutoff=cutoff,
            publication_cutoff=cutoff,
            timezone="Asia/Shanghai",
            calendar_snapshot_ids=used_calendar_ids,
            source_snapshot_ids=tuple(sorted(queried_snapshot_ids)),
            sources=tuple(sorted({item.source for item in selected})),
            latest_price_date=latest_price_date,
            stale_reason=stale_reason,
            missing_sessions=missing,
            bars=tuple(result),
        )
