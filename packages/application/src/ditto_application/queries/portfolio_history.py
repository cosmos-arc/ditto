"""
Exact-identity historical valuation and flow-adjusted returns (accounts v1).

The query replays an explicit ledger revision day by day against retained
PIT-visible prices, classifies external cash flows, and delegates linking to
the pure portfolio contract (:mod:`ditto_portfolio.account_returns`).  The
engine is account-kind agnostic: MANUAL and PAPER accounts share one replay
machine and differ only in the account-kind gate, the paper-session binding,
and the error/result identities.  It is read-only: no backtest runs, no
ledger writes, no silent "latest" fallback — prices come from exact source
snapshots and the ledger from an exact append-order revision.

Carry-forward eligibility (whether a stale price may bridge a day) may consult bars
dated after the valuation day as long as they are visible under the knowledge cutoff;
the carried price value itself never comes from a bar published after that day's close.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256

import orjson
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_execution.paper.session import PaperSessionStorePort
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
from ditto_application.queries.history_valuation import (
    VALUATION_POLICY_VERSION,
    HistoryPointView,
    HistoryQuality,
    HistorySegmentView,
    PricedBar,
    bars_by_instrument,
    build_history_points,
    build_history_segments,
    end_of_day,
    price_at,
    trade_day,
)
from ditto_application.queries.pit_snapshots import group_dataset_snapshots
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisSourcePort,
)

__all__ = [
    "VALUATION_POLICY_VERSION",
    "AccountHistoryRequest",
    "AccountHistoryView",
    "GetManualHistoryQuery",
    "GetPaperHistoryQuery",
    "HistoryPointView",
    "HistoryQuality",
    "HistorySegmentView",
    "PaperHistoryRequest",
    "pit_context",
]

_LEDGER_HASH_PREFIX = "account-ledger:sha256:"

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


@dataclass(frozen=True)
class _HistoryFlavor:
    """Kind-scoped identities: error codes, result prefix, and account gate."""

    account_kind: AccountKind
    kind_label: str
    code_prefix: str
    failure_context: str
    result_prefix: str


_MANUAL_FLAVOR = _HistoryFlavor(
    account_kind=AccountKind.MANUAL,
    kind_label="MANUAL",
    code_prefix="MANUAL_HISTORY",
    failure_context="manual history",
    result_prefix="manual-history:sha256:",
)
_PAPER_FLAVOR = _HistoryFlavor(
    account_kind=AccountKind.PAPER,
    kind_label="PAPER",
    code_prefix="PAPER_HISTORY",
    failure_context="paper history",
    result_prefix="paper-history:sha256:",
)


@dataclass(frozen=True, kw_only=True)
class AccountHistoryRequest:
    """Exact read identity for one account-kind-scoped historical series."""

    account_id: str
    start_date: str
    end_date: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    ledger_event_count: int
    ledger_hash: str

    def result_identity(self) -> dict[str, object]:
        """Request facts bound into the replayable result identity."""
        return {
            "account_id": self.account_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "knowledge_cutoff": self.knowledge_cutoff.isoformat(),
            "publication_cutoff": self.publication_cutoff.isoformat(),
            "source_snapshot_ids": list(self.source_snapshot_ids),
        }


@dataclass(frozen=True, kw_only=True)
class PaperHistoryRequest(AccountHistoryRequest):
    """Exact read identity for one PAPER series, anchored to one session."""

    session_id: str

    def result_identity(self) -> dict[str, object]:
        """Extend the replay identity with the bound session."""
        return {**super().result_identity(), "session_id": self.session_id}


@dataclass(frozen=True, kw_only=True)
class AccountHistoryView:
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


def _error(
    flavor: _HistoryFlavor,
    code_suffix: str,
    reason: str,
    **details: object,
) -> AppQueryError:
    return AppQueryError(
        f"{flavor.failure_context} query failed closed: {reason}",
        details={
            "code": f"{flavor.code_prefix}_{code_suffix}",
            "reason": reason,
            **details,
        },
    )


def _parse_request_date(value: str, field: str, flavor: _HistoryFlavor) -> date:
    try:
        return ledger_parse_date(value, field)
    except AccountLedgerError as exc:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            f"{field} must be YYYY-MM-DD",
            field=field,
        ) from exc


def pit_context(
    *,
    snapshot_reader: ProviderSnapshotReader,
    source_snapshot_ids: tuple[str, ...],
    end: date,
    knowledge_cutoff: datetime,
    publication_cutoff: datetime,
    error: Callable[..., AppQueryError],
    mixed_version_code: str,
) -> PITQueryContext:
    """Build the shared PIT query context for exact price snapshots."""
    snapshots: list[ProviderSnapshot] = []
    for snapshot_id in source_snapshot_ids:
        snapshot = snapshot_reader.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.snapshot_id != snapshot_id:
            raise error(
                "SOURCE_SNAPSHOT_NOT_FOUND",
                "exact price source snapshot was not found",
                snapshot_id=snapshot_id,
            )
        if snapshot.created_at > knowledge_cutoff:
            raise error(
                "SOURCE_SNAPSHOT_FUTURE",
                "price source snapshot is after knowledge cutoff",
                snapshot_id=snapshot_id,
            )
        snapshots.append(snapshot)
    try:
        return PITQueryContext(
            as_of=max(end_of_day(end), knowledge_cutoff),
            knowledge_cutoff=knowledge_cutoff,
            publication_cutoff=publication_cutoff,
            source_snapshots=group_dataset_snapshots(
                snapshots,
                error=error,
                mixed_version_code=mixed_version_code,
            ),
        )
    except ValueError as exc:
        raise error("PIT_CONTEXT_INVALID", str(exc)) from exc


def _pit_context(
    request: AccountHistoryRequest,
    snapshot_reader: ProviderSnapshotReader,
    flavor: _HistoryFlavor,
) -> PITQueryContext:
    def flavor_error(code: str, reason: str, **details: object) -> AppQueryError:
        return _error(flavor, code, reason, **details)

    return pit_context(
        snapshot_reader=snapshot_reader,
        source_snapshot_ids=request.source_snapshot_ids,
        end=_parse_request_date(request.end_date, "end_date", flavor),
        knowledge_cutoff=request.knowledge_cutoff,
        publication_cutoff=request.publication_cutoff,
        error=flavor_error,
        mixed_version_code=f"{flavor.code_prefix}_SNAPSHOT_SCHEMA_MIXED",
    )


def _validate_request(request: AccountHistoryRequest, flavor: _HistoryFlavor) -> None:
    if not request.account_id.strip():
        raise _error(flavor, "REQUEST_INVALID", "account_id must be non-empty")
    start = _parse_request_date(request.start_date, "start_date", flavor)
    end = _parse_request_date(request.end_date, "end_date", flavor)
    if start > end:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "start_date cannot be after end_date",
        )
    if request.knowledge_cutoff.tzinfo is None:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "knowledge_cutoff must be timezone-aware",
        )
    if request.publication_cutoff.tzinfo is None:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "publication_cutoff must be timezone-aware",
        )
    if request.publication_cutoff > request.knowledge_cutoff:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "publication_cutoff cannot exceed knowledge_cutoff",
        )
    if not request.source_snapshot_ids:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "at least one price source snapshot is required",
        )
    if len(set(request.source_snapshot_ids)) != len(request.source_snapshot_ids):
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "price source snapshots must be unique",
        )
    if request.ledger_event_count < 1:
        raise _error(
            flavor,
            "REQUEST_INVALID",
            "ledger_event_count must be positive",
        )
    if not request.ledger_hash.startswith(_LEDGER_HASH_PREFIX):
        raise _error(
            flavor,
            "REQUEST_INVALID",
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


def _result_id(
    request: AccountHistoryRequest,
    *,
    revision: LedgerRevision,
    series: ReturnSeries,
    priced_dates: tuple[tuple[str, tuple[PricedBar, ...]], ...],
    flows: tuple[ExternalFlow, ...],
    flavor: _HistoryFlavor,
) -> str:
    payload = {
        **request.result_identity(),
        "ledger_revision": {
            "event_count": revision.event_count,
            "ledger_hash": revision.ledger_hash,
        },
        "method": series.method,
        "policy": VALUATION_POLICY_VERSION,
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
    return f"{flavor.result_prefix}{digest}"


class _AccountHistoryEngine:
    """Kind-agnostic replay of one ledger revision into a return series."""

    def __init__(
        self,
        *,
        journal: AccountEventJournalPort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
        rebuilder: AccountLedgerRebuilder,
        flavor: _HistoryFlavor,
    ) -> None:
        self._journal = journal
        self._snapshot_reader = snapshot_reader
        self._valuation_source = valuation_source
        self._rebuilder = rebuilder
        self._flavor = flavor

    def history(self, request: AccountHistoryRequest) -> AccountHistoryView:
        """Return the exact replayable series or fail closed."""
        _validate_request(request, self._flavor)
        account = self._account(request.account_id)
        prefix = self._ledger_prefix(request)
        effective = resolve_effective_events(prefix)
        context = _pit_context(request, self._snapshot_reader, self._flavor)
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
                self._flavor,
                "ACCOUNT_NOT_FOUND",
                "account not found",
                account_id=account_id,
            )
        if account.kind is not self._flavor.account_kind:
            raise _error(
                self._flavor,
                "ACCOUNT_KIND_MISMATCH",
                f"account is not a {self._flavor.kind_label} account",
                account_id=account_id,
            )
        return account

    def _ledger_prefix(
        self,
        request: AccountHistoryRequest,
    ) -> tuple[AccountEvent, ...]:
        events = tuple(self._journal.list_events(request.account_id))
        if len(events) < request.ledger_event_count:
            raise _error(
                self._flavor,
                "LEDGER_REVISION_COUNT_INVALID",
                "ledger stream is shorter than the requested revision",
                requested=request.ledger_event_count,
                actual=len(events),
            )
        prefix = events[: request.ledger_event_count]
        if ledger_hash(prefix) != request.ledger_hash:
            raise _error(
                self._flavor,
                "LEDGER_REVISION_MISMATCH",
                "computed ledger revision hash differs from request",
            )
        return prefix

    def _build(
        self,
        *,
        request: AccountHistoryRequest,
        account: AccountDefinition,
        prefix: tuple[AccountEvent, ...],
        effective: tuple[AccountEvent, ...],
        context: PITQueryContext,
    ) -> AccountHistoryView:
        flavor = self._flavor
        start = _parse_request_date(request.start_date, "start_date", flavor)
        end = _parse_request_date(request.end_date, "end_date", flavor)
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
        bars = bars_by_instrument(self._valuation_source, context, instrument_ids)
        bar_dates = {
            trade_day(bar.occurred_at)
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
        request: AccountHistoryRequest,
        account: AccountDefinition,
        prefix: tuple[AccountEvent, ...],
        valuation_dates: list[date],
        bars: dict[int, tuple[TechnicalBar, ...]],
        bar_dates: set[date],
        flows: tuple[ExternalFlow, ...],
    ) -> AccountHistoryView:
        observations: list[ValuationObservation] = []
        priced_dates: list[tuple[str, tuple[PricedBar, ...]]] = []
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
            priced: list[PricedBar] = []
            missing: list[HistoryQuality] = []
            for instrument_id in sorted(int(item) for item in held):
                priced_bar = price_at(
                    instrument_id=instrument_id,
                    bars=bars.get(instrument_id, ()),
                    on_date=day,
                    market_traded_on_date=market_traded_on_date,
                )
                if isinstance(priced_bar, PricedBar):
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
                self._flavor,
                "RETURN_SERIES_INVALID",
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
            flavor=self._flavor,
        )
        flows_by_date: dict[str, Decimal] = {}
        for flow in flows:
            if flow.kind is ExternalFlowKind.CASH:
                flows_by_date[flow.on_date] = (
                    flows_by_date.get(flow.on_date, _ZERO) + flow.amount
                )
        points = build_history_points(
            series=series,
            valuation_dates=valuation_dates,
            priced_dates=dict(priced_dates),
            display_cash=display_cash,
            gap_quality=gap_quality,
            flows_by_date=flows_by_date,
        )
        segments = build_history_segments(series)
        return AccountHistoryView(
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
            valuation_policy_version=VALUATION_POLICY_VERSION,
            points=points,
            segments=segments,
        )

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
                self._flavor,
                "LEDGER_REBUILD_FAILED",
                str(exc),
            ) from exc


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
        self._engine = _AccountHistoryEngine(
            journal=journal,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
            rebuilder=rebuilder or AccountLedgerRebuilder(),
            flavor=_MANUAL_FLAVOR,
        )

    def history(self, request: AccountHistoryRequest) -> AccountHistoryView:
        """Return the exact replayable series or fail closed."""
        return self._engine.history(request)


class GetPaperHistoryQuery:
    """Replay one PAPER ledger revision, session-bound, into a return series."""

    def __init__(
        self,
        *,
        journal: AccountEventJournalPort,
        session_store: PaperSessionStorePort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
        rebuilder: AccountLedgerRebuilder | None = None,
    ) -> None:
        self._session_store = session_store
        self._engine = _AccountHistoryEngine(
            journal=journal,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
            rebuilder=rebuilder or AccountLedgerRebuilder(),
            flavor=_PAPER_FLAVOR,
        )

    def history(self, request: PaperHistoryRequest) -> AccountHistoryView:
        """Validate the session-account binding, then replay fail-closed."""
        if not request.session_id.strip():
            raise _error(
                _PAPER_FLAVOR,
                "REQUEST_INVALID",
                "session_id must be non-empty",
            )
        session = self._session_store.get_session(request.session_id)
        if session is None:
            raise _error(
                _PAPER_FLAVOR,
                "SESSION_NOT_FOUND",
                "paper session was not found",
                session_id=request.session_id,
            )
        if session.account_id != request.account_id:
            raise _error(
                _PAPER_FLAVOR,
                "SESSION_ACCOUNT_MISMATCH",
                "paper session belongs to a different account",
                session_id=request.session_id,
                session_account_id=session.account_id,
            )
        return self._engine.history(request)
