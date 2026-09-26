"""Source-bound market candles for the instrument chart."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
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
    snapshot_observed_by,
)
from ditto_application.queries.technical_analysis_source import (
    AdjustmentFactor,
    ProviderPayloadTechnicalAnalysisSource,
    SuspensionEvidence,
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


def _snapshot_observed_at(
    snapshots: ProviderSnapshotReader, snapshot_id: str, cutoff: datetime
) -> datetime:
    snapshot = snapshots.get_snapshot(snapshot_id)
    if snapshot is None:
        raise AppQueryError("contributing chart snapshot is unavailable")
    return snapshot_observed_by(snapshot, cutoff)


def _chart_rows(
    raw: tuple[TechnicalBar, ...],
    snapshots: ProviderSnapshotReader,
    calendar: RetainedCalendarWindow,
    request: MarketChartRequest,
    as_of: datetime,
    factors: dict[str, AdjustmentFactor],
    suspensions: dict[str, SuspensionEvidence],
) -> tuple[tuple[MarketChartBar, ...], tuple[str, ...], str | None]:
    """Select visible sessions, then aggregate complete or partial periods."""
    days = set(calendar.days)
    by_day: dict[str, TechnicalBar] = {}
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
        if previous is None or _snapshot_observed_at(
            snapshots, bar.source_snapshot_id, as_of
        ) > _snapshot_observed_at(snapshots, previous.source_snapshot_id, as_of):
            by_day[day] = bar
    visible_days = [
        day
        for day in calendar.days
        if max(request.start_date, request.listed_on or request.start_date).isoformat()
        <= day
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
        contributing_suspensions = [
            evidence
            for day, evidence in suspensions.items()
            if day in calendar.days
            and max(period_start, request.listed_on or period_start).isoformat()
            <= day
            <= min(
                period_end,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else period_end,
            ).isoformat()
            and day not in by_day
            and _period_key(date.fromisoformat(day), request.period)
            == _period_key(date.fromisoformat(first_day), request.period)
        ]
        complete_calendar = calendar_has_complete_authority(
            calendar,
            max(period_start, request.listed_on or period_start).isoformat(),
            min(
                period_end,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else period_end,
            ).isoformat(),
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
        contributing_factors = (
            [factors[day] for day, _ in group]
            + ([factors[max(by_day)]] if request.adjustment == "qfq" else [])
            if request.adjustment != "none"
            else []
        )
        bar_snapshot_ids = (
            {bar.source_snapshot_id for _, bar in group}
            | {item.snapshot_id for item in contributing_suspensions}
            | {item.snapshot_id for item in contributing_factors}
        )
        calendar_ids = {
            snapshot_id
            for day, snapshot_id in calendar.authority.items()
            if max(period_start, request.listed_on or period_start).isoformat()
            <= day
            <= min(
                period_end,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else period_end,
            ).isoformat()
        }
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
                source_snapshot_ids=tuple(sorted(bar_snapshot_ids)),
                available_at=max(
                    [bar.knowledge_at for _, bar in group]
                    + [
                        _snapshot_observed_at(snapshots, item, as_of)
                        for item in bar_snapshot_ids | calendar_ids
                    ]
                    + [item.available_at for item in contributing_suspensions]
                    + [item.available_at for item in contributing_factors]
                ),
                published_at=max(
                    [bar.publication_at for _, bar in group]
                    + [item.published_at for item in contributing_suspensions]
                    + [item.published_at for item in contributing_factors]
                ),
                partial=partial,
            )
        )
    return tuple(result), missing, max(by_day, default=None)


def _snapshot_matches_instrument(
    item: ProviderSnapshot,
    start_date: date,
    end_date: date,
    ticker_at: Callable[[str, date], str | None],
) -> bool:
    tickers = {
        key.removeprefix("source_ticker=")
        for key in item.canonical_asset.partition_keys
        if key.startswith("source_ticker=")
    }
    if not tickers:
        return True  # Market-wide requests are filtered at the row boundary.
    first = max(start_date, date.fromisoformat(item.request_start))
    last = min(end_date, date.fromisoformat(item.request_end))
    return any(
        ticker_at(item.source, first + timedelta(days=offset)) in tickers
        for offset in range((last - first).days + 1)
    )


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
        *,
        instrument_id: int,
    ) -> tuple[ProviderSnapshot, ...]:
        @cache
        def ticker_at(source_name: str, day: date) -> str | None:
            return self._metadata.get_source_ticker(
                instrument_id,
                source=source_name,
                asof=day.isoformat(),
                cutoff=cutoff.isoformat(),
            )

        candidates = [
            item
            for item in self._snapshots.list_snapshots(dataset_id=dataset_id)
            if item.created_at <= cutoff
            and (source is None or item.source == source)
            and _snapshot_range(item.request_start) <= end_date.strftime("%Y%m%d")
            and _snapshot_range(item.request_end) >= start_date.strftime("%Y%m%d")
            and _snapshot_matches_instrument(item, start_date, end_date, ticker_at)
        ]
        if not candidates:
            if dataset_id == "stock_status":
                return ()
            raise AppQueryError(
                f"retained chart {dataset_id} snapshots are unavailable at cutoff"
            )
        latest = max(candidates, key=lambda item: snapshot_observed_by(item, cutoff))
        revisions: dict[tuple[str, str, str], ProviderSnapshot] = {}
        for item in candidates:
            if (
                item.schema_version != latest.schema_version
                or item.source != latest.source
            ):
                continue
            key = (item.request_start, item.request_end, item.request_parameters_hash)
            prior = revisions.get(key)
            if prior is None or snapshot_observed_by(
                item, cutoff
            ) > snapshot_observed_by(prior, cutoff):
                revisions[key] = item
        for item in revisions.values():
            if not (item.payload_retained and item.payload_uri) and not (
                item.row_count == 0
                and dict(item.response_metadata).get("snapshot_layer")
                == "verified_empty_provider_observation"
            ):
                raise AppQueryError(
                    "authoritative chart revision has no retained payload"
                )
        return tuple(revisions.values())

    def _load_suspensions(
        self,
        request: MarketChartRequest,
        source: str,
        cutoff: datetime,
        instrument_code: Callable[[date], str | None],
    ) -> tuple[dict[str, SuspensionEvidence], tuple[str, ...]]:
        suspensions: dict[str, SuspensionEvidence] = {}
        snapshot_ids: tuple[str, ...] = ()
        if (
            request.asset_class == "stock"
            and self._market.allows_suspension_evidence(
                allow_experimental_data=request.allow_experimental_data
            )
            and any(
                item.created_at <= cutoff
                and item.source == source
                and _snapshot_range(item.request_start)
                <= request.end_date.strftime("%Y%m%d")
                and _snapshot_range(item.request_end)
                >= request.start_date.strftime("%Y%m%d")
                for item in self._snapshots.list_snapshots(dataset_id="stock_status")
            )
        ):
            status_snapshots = self._select_snapshots(
                "stock_status",
                request.start_date,
                request.end_date,
                cutoff,
                source,
                instrument_id=request.instrument_id,
            )
            if not status_snapshots:
                return {}, ()
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
            if any(item.payload_retained for item in status_snapshots):
                suspensions = self._bars.load_suspensions(
                    status_context,
                    instrument_id=InstrumentId(request.instrument_id),
                    instrument_code=instrument_code,
                )
        return suspensions, snapshot_ids

    def _load_factors(
        self,
        request: MarketChartRequest,
        source: str,
        cutoff: datetime,
        instrument_code: Callable[[date], str | None],
    ) -> tuple[dict[str, AdjustmentFactor], tuple[str, ...]]:
        snapshot_ids: tuple[str, ...] = ()
        factors: dict[str, AdjustmentFactor] = {}
        if request.adjustment != "none":
            self._market.assert_adjustment_allowed(
                allow_experimental_data=request.allow_experimental_data
            )
            factor_snapshots = self._select_snapshots(
                "adj_factor",
                request.start_date,
                request.end_date,
                cutoff,
                source,
                instrument_id=request.instrument_id,
            )
            snapshot_ids = tuple(item.snapshot_id for item in factor_snapshots)
            factor_context = PITQueryContext(
                as_of=cutoff,
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
            factors = (
                self._bars.load_adjustment_factors(
                    factor_context,
                    instrument_id=InstrumentId(request.instrument_id),
                    instrument_code=instrument_code,
                )
                if any(item.payload_retained for item in factor_snapshots)
                else {}
            )
        return factors, snapshot_ids

    def _load_calendar(
        self, request: MarketChartRequest, cutoff: datetime
    ) -> tuple[RetainedCalendarWindow, tuple[str, ...]]:
        first_period_start = max(
            _period_bounds(request.start_date, request.period)[0],
            request.listed_on or _period_bounds(request.start_date, request.period)[0],
        )
        last_period_end = min(
            _period_bounds(request.end_date, request.period)[1],
            request.delisted_on - timedelta(days=1)
            if request.delisted_on
            else _period_bounds(request.end_date, request.period)[1],
        )
        try:
            calendar = retained_calendar_window(
                snapshots=self._snapshots,
                payloads=self._payloads,
                cutoff=cutoff,
                first_day=first_period_start.isoformat(),
                last_day=last_period_end.isoformat(),
                allow_closed_window=True,
            )
        except RetainedCalendarAbsent as error:
            raise AppQueryError(
                "retained chart calendar is unavailable at cutoff"
            ) from error
        if not calendar_has_complete_authority(
            calendar,
            first_period_start.isoformat(),
            min(request.end_date, last_period_end).isoformat(),
        ):
            raise AppQueryError("retained chart calendar has incomplete authority")
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
        return calendar, used_calendar_ids

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
        end_date = min(end_date, as_of.astimezone(_SHANGHAI).date())
        request = replace(request, end_date=end_date)
        if max(start_date, request.listed_on or start_date) > min(
            end_date,
            request.delisted_on - timedelta(days=1)
            if request.delisted_on
            else end_date,
        ):
            return MarketChartView(
                instrument_id=instrument_id,
                period=period,
                adjustment=adjustment,
                as_of=as_of,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
                timezone="Asia/Shanghai",
                calendar_snapshot_ids=(),
                source_snapshot_ids=(),
                sources=(),
                latest_price_date=None,
                stale_reason=None,
                missing_sessions=(),
                bars=(),
            )
        calendar, used_calendar_ids = self._load_calendar(request, cutoff)
        if not any(
            start_date.isoformat() <= day <= end_date.isoformat()
            for day in calendar.days
        ):
            return MarketChartView(
                instrument_id=instrument_id,
                period=period,
                adjustment=adjustment,
                as_of=as_of,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
                timezone="Asia/Shanghai",
                calendar_snapshot_ids=used_calendar_ids,
                source_snapshot_ids=(),
                sources=(),
                latest_price_date=None,
                stale_reason=None,
                missing_sessions=(),
                bars=(),
            )
        selected = self._select_snapshots(
            f"{asset_class}_daily",
            start_date,
            end_date,
            cutoff,
            instrument_id=instrument_id,
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
        raw = (
            self._bars.load(
                context,
                instrument_id=InstrumentId(instrument_id),
                instrument_code=instrument_code,
            )
            if any(item.payload_retained for item in selected)
            else ()
        )
        factors, factor_ids = self._load_factors(
            request, latest.source, cutoff, instrument_code
        )
        queried_snapshot_ids.update(factor_ids)
        suspensions, status_ids = self._load_suspensions(
            request, latest.source, cutoff, instrument_code
        )
        queried_snapshot_ids.update(status_ids)
        result, missing, latest_price_date = _chart_rows(
            raw,
            self._snapshots,
            calendar,
            request,
            as_of,
            factors,
            suspensions,
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
