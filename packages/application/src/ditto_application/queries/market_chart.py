"""Source-bound market candles for the instrument chart."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from functools import cache, partial
from typing import NamedTuple
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
    calendar_has_single_source,
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
    exchange: str = "SSE"


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


def _require_chart_ticker(value: str | None) -> str:
    if value is None:
        raise AppQueryError("effective chart ticker mapping is unavailable")
    return value


def _snapshot_observed_at(
    snapshots: ProviderSnapshotReader, snapshot_id: str, cutoff: datetime
) -> datetime:
    snapshot = snapshots.get_snapshot(snapshot_id)
    if snapshot is None:
        raise AppQueryError("contributing chart snapshot is unavailable")
    return snapshot_observed_by(snapshot, cutoff)


def _observed_at_reader(
    snapshots: ProviderSnapshotReader, as_of: datetime
) -> Callable[[str], datetime]:
    """
    Resolve each snapshot's observation time once per request.

    Candles share the same contributing snapshot set, so resolving per bar
    and per candle would re-read every snapshot from the reader thousands
    of times on a long daily range.
    """
    resolved: dict[str, datetime] = {}

    def observed_at(snapshot_id: str) -> datetime:
        if snapshot_id not in resolved:
            resolved[snapshot_id] = _snapshot_observed_at(snapshots, snapshot_id, as_of)
        return resolved[snapshot_id]

    return observed_at


class _SnapshotIndex(NamedTuple):
    """Per-request snapshot lookups resolved once for all candles."""

    observed_at: Callable[[str], datetime]
    absence_sources: tuple[ProviderSnapshot, ...]


def _qfq_baseline_day(
    request: MarketChartRequest,
    days: set[str],
    as_of: datetime,
    factors: dict[str, AdjustmentFactor],
) -> str | None:
    """
    Resolve the QFQ baseline as the anchor session's own factor.

    The anchor is the latest eligible open session, not merely the latest
    factor date: a corporate action on the anchor session rescales every
    earlier candle, so its factor must be covered or we fail closed instead
    of silently scaling against a stale baseline. Non-QFQ charts have no
    baseline.
    """
    if request.adjustment != "qfq":
        return None
    anchor_day = max(
        (
            day
            for day in days
            if day
            <= min(
                request.end_date,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else request.end_date,
            ).isoformat()
            and _daily_knowledge_at(date.fromisoformat(day)) <= as_of
        ),
        default=None,
    )
    if anchor_day is None or anchor_day not in factors:
        raise AppQueryError(
            "exact adjustment factor missing for the chart anchor session"
        )
    return anchor_day


def _tied_price_conflicts(
    observed_at: Callable[[str], datetime], bar: TechnicalBar, previous: TechnicalBar
) -> bool:
    """
    Equal observation timestamps do not establish revision order.

    Distinct tied shards for one session leave the chosen bar lineage and
    its knowledge/publication metadata dependent on catalog ordering even
    when the numeric values agree, so any distinct tie fails closed.
    """
    return (
        observed_at(bar.source_snapshot_id) == observed_at(previous.source_snapshot_id)
        and bar.source_snapshot_id != previous.source_snapshot_id
    )


def _require_price_source_factor_basis(
    adjustment: str,
    price_source_snapshot: ProviderSnapshot,
    factor_shards: tuple[ProviderSnapshot, ...],
) -> None:
    """
    Reject factor shards that change the HFQ normalization basis.

    HFQ multiplies the provider's absolute factor, so a factor shard from
    another provider applies a different normalization basis; QFQ ratios stay
    within the factor dataset's own single-source selection and keep the
    fallback-source contract.
    """
    if adjustment == "hfq" and any(
        item.source != price_source_snapshot.source for item in factor_shards
    ):
        raise AppQueryError("hfq factors require the price source basis")


def _visible_bars(
    raw: tuple[TechnicalBar, ...],
    calendar: RetainedCalendarWindow,
    request: MarketChartRequest,
    suspensions: dict[str, SuspensionEvidence],
    observed_at: Callable[[str], datetime],
) -> dict[str, TechnicalBar]:
    """Pick each session's newest observed bar inside the clipped window."""
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
        if day not in days or day in suspensions:
            raise AppQueryError(
                "chart price conflicts with retained full-day suspension"
                if day in suspensions
                else "chart bar is outside the retained trading calendar"
            )
        previous = by_day.get(day)
        if previous is None or observed_at(bar.source_snapshot_id) > observed_at(
            previous.source_snapshot_id
        ):
            by_day[day] = bar
        elif _tied_price_conflicts(observed_at, bar, previous):
            raise AppQueryError("tied price revisions conflict for a chart session")
    return by_day


def _chart_rows(
    raw: tuple[TechnicalBar, ...],
    index: _SnapshotIndex,
    calendar: RetainedCalendarWindow,
    request: MarketChartRequest,
    factors: dict[str, AdjustmentFactor],
    suspensions: dict[str, SuspensionEvidence],
    ticker: Callable[[date], str | None],
) -> tuple[tuple[MarketChartBar, ...], tuple[str, ...], str | None]:
    """Select visible sessions, then aggregate complete or partial periods."""
    as_of = request.now.astimezone(UTC)
    snapshot_observed_at = index.observed_at
    by_day = _visible_bars(raw, calendar, request, suspensions, snapshot_observed_at)
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
        and _daily_knowledge_at(date.fromisoformat(day)) <= as_of
    )
    grouped: dict[tuple[int, int], list[tuple[str, TechnicalBar]]] = {}
    for day, bar in sorted(by_day.items()):
        grouped.setdefault(
            _period_key(date.fromisoformat(day), request.period), []
        ).append((day, bar))
    if request.adjustment != "none" and any(day not in factors for day in by_day):
        raise AppQueryError("exact adjustment factor missing for a chart price day")
    # A full-day suspension has no price bar, so it cannot anchor the QFQ
    # baseline; factor authority already excludes suspended sessions.
    baseline_day = _qfq_baseline_day(
        request, set(calendar.days) - suspensions.keys(), as_of, factors
    )
    baseline = factors[baseline_day].value if baseline_day else 1.0

    def multiplier(day: str) -> float:
        if request.adjustment == "none":
            return 1.0
        factor = factors[day].value
        return factor / baseline if request.adjustment == "qfq" else factor

    result: list[MarketChartBar] = []
    absence_sources = index.absence_sources
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
                _daily_knowledge_at(date.fromisoformat(expected[-1])) > as_of
                if expected
                else True
            )
        )
        contributing_factors = (
            [factors[day] for day, _ in group]
            + (
                [factors[baseline_day]]
                if request.adjustment == "qfq" and baseline_day
                else []
            )
            if request.adjustment != "none"
            else []
        )
        absence_snapshot_ids = {
            item.snapshot_id
            for item in absence_sources
            if any(
                period_start.isoformat() <= day <= period_end.isoformat()
                and _snapshot_range(item.request_start)
                <= day.replace("-", "")
                <= _snapshot_range(item.request_end)
                # Absence lineage must hold for the instrument's effective
                # ticker on the missing day; an old-ticker shard across a
                # rename cannot establish that absence.
                and _absence_scope_matches(item, day, ticker)
                for day in missing
            )
        }
        bar_snapshot_ids = (
            {bar.source_snapshot_id for _, bar in group}
            | {item.snapshot_id for item in contributing_suspensions}
            | {item.snapshot_id for item in contributing_factors}
            | absence_snapshot_ids
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
                        snapshot_observed_at(item)
                        for item in bar_snapshot_ids | calendar_ids
                    ]
                    + [item.available_at for item in contributing_suspensions]
                    + [item.available_at for item in contributing_factors]
                    # A missing session's effect on this candle is knowable
                    # no earlier than its T+1 knowledge time.
                    + [
                        _daily_knowledge_at(date.fromisoformat(day))
                        for day in missing
                        if period_start.isoformat() <= day <= period_end.isoformat()
                    ]
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


def _date_keys(start: date, end: date) -> list[str]:
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _window_hits(sorted_days: list[str], start: str, end: str) -> bool:
    """Whether any sorted compact day falls inside [start, end]."""
    index = bisect_left(sorted_days, start)
    return index < len(sorted_days) and sorted_days[index] <= end


def _window_days(sorted_days: list[str], start: str, end: str) -> list[str]:
    """Sorted compact days inside [start, end] (inclusive)."""
    lo = bisect_left(sorted_days, start)
    hi = bisect_right(sorted_days, end)
    return sorted_days[lo:hi]


def _absence_scope_matches(
    item: ProviderSnapshot, day: str, ticker: Callable[[date], str | None]
) -> bool:
    tickers = {
        key.removeprefix("source_ticker=")
        for key in item.canonical_asset.partition_keys
        if key.startswith("source_ticker=")
    }
    return not tickers or ticker(date.fromisoformat(day)) in tickers


def _snapshot_matches_instrument(
    item: ProviderSnapshot,
    sorted_days: list[str],
    ticker_at: Callable[[str, date], str | None],
) -> bool:
    """
    Match the partition ticker on consumable sessions only.

    A rename visible only on an unclosed day must not admit or require
    mapping for the shard. Sessions are bisected to the shard's own
    request window so scoped shards never walk the full consumable set.
    """
    tickers = {
        key.removeprefix("source_ticker=")
        for key in item.canonical_asset.partition_keys
        if key.startswith("source_ticker=")
    }
    if not tickers:
        return True  # Market-wide requests are filtered at the row boundary.
    return any(
        ticker_at(item.source, date.fromisoformat(day)) in tickers
        for day in _window_days(
            sorted_days,
            _snapshot_range(item.request_start),
            _snapshot_range(item.request_end),
        )
    )


def _daily_knowledge_at(day: date) -> datetime:
    """
    Retained daily datasets are knowable at T+1 15:00 Asia/Shanghai.

    The provider contract stamps knowledge_date = trade_date + 1, so a
    session becomes consumable (and its absence mature) only after that
    knowledge time, not at the market close.
    """
    return datetime.combine(day + timedelta(days=1), time(15), _SHANGHAI).astimezone(
        UTC
    )


def _consumable_sessions(
    calendar: RetainedCalendarWindow, start_date: date, end_date: date, as_of: datetime
) -> frozenset[str]:
    """
    Open sessions in the clipped window whose knowledge time passed as_of.

    A session whose daily bar is not yet knowable cannot consume evidence at
    this cutoff.
    """
    return frozenset(
        day
        for day in calendar.days
        if start_date.isoformat() <= day <= end_date.isoformat()
        and _daily_knowledge_at(date.fromisoformat(day)) <= as_of
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

    def _collapse_revisions(
        self, candidates: list[ProviderSnapshot], cutoff: datetime
    ) -> tuple[ProviderSnapshot, ...]:
        """
        Keep each exact-request key's newest observed revision.

        Tied observation with a distinct snapshot has no PIT revision order;
        catalog iteration must not pick the winning payload. Snapshot
        identity covers source, dataset, bounds, schema version, and
        checksum, so a distinct tied ID always hides a content or schema
        difference even when the payload checksum alone matches.
        """
        revisions: dict[tuple[str, str, str, str], ProviderSnapshot] = {}
        for item in candidates:
            key = (
                item.source,
                item.request_start,
                item.request_end,
                item.request_parameters_hash,
            )
            prior = revisions.get(key)
            if prior is None:
                revisions[key] = item
                continue
            item_observed = snapshot_observed_by(item, cutoff)
            prior_observed = snapshot_observed_by(prior, cutoff)
            if (
                item_observed == prior_observed
                and item.snapshot_id != prior.snapshot_id
            ):
                raise AppQueryError("tied exact-request chart revisions conflict")
            if item_observed > prior_observed:
                revisions[key] = item
        return tuple(revisions.values())

    def _select_snapshots(
        self,
        dataset_id: str,
        start_date: date,
        end_date: date,
        cutoff: datetime,
        *,
        instrument_id: int,
        consumable_days: frozenset[str],
    ) -> tuple[ProviderSnapshot, ...]:
        tickers_for = cache(
            partial(
                self._metadata.get_source_tickers,
                instrument_id,
                asofs=_date_keys(start_date, end_date),
                cutoff=cutoff.isoformat(),
            )
        )

        def ticker_at(source_name: str, day: date) -> str:
            return _require_chart_ticker(
                tickers_for(source=source_name).get(day.isoformat())
            )

        # Only sessions the chart can consume — open inside the request
        # window and already closed by the cutoff — may require evidence;
        # shards scoped to closed days or to today's unclosed session must
        # not join source/schema authority decisions.
        consumable_window_iso = frozenset(
            day
            for day in consumable_days
            if start_date.isoformat() <= day <= end_date.isoformat()
        )
        # Sorted compact sessions let each candidate's bounds intersect the
        # consumable set in O(log n) instead of rescanning every session.
        sorted_window_days = sorted(
            day.replace("-", "") for day in consumable_window_iso
        )
        candidates = [
            item
            for item in self._snapshots.list_snapshots(dataset_id=dataset_id)
            if item.created_at <= cutoff
            and _snapshot_range(item.request_start) <= end_date.strftime("%Y%m%d")
            and _snapshot_range(item.request_end) >= start_date.strftime("%Y%m%d")
            and _window_hits(
                sorted_window_days,
                _snapshot_range(item.request_start),
                _snapshot_range(item.request_end),
            )
            and _snapshot_matches_instrument(item, sorted_window_days, ticker_at)
        ]
        if not candidates:
            if dataset_id == "stock_status":
                return ()
            raise AppQueryError(
                f"retained chart {dataset_id} snapshots are unavailable at cutoff"
            )
        selected = self._collapse_revisions(candidates, cutoff)
        if len({item.source for item in selected}) > 1:
            raise AppQueryError("retained chart shards have incompatible sources")
        if len({item.schema_version for item in selected}) > 1:
            raise AppQueryError("retained chart shards have incompatible schemas")
        for item in selected:
            if not (item.payload_retained and item.payload_uri) and not (
                item.row_count == 0
                and dict(item.response_metadata).get("snapshot_layer")
                == "verified_empty_provider_observation"
            ):
                raise AppQueryError(
                    "authoritative chart revision has no retained payload"
                )
        return selected

    def _instrument_code(
        self,
        request: MarketChartRequest,
        source: str,
        cutoff: datetime,
        calendar: RetainedCalendarWindow,
        consumable_days: frozenset[str],
        *,
        window: tuple[date, date],
    ) -> Callable[[date], str | None]:
        identities = self._metadata.get_source_tickers(
            request.instrument_id,
            source=source,
            asofs=list(calendar.days),
            cutoff=cutoff.isoformat(),
        )

        @cache
        def ticker(day: date) -> str | None:
            day_key = day.isoformat()
            value = (
                identities[day_key]
                if day_key in identities
                else self._metadata.get_source_ticker(
                    request.instrument_id,
                    source=source,
                    asof=day_key,
                    cutoff=cutoff.isoformat(),
                )
            )
            # Fail closed exactly over the authority window the caller reads:
            # a silent None outside the raw request dates would let row
            # filtering drop evidence the chart still consumes.
            if window[0] <= day <= window[1]:
                return _require_chart_ticker(value)
            return value

        # Eager validation covers only consumable sessions; an unclosed
        # session has no readable bar, so a not-yet-visible same-day rename
        # must not fail the valid closed-session history.
        for day in consumable_days:
            ticker(date.fromisoformat(day))
        return ticker

    def _load_suspensions(
        self,
        request: MarketChartRequest,
        cutoff: datetime,
        calendar: RetainedCalendarWindow,
    ) -> tuple[dict[str, SuspensionEvidence], tuple[ProviderSnapshot, ...]]:
        suspensions: dict[str, SuspensionEvidence] = {}
        status_snapshots: tuple[ProviderSnapshot, ...] = ()
        if request.asset_class == "stock" and self._market.allows_suspension_evidence(
            allow_experimental_data=request.allow_experimental_data
        ):
            # Suspension evidence bounds the aggregated periods' expected
            # sessions, which span the natural period and lifecycle bounds
            # rather than the raw request dates; select status authority over
            # that same window so day-scoped suspension shards beyond the
            # requested dates still join, and validate ticker identity over
            # that window so a cutoff-visible mapping gap on a post-request
            # suspension day fails closed instead of silently dropping rows.
            period_start = _period_bounds(request.start_date, request.period)[0]
            period_end = min(
                _period_bounds(request.end_date, request.period)[1],
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else _period_bounds(request.end_date, request.period)[1],
            )
            consumable_days = _consumable_sessions(
                calendar, period_start, period_end, cutoff
            )
            status_snapshots = self._select_snapshots(
                "stock_status",
                period_start,
                period_end,
                cutoff,
                instrument_id=request.instrument_id,
                consumable_days=consumable_days,
            )
            if not status_snapshots:
                return {}, status_snapshots
            instrument_code = self._instrument_code(
                request,
                status_snapshots[0].source,
                cutoff,
                calendar,
                consumable_days,
                window=(
                    max(period_start, request.listed_on or period_start),
                    period_end,
                ),
            )
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
                    window=(period_start, period_end),
                )
        return suspensions, status_snapshots

    def _load_factors(
        self,
        request: MarketChartRequest,
        cutoff: datetime,
        calendar: RetainedCalendarWindow,
        suspensions: dict[str, SuspensionEvidence],
    ) -> tuple[dict[str, AdjustmentFactor], tuple[ProviderSnapshot, ...]]:
        factor_snapshots: tuple[ProviderSnapshot, ...] = ()
        factors: dict[str, AdjustmentFactor] = {}
        if request.adjustment != "none":
            self._market.assert_adjustment_allowed(
                allow_experimental_data=request.allow_experimental_data
            )
            # Factors are consumed only for dates with price bars, so a
            # shard scoped solely to a suspended session — from another
            # source or schema — cannot join factor authority, mirroring
            # price authority.
            consumable_days = (
                _consumable_sessions(
                    calendar, request.start_date, request.end_date, cutoff
                )
                - suspensions.keys()
            )
            factor_snapshots = self._select_snapshots(
                "adj_factor",
                request.start_date,
                request.end_date,
                cutoff,
                instrument_id=request.instrument_id,
                consumable_days=consumable_days,
            )
            instrument_code = self._instrument_code(
                request,
                factor_snapshots[0].source,
                cutoff,
                calendar,
                consumable_days,
                window=(request.start_date, request.end_date),
            )
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
                    window=(request.start_date, request.end_date),
                )
                if any(item.payload_retained for item in factor_snapshots)
                else {}
            )
        return factors, factor_snapshots

    def _reject_suspended_price_conflicts(
        self,
        request: MarketChartRequest,
        cutoff: datetime,
        calendar: RetainedCalendarWindow,
        consumable_days: frozenset[str],
        suspensions: dict[str, SuspensionEvidence],
    ) -> None:
        """
        Fail closed when retained price rows contradict full-day suspensions.

        When every consumable session is suspended, price selection is
        skipped for authority purposes, but a retained nonempty price
        artifact covering those sessions still contradicts the status
        authority: its rows are loaded over the collapsed exact-request
        revisions and run through the same suspension-conflict guard the
        normal path uses. Absence-only polls carry no rows and stay outside
        price authority, so they cannot turn this into a mixed-source
        rejection. No eager ticker mapping is demanded — identity resolves
        lazily per row.
        """
        suspended = consumable_days & suspensions.keys()
        if not suspended:
            return
        dataset = f"{request.asset_class}_daily"
        sorted_suspended = sorted(day.replace("-", "") for day in suspended)
        # Mirror selection's instrument-scope filter with a non-raising
        # resolver: ticker-scoped backfill shards for unrelated instruments
        # cover the dates but prove nothing about this one, and loading
        # their payloads would fail the request on foreign schemas.
        tickers_for = cache(
            partial(
                self._metadata.get_source_tickers,
                request.instrument_id,
                asofs=_date_keys(request.start_date, request.end_date),
                cutoff=cutoff.isoformat(),
            )
        )

        def ticker_at(source_name: str, day: date) -> str | None:
            return tickers_for(source=source_name).get(day.isoformat())

        candidates = [
            item
            for item in self._snapshots.list_snapshots(dataset_id=dataset)
            if item.created_at <= cutoff
            and (
                item.payload_retained
                or (
                    item.row_count == 0
                    and dict(item.response_metadata).get("snapshot_layer")
                    == "verified_empty_provider_observation"
                )
            )
            and _window_hits(
                sorted_suspended,
                _snapshot_range(item.request_start),
                _snapshot_range(item.request_end),
            )
            and _snapshot_matches_instrument(item, sorted_suspended, ticker_at)
        ]
        if not candidates:
            return
        selected = self._collapse_revisions(candidates, cutoff)
        by_source: dict[str, list[ProviderSnapshot]] = {}
        for item in selected:
            by_source.setdefault(item.source, []).append(item)
        for source, group in by_source.items():
            if not any(item.payload_retained for item in group):
                continue
            # Identity resolves per provider: one source's mapping must not
            # silently filter another source's contradictory rows.
            instrument_code = self._instrument_code(
                request,
                source,
                cutoff,
                calendar,
                frozenset(),
                window=(request.start_date, request.end_date),
            )
            context = PITQueryContext(
                as_of=cutoff,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
                source_snapshots=(
                    DatasetSnapshot(
                        dataset_id=dataset,
                        dataset_version=group[0].schema_version,
                        source_snapshot_ids=tuple(item.snapshot_id for item in group),
                        created_at=max(item.created_at for item in group),
                    ),
                ),
            )
            raw = self._bars.load(
                context,
                instrument_id=InstrumentId(request.instrument_id),
                instrument_code=instrument_code,
                window=(request.start_date, request.end_date),
            )
            _visible_bars(
                raw,
                calendar,
                request,
                suspensions,
                _observed_at_reader(self._snapshots, cutoff),
            )

    def _load_visible_factors(
        self,
        request: MarketChartRequest,
        cutoff: datetime,
        calendar: RetainedCalendarWindow,
        suspensions: dict[str, SuspensionEvidence],
        latest: ProviderSnapshot,
        raw: tuple[TechnicalBar, ...],
    ) -> tuple[
        dict[str, AdjustmentFactor], tuple[ProviderSnapshot, ...], MarketChartRequest
    ]:
        """
        Load adjustment factors only when price bars are visible.

        Authoritative price absence leaves nothing to adjust, so the empty
        result never demands factor evidence or a QFQ anchor factor — the
        same behavior as adjustment="none" and the all-suspended branch.
        """
        if raw:
            factors, shards = self._load_factors(request, cutoff, calendar, suspensions)
            _require_price_source_factor_basis(request.adjustment, latest, shards)
            return factors, shards, request
        return {}, (), replace(request, adjustment="none")

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
                exchange=request.exchange,
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
        if not calendar_has_single_source(
            calendar, first_period_start.isoformat(), last_period_end.isoformat()
        ):
            raise AppQueryError("retained chart calendar has incompatible sources")
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
        as_of = now.astimezone(UTC)
        cutoff = as_of
        start_date = max(start_date, request.listed_on or start_date)
        end_date = min(
            end_date,
            as_of.astimezone(_SHANGHAI).date(),
            request.delisted_on - timedelta(days=1)
            if request.delisted_on
            else end_date,
        )
        request = replace(request, start_date=start_date, end_date=end_date)
        if start_date > end_date:
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
            max(start_date, request.listed_on or start_date).isoformat()
            <= day
            <= min(
                end_date,
                request.delisted_on - timedelta(days=1)
                if request.delisted_on
                else end_date,
            ).isoformat()
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
        # No in-range session has closed yet, so no daily bar is knowable:
        # return the calendar-bound empty result before the maturity gate or
        # any retained-price requirement can reject a still-valid request.
        consumable_days = _consumable_sessions(calendar, start_date, end_date, as_of)
        if not consumable_days:
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
        self._market.assert_bars_allowed(
            asset_class=asset_class,
            instrument_id=instrument_id,
            allow_experimental_data=allow_experimental_data,
        )
        # Authoritative suspensions load before price selection: a full-day
        # suspension has no readable bar, so its dates leave price authority
        # coverage and an irrelevant price poll scoped to that day cannot
        # turn a complete candle into a mixed-source rejection.
        suspensions, status_shards = self._load_suspensions(request, cutoff, calendar)
        price_consumable_days = consumable_days - suspensions.keys()
        # A retained nonempty price artifact over suspended sessions still
        # contradicts the status authority in any window — mixed or fully
        # suspended — because a shard scoped only to the suspended day never
        # joins price selection; its rows route through the
        # suspension-conflict guard here.
        self._reject_suspended_price_conflicts(
            request, cutoff, calendar, consumable_days, suspensions
        )
        if not price_consumable_days:
            # Every consumable session is a full-day suspension: no price bar
            # is knowable or required, and the suspension evidence carries
            # the lineage.
            return MarketChartView(
                instrument_id=instrument_id,
                period=period,
                adjustment=adjustment,
                as_of=as_of,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
                timezone="Asia/Shanghai",
                calendar_snapshot_ids=used_calendar_ids,
                source_snapshot_ids=tuple(item.snapshot_id for item in status_shards),
                sources=tuple(sorted({item.source for item in status_shards})),
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
            consumable_days=price_consumable_days,
        )
        latest = max(selected, key=lambda item: item.created_at)
        queried_snapshot_ids = {item.snapshot_id for item in selected}

        instrument_code = self._instrument_code(
            request,
            latest.source,
            cutoff,
            calendar,
            price_consumable_days,
            window=(start_date, end_date),
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
                window=(start_date, end_date),
            )
            if any(item.payload_retained for item in selected)
            else ()
        )
        factors, factor_shards, factor_request = self._load_visible_factors(
            request, cutoff, calendar, suspensions, latest, raw
        )
        queried_snapshot_ids.update(item.snapshot_id for item in factor_shards)
        queried_snapshot_ids.update(item.snapshot_id for item in status_shards)
        result, missing, latest_price_date = _chart_rows(
            raw,
            _SnapshotIndex(
                observed_at=_observed_at_reader(self._snapshots, as_of),
                # Only the selected price shards can evidence a missing
                # price session; factor/status shards neither prove price
                # absence nor necessarily contributed to the candle.
                absence_sources=selected,
            ),
            calendar,
            factor_request,
            factors,
            suspensions,
            instrument_code,
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
            sources=tuple(
                sorted(
                    {
                        item.source
                        for item in (*selected, *factor_shards, *status_shards)
                    }
                )
            ),
            latest_price_date=latest_price_date,
            stale_reason=stale_reason,
            missing_sessions=missing,
            bars=tuple(result),
        )
