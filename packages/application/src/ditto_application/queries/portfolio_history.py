"""
Exact-identity historical valuation and flow-adjusted returns (Manual v1).

The query replays an explicit ledger revision day by day against retained
PIT-visible prices, classifies external cash flows, and delegates linking to
the pure portfolio contract (:mod:`ditto_portfolio.account_returns`).  It is
read-only: no backtest runs, no ledger writes, no silent "latest" fallback —
prices come from exact source snapshots and the ledger from an exact
append-order revision.

Carry-forward eligibility (whether a stale price may bridge a day) may consult bars
dated after the valuation day as long as they are visible under the knowledge cutoff;
the carried price value itself never comes from a bar published after that day's close.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo

import orjson
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventJournalPort,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
    ledger_hash,
    ledger_parse_date,
)
from ditto_portfolio.account_projection import (
    AccountLedgerRebuilder,
    PortfolioSnapshot,
    resolve_effective_events,
)
from ditto_portfolio.account_returns import (
    ExternalFlow,
    ExternalFlowKind,
    ReturnSeries,
    ValuationObservation,
    compute_return_series,
)
from ditto_portfolio.errors import PortfolioError

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import LedgerRevision
from ditto_application.queries.pit_snapshots import group_dataset_snapshots
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisSourcePort,
)

__all__ = [
    "MANUAL_VALUATION_POLICY_VERSION",
    "GetManualHistoryQuery",
    "HistoryPointView",
    "HistoryQuality",
    "HistorySegmentView",
    "ManualHistoryRequest",
    "ManualHistoryView",
]

MANUAL_VALUATION_POLICY_VERSION = "manual-valuation-stale-evidence-v1"
_RESULT_ID_PREFIX = "manual-history:sha256:"
_LEDGER_HASH_PREFIX = "account-ledger:sha256:"

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_ZERO = Decimal("0")

_CASH_FLOW_TYPES = frozenset(
    {
        AccountEventType.OPENING_CASH,
        AccountEventType.DEPOSIT,
        AccountEventType.WITHDRAWAL,
    }
)
_SECURITY_TRANSFER_TYPES = frozenset(
    {
        AccountEventType.OPENING_POSITION,
        AccountEventType.TRANSFER_IN,
        AccountEventType.TRANSFER_OUT,
    }
)


@dataclass(frozen=True, kw_only=True)
class ManualHistoryRequest:
    """Exact read identity for one MANUAL historical series."""

    account_id: str
    start_date: str
    end_date: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    ledger_event_count: int
    ledger_hash: str


@dataclass(frozen=True, kw_only=True)
class HistoryQuality:
    """One machine-readable quality or absence mark."""

    code: str
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class HistoryPointView:
    """One dated valuation row; missing prices leave value gaps."""

    on_date: str
    valuation_instant: str
    total_value: Decimal | None
    cash: Decimal | None
    external_flow: Decimal
    period_return: Decimal | None
    cumulative_return: Decimal | None
    segment_id: int | None
    price_time: str | None
    stale: bool
    source_snapshot_ids: tuple[str, ...]
    quality: tuple[HistoryQuality, ...]


@dataclass(frozen=True, kw_only=True)
class HistorySegmentView:
    """One continuous positive-capital run with its own linked TWR."""

    segment_id: int
    start_date: str
    end_date: str
    start_value: Decimal
    end_value: Decimal
    linked_return: Decimal | None
    closed_reason: str
    quality: tuple[HistoryQuality, ...]


@dataclass(frozen=True, kw_only=True)
class ManualHistoryView:
    """Complete replayable result for one account and range."""

    result_id: str
    account_id: str
    currency: str
    start_date: str
    end_date: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    ledger_revision: LedgerRevision
    method: str
    valuation_policy_version: str
    points: tuple[HistoryPointView, ...]
    segments: tuple[HistorySegmentView, ...]


@dataclass(frozen=True)
class _PricedBar:
    instrument_id: int
    price: Decimal
    occurred_at: datetime
    source_snapshot_id: str
    price_date: str
    carried: bool


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"manual history query failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=_SHANGHAI)


def _trade_day(instant: datetime) -> date:
    """Bars carry a Shanghai-midnight occurred_at; map it to the trade date."""
    return instant.astimezone(_SHANGHAI).date()


def _pit_context(
    request: ManualHistoryRequest,
    snapshot_reader: ProviderSnapshotReader,
) -> PITQueryContext:
    end = _parse_request_date(request.end_date, "end_date")
    snapshots: list[ProviderSnapshot] = []
    for snapshot_id in request.source_snapshot_ids:
        snapshot = snapshot_reader.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.snapshot_id != snapshot_id:
            raise _error(
                "MANUAL_HISTORY_SOURCE_SNAPSHOT_NOT_FOUND",
                "exact price source snapshot was not found",
                snapshot_id=snapshot_id,
            )
        if snapshot.created_at > request.knowledge_cutoff:
            raise _error(
                "MANUAL_HISTORY_SOURCE_SNAPSHOT_FUTURE",
                "price source snapshot is after knowledge cutoff",
                snapshot_id=snapshot_id,
            )
        snapshots.append(snapshot)
    try:
        return PITQueryContext(
            as_of=max(_end_of_day(end), request.knowledge_cutoff),
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            source_snapshots=group_dataset_snapshots(
                snapshots,
                error=_error,
                mixed_version_code="MANUAL_HISTORY_SNAPSHOT_SCHEMA_MIXED",
            ),
        )
    except ValueError as exc:
        raise _error("MANUAL_HISTORY_PIT_CONTEXT_INVALID", str(exc)) from exc


def _parse_request_date(value: str, field: str) -> date:
    try:
        return ledger_parse_date(value, field)
    except AccountLedgerError as exc:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            f"{field} must be YYYY-MM-DD",
            field=field,
        ) from exc


def _validate_request(request: ManualHistoryRequest) -> None:
    if not request.account_id.strip():
        raise _error("MANUAL_HISTORY_REQUEST_INVALID", "account_id must be non-empty")
    start = _parse_request_date(request.start_date, "start_date")
    end = _parse_request_date(request.end_date, "end_date")
    if start > end:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "start_date cannot be after end_date",
        )
    if request.knowledge_cutoff.tzinfo is None:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "knowledge_cutoff must be timezone-aware",
        )
    if request.publication_cutoff.tzinfo is None:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "publication_cutoff must be timezone-aware",
        )
    if request.publication_cutoff > request.knowledge_cutoff:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "publication_cutoff cannot exceed knowledge_cutoff",
        )
    if not request.source_snapshot_ids:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "at least one price source snapshot is required",
        )
    if len(set(request.source_snapshot_ids)) != len(request.source_snapshot_ids):
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "price source snapshots must be unique",
        )
    if request.ledger_event_count < 1:
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "ledger_event_count must be positive",
        )
    if not request.ledger_hash.startswith(_LEDGER_HASH_PREFIX):
        raise _error(
            "MANUAL_HISTORY_REQUEST_INVALID",
            "ledger_hash must be an account-ledger:sha256: identity",
        )


def _effective_flows(
    effective_events: tuple[AccountEvent, ...],
    *,
    start: str,
    end: str,
) -> tuple[ExternalFlow, ...]:
    flows: list[ExternalFlow] = []
    for event in effective_events:
        if not (start <= event.trade_date <= end):
            continue
        effective_type = event.replacement_event_type or event.event_type
        if effective_type in _CASH_FLOW_TYPES:
            flows.append(
                ExternalFlow(
                    on_date=event.trade_date,
                    amount=event.net_cash,
                    position=event.flow_position,
                    kind=ExternalFlowKind.CASH,
                )
            )
        elif effective_type in _SECURITY_TRANSFER_TYPES:
            flows.append(
                ExternalFlow(
                    on_date=event.trade_date,
                    amount=_ZERO,
                    position=None,
                    kind=ExternalFlowKind.SECURITY_TRANSFER,
                )
            )
    return tuple(flows)


def _visible_bars(
    bars: tuple[TechnicalBar, ...],
    on_date: date,
) -> tuple[TechnicalBar, ...]:
    day_end = _end_of_day(on_date)
    return tuple(
        bar
        for bar in bars
        if _trade_day(bar.occurred_at) <= on_date and bar.publication_at <= day_end
    )


def _price_at(
    *,
    instrument_id: int,
    bars: tuple[TechnicalBar, ...],
    on_date: date,
    market_traded_on_date: bool,
) -> _PricedBar | HistoryQuality:
    visible = _visible_bars(bars, on_date)
    if not visible:
        return HistoryQuality(code="price_missing", detail=str(instrument_id))
    latest = max(visible, key=lambda bar: bar.occurred_at)
    price = Decimal(str(latest.close))
    if not price.is_finite() or price <= 0:
        return HistoryQuality(
            code="price_missing", detail=f"{instrument_id}:invalid_close"
        )
    candidate_day = _trade_day(latest.occurred_at)
    carried = candidate_day < on_date
    if carried:
        # Carry-forward is only defensible while trading demonstrably
        # continued after the candidate bar (or the candidate itself is a
        # suspended row); an unknown delisting residual must stay a gap.
        resumed_after_candidate = any(
            _trade_day(bar.occurred_at) > candidate_day for bar in bars
        )
        if not (resumed_after_candidate or latest.suspended):
            return HistoryQuality(
                code="price_missing",
                detail=(
                    f"{instrument_id}:unknown_trading_status_after_"
                    f"{candidate_day.isoformat()}"
                ),
            )
    return _PricedBar(
        instrument_id=instrument_id,
        price=price,
        occurred_at=latest.occurred_at,
        source_snapshot_id=latest.source_snapshot_id,
        price_date=candidate_day.isoformat(),
        carried=carried and market_traded_on_date,
    )


def _bars_by_instrument(
    source: TechnicalAnalysisSourcePort,
    context: PITQueryContext,
    instrument_ids: tuple[int, ...],
) -> dict[int, tuple[TechnicalBar, ...]]:
    bars: dict[int, tuple[TechnicalBar, ...]] = {}
    for instrument_id in instrument_ids:
        bars[instrument_id] = source.load(
            context,
            instrument_id=InstrumentId(instrument_id),
            instrument_code=str(instrument_id),
        )
    return bars


def _result_id(
    request: ManualHistoryRequest,
    *,
    revision: LedgerRevision,
    series: ReturnSeries,
    priced_dates: tuple[tuple[str, tuple[_PricedBar, ...]], ...],
    flows: tuple[ExternalFlow, ...],
) -> str:
    payload = {
        "account_id": request.account_id,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "knowledge_cutoff": request.knowledge_cutoff.isoformat(),
        "publication_cutoff": request.publication_cutoff.isoformat(),
        "source_snapshot_ids": list(request.source_snapshot_ids),
        "ledger_revision": {
            "event_count": revision.event_count,
            "ledger_hash": revision.ledger_hash,
        },
        "method": series.method,
        "policy": MANUAL_VALUATION_POLICY_VERSION,
        "priced_dates": [
            (
                on_date,
                [
                    (
                        bar.instrument_id,
                        str(bar.price),
                        bar.occurred_at.isoformat(),
                        bar.source_snapshot_id,
                        bar.carried,
                    )
                    for bar in sorted(prices, key=lambda item: item.instrument_id)
                ],
            )
            for on_date, prices in priced_dates
        ],
        "flows": [
            (
                flow.on_date,
                str(flow.amount),
                flow.position.value if flow.position is not None else None,
                flow.kind.value,
            )
            for flow in flows
        ],
    }
    digest = sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
    return f"{_RESULT_ID_PREFIX}{digest}"


class GetManualHistoryQuery:
    """Replay one MANUAL ledger revision into a flow-adjusted return series."""

    def __init__(
        self,
        *,
        journal: AccountEventJournalPort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
        rebuilder: AccountLedgerRebuilder | None = None,
    ) -> None:
        self._journal = journal
        self._snapshot_reader = snapshot_reader
        self._valuation_source = valuation_source
        self._rebuilder = rebuilder or AccountLedgerRebuilder()

    def history(self, request: ManualHistoryRequest) -> ManualHistoryView:
        """Return the exact replayable series or fail closed."""
        _validate_request(request)
        account = self._account(request.account_id)
        prefix = self._ledger_prefix(request)
        effective = resolve_effective_events(prefix)
        context = _pit_context(request, self._snapshot_reader)
        return self._build(
            request=request,
            account=account,
            prefix=prefix,
            effective=effective,
            context=context,
        )

    def _account(self, account_id: str) -> AccountDefinition:
        account = self._journal.get_account(account_id)
        if account is None:
            raise _error(
                "MANUAL_HISTORY_ACCOUNT_NOT_FOUND",
                "account not found",
                account_id=account_id,
            )
        if account.kind is not AccountKind.MANUAL:
            raise _error(
                "MANUAL_HISTORY_ACCOUNT_KIND_MISMATCH",
                "account is not a MANUAL account",
                account_id=account_id,
            )
        return account

    def _ledger_prefix(
        self,
        request: ManualHistoryRequest,
    ) -> tuple[AccountEvent, ...]:
        events = tuple(self._journal.list_events(request.account_id))
        if len(events) < request.ledger_event_count:
            raise _error(
                "MANUAL_HISTORY_LEDGER_REVISION_COUNT_INVALID",
                "ledger stream is shorter than the requested revision",
                requested=request.ledger_event_count,
                actual=len(events),
            )
        prefix = events[: request.ledger_event_count]
        if ledger_hash(prefix) != request.ledger_hash:
            raise _error(
                "MANUAL_HISTORY_LEDGER_REVISION_MISMATCH",
                "computed ledger revision hash differs from request",
            )
        return prefix

    def _build(
        self,
        *,
        request: ManualHistoryRequest,
        account: AccountDefinition,
        prefix: tuple[AccountEvent, ...],
        effective: tuple[AccountEvent, ...],
        context: PITQueryContext,
    ) -> ManualHistoryView:
        start = _parse_request_date(request.start_date, "start_date")
        end = _parse_request_date(request.end_date, "end_date")
        flows = _effective_flows(
            effective, start=request.start_date, end=request.end_date
        )
        instrument_ids = tuple(
            sorted(
                {
                    int(event.instrument_id)
                    for event in effective
                    if event.instrument_id is not None
                }
            )
        )
        bars = _bars_by_instrument(self._valuation_source, context, instrument_ids)
        bar_dates = {
            _trade_day(bar.occurred_at)
            for instrument_bars in bars.values()
            for bar in instrument_bars
        }
        event_dates = {
            ledger_parse_date(event.trade_date, "trade_date") for event in effective
        }
        inception = min(event_dates) if event_dates else None
        valuation_dates = sorted(
            day
            for day in bar_dates | event_dates
            if start <= day <= end and (inception is None or day >= inception)
        )
        return self._series(
            request=request,
            account=account,
            prefix=prefix,
            valuation_dates=valuation_dates,
            bars=bars,
            bar_dates=bar_dates,
            flows=flows,
        )

    def _series(
        self,
        *,
        request: ManualHistoryRequest,
        account: AccountDefinition,
        prefix: tuple[AccountEvent, ...],
        valuation_dates: list[date],
        bars: dict[int, tuple[TechnicalBar, ...]],
        bar_dates: set[date],
        flows: tuple[ExternalFlow, ...],
    ) -> ManualHistoryView:
        observations: list[ValuationObservation] = []
        priced_dates: list[tuple[str, tuple[_PricedBar, ...]]] = []
        display_cash: dict[str, Decimal] = {}
        gap_quality: dict[str, tuple[HistoryQuality, ...]] = {}
        previous_valued = False
        for day in valuation_dates:
            unvalued = self._rebuild(account, prefix, day.isoformat(), prices=None)
            held = {
                position.instrument_id
                for position in unvalued.positions
                if position.quantity > _ZERO
            }
            market_traded_on_date = day in bar_dates
            priced: list[_PricedBar] = []
            missing: list[HistoryQuality] = []
            for instrument_id in sorted(int(item) for item in held):
                priced_bar = _price_at(
                    instrument_id=instrument_id,
                    bars=bars.get(instrument_id, ()),
                    on_date=day,
                    market_traded_on_date=market_traded_on_date,
                )
                if isinstance(priced_bar, _PricedBar):
                    priced.append(priced_bar)
                else:
                    missing.append(priced_bar)
            if missing:
                day_key = day.isoformat()
                display_cash[day_key] = unvalued.cash.total
                gap_quality[day_key] = tuple(missing)
                previous_valued = False
                continue
            snapshot = self._rebuild(
                account,
                prefix,
                day.isoformat(),
                prices={InstrumentId(bar.instrument_id): bar.price for bar in priced},
            )
            observations.append(
                ValuationObservation(
                    on_date=day.isoformat(),
                    total_value=snapshot.total_value,
                    gap_before=not previous_valued and bool(observations),
                )
            )
            priced_dates.append((day.isoformat(), tuple(priced)))
            display_cash[day.isoformat()] = snapshot.cash.total
            previous_valued = True

        observation_dates = {obs.on_date for obs in observations}
        calculator_flows = tuple(
            flow for flow in flows if flow.on_date in observation_dates
        )
        try:
            series = compute_return_series(
                observations=tuple(observations),
                flows=calculator_flows,
            )
        except PortfolioError as exc:
            raise _error(
                "MANUAL_HISTORY_RETURN_SERIES_INVALID",
                str(exc),
            ) from exc
        revision = LedgerRevision(
            event_count=request.ledger_event_count,
            ledger_hash=request.ledger_hash,
        )
        result_id = _result_id(
            request,
            revision=revision,
            series=series,
            priced_dates=tuple(priced_dates),
            flows=flows,
        )
        points = self._points(
            series=series,
            valuation_dates=valuation_dates,
            flows=flows,
            priced_dates=dict(priced_dates),
            display_cash=display_cash,
            gap_quality=gap_quality,
        )
        segments = tuple(
            HistorySegmentView(
                segment_id=segment.segment_id,
                start_date=segment.start_date,
                end_date=segment.end_date,
                start_value=segment.start_value,
                end_value=segment.end_value,
                linked_return=segment.linked_return,
                closed_reason=segment.closed_reason,
                quality=tuple(
                    HistoryQuality(code=reason.code.value, detail=reason.detail)
                    for reason in segment.reasons
                ),
            )
            for segment in series.segments
        )
        return ManualHistoryView(
            result_id=result_id,
            account_id=account.account_id,
            currency="CNY",
            start_date=request.start_date,
            end_date=request.end_date,
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            source_snapshot_ids=request.source_snapshot_ids,
            ledger_revision=revision,
            method=series.method,
            valuation_policy_version=MANUAL_VALUATION_POLICY_VERSION,
            points=points,
            segments=segments,
        )

    def _points(
        self,
        *,
        series: ReturnSeries,
        valuation_dates: list[date],
        flows: tuple[ExternalFlow, ...],
        priced_dates: dict[str, tuple[_PricedBar, ...]],
        display_cash: dict[str, Decimal],
        gap_quality: dict[str, tuple[HistoryQuality, ...]],
    ) -> tuple[HistoryPointView, ...]:
        by_date = {point.on_date: point for point in series.points}
        flows_by_date: dict[str, Decimal] = {}
        for flow in flows:
            if flow.kind is ExternalFlowKind.CASH:
                flows_by_date[flow.on_date] = (
                    flows_by_date.get(flow.on_date, _ZERO) + flow.amount
                )
        points: list[HistoryPointView] = []
        for day in valuation_dates:
            key = day.isoformat()
            priced = priced_dates.get(key, ())
            stale = any(bar.carried for bar in priced)
            calculator_point = by_date.get(key)
            quality: tuple[HistoryQuality, ...] = (
                gap_quality.get(key, ())
                if calculator_point is None
                else tuple(
                    HistoryQuality(code=reason.code.value, detail=reason.detail)
                    for reason in calculator_point.reasons
                )
            )
            if calculator_point is None:
                total_value = None
                period_return = None
                cumulative_return = None
                segment_id = None
            else:
                total_value = calculator_point.total_value
                period_return = calculator_point.period_return
                cumulative_return = calculator_point.cumulative_return
                segment_id = calculator_point.segment_id
            if stale:
                stale_marks = tuple(
                    HistoryQuality(
                        code="stale_price",
                        detail=f"{bar.instrument_id}:{bar.price_date}",
                    )
                    for bar in priced
                    if bar.carried
                )
                quality = (*quality, *stale_marks)
            points.append(
                HistoryPointView(
                    on_date=key,
                    valuation_instant=_end_of_day(day).isoformat(),
                    total_value=total_value,
                    cash=display_cash.get(key),
                    external_flow=flows_by_date.get(key, _ZERO),
                    period_return=period_return,
                    cumulative_return=cumulative_return,
                    segment_id=segment_id,
                    price_time=(
                        max(bar.occurred_at for bar in priced).isoformat()
                        if priced
                        else None
                    ),
                    stale=stale,
                    source_snapshot_ids=tuple(
                        sorted({bar.source_snapshot_id for bar in priced})
                    ),
                    quality=quality,
                )
            )
        return tuple(points)

    def _rebuild(
        self,
        account: AccountDefinition,
        prefix: tuple[AccountEvent, ...],
        as_of: str,
        prices: dict[InstrumentId, Decimal] | None,
    ) -> PortfolioSnapshot:
        try:
            return self._rebuilder.rebuild(
                account=account,
                events=prefix,
                as_of=as_of,
                valuation_prices=prices,
            )
        except AccountLedgerError as exc:
            raise _error(
                "MANUAL_HISTORY_LEDGER_REBUILD_FAILED",
                str(exc),
            ) from exc
