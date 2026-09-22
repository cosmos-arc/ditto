"""Manual history query replays exact revisions into flow-adjusted returns."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.portfolio_history import (
    MANUAL_VALUATION_POLICY_VERSION,
    GetManualHistoryQuery,
    ManualHistoryRequest,
    ManualHistoryView,
)
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    FlowPosition,
    create_account_event,
    ledger_hash,
)

_D = Decimal
_ACCOUNT_ID = "manual-history-account"
_OPENED_AT = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
_RECORDED_AT = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
_KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)


def _account(
    account_id: str = _ACCOUNT_ID,
    kind: AccountKind = AccountKind.MANUAL,
) -> AccountDefinition:
    return AccountDefinition(
        account_id=account_id,
        kind=kind,
        name="Manual history fixture",
        opened_at=_OPENED_AT,
    )


def _event(
    event_id: str,
    event_type: AccountEventType,
    *,
    trade_date: str = "2026-03-02",
    instrument_id: int | None = None,
    quantity: str = "0",
    price: str = "0",
    gross_amount: str = "0",
    fees: str = "0",
    flow_position: FlowPosition | None = None,
    corrects_event_id: str | None = None,
    replacement_event_type: AccountEventType | None = None,
    account: AccountDefinition | None = None,
) -> AccountEvent:
    return create_account_event(
        account=account or _account(),
        draft=AccountEventDraft(
            event_type=event_type,
            event_id=event_id,
            trade_date=trade_date,
            settlement_date=trade_date,
            recorded_at=_RECORDED_AT,
            idempotency_key=f"idem-{event_id}",
            actor="user:chevy",
            source=AccountEventSource.MANUAL_ENTRY,
            instrument_id=(
                InstrumentId(instrument_id) if instrument_id is not None else None
            ),
            quantity=_D(quantity),
            price=_D(price),
            gross_amount=_D(gross_amount),
            fees=_D(fees),
            flow_position=flow_position,
            corrects_event_id=corrects_event_id,
            replacement_event_type=replacement_event_type,
        ),
    )


class _Journal:
    def __init__(self, account: AccountDefinition, events: list[AccountEvent]):
        self._account = account
        self.events = events

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        raise AssertionError("history query must not create accounts")

    def get_account(self, account_id: str) -> AccountDefinition | None:
        return self._account if account_id == self._account.account_id else None

    def append(self, event: AccountEvent) -> AccountEvent:
        self.events.append(event)
        return event

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        return next(
            (
                event
                for event in self.events
                if event.account_id == account_id and event.event_id == event_id
            ),
            None,
        )

    def find_by_idempotency_key(
        self,
        account_id: str,
        idempotency_key: str,
    ) -> AccountEvent | None:
        return next(
            (
                event
                for event in self.events
                if event.account_id == account_id
                and event.idempotency_key == idempotency_key
            ),
            None,
        )

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        return tuple(event for event in self.events if event.account_id == account_id)


class _SnapshotReader:
    def __init__(
        self,
        snapshot: ProviderSnapshot,
        *,
        expected_id: str | None = None,
    ):
        self._snapshot = snapshot
        self._expected_id = expected_id or snapshot.snapshot_id

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._snapshot if snapshot_id == self._expected_id else None

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        del snapshot_id
        return None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        del snapshot_id
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        del dataset_id, source, canonical_asset
        return ()


class _ValuationSource:
    def __init__(self, bars: dict[int, tuple[TechnicalBar, ...]]):
        self._bars = bars
        self.contexts: list[PITQueryContext] = []

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        self.contexts.append(context)
        assert instrument_code == str(instrument_id)
        return self._bars.get(int(instrument_id), ())


def _bar(
    day: str,
    close: float,
    *,
    snapshot_id: str | None = None,
    published_day: str | None = None,
    suspended: bool = False,
) -> TechnicalBar:
    occurred = datetime.fromisoformat(f"{day}T07:00:00+00:00")
    published = datetime.fromisoformat(f"{published_day or day}T10:00:00+00:00")
    return TechnicalBar(
        occurred_at=occurred,
        knowledge_at=published,
        publication_at=published,
        source_snapshot_id=snapshot_id or _SNAPSHOT_ID,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        turnover=close * 1000.0,
        adjustment_factor=1.0,
        suspended=suspended,
    )


def _snapshot(*, created_at: datetime | None = None) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="fixture",
            request_start="2026-03-02",
            request_end="2026-03-05",
            schema_version="market.stock_daily.v1",
            checksum="sha256:retained-bars",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="sha256:params",
            response_metadata=(("rows", "6"),),
            license_record_id="license:fixture",
            row_count=6,
            payload_uri="file:///tmp/fixture-stock-daily.parquet",
            payload_retained=True,
            created_at=created_at or datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
        )
    )


_SNAPSHOT = _snapshot()
_SNAPSHOT_ID = _SNAPSHOT.snapshot_id


def _query(
    events: list[AccountEvent],
    bars: dict[int, tuple[TechnicalBar, ...]],
    *,
    account: AccountDefinition | None = None,
) -> tuple[GetManualHistoryQuery, _Journal]:
    journal = _Journal(account or _account(), events)
    query = GetManualHistoryQuery(
        journal=journal,
        snapshot_reader=_SnapshotReader(_SNAPSHOT),
        valuation_source=_ValuationSource(bars),
    )
    return query, journal


def _request(
    *,
    event_count: int,
    ledger_hash_value: str,
    end_date: str = "2026-03-05",
    start_date: str = "2026-03-02",
) -> ManualHistoryRequest:
    return ManualHistoryRequest(
        account_id=_ACCOUNT_ID,
        start_date=start_date,
        end_date=end_date,
        knowledge_cutoff=_KNOWLEDGE,
        publication_cutoff=_KNOWLEDGE,
        source_snapshot_ids=(_SNAPSHOT_ID,),
        ledger_event_count=event_count,
        ledger_hash=ledger_hash_value,
    )


def _base_events(
    flow_position: FlowPosition | None = FlowPosition.START_OF_DAY,
) -> list[AccountEvent]:
    return [
        _event(
            "event-opening",
            AccountEventType.OPENING_CASH,
            trade_date="2026-03-02",
            gross_amount="100",
        ),
        _event(
            "event-buy",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=1,
            quantity="10",
            price="10",
        ),
        _event(
            "event-deposit",
            AccountEventType.DEPOSIT,
            trade_date="2026-03-04",
            gross_amount="100",
            flow_position=flow_position,
        ),
    ]


def _base_bars() -> dict[int, tuple[TechnicalBar, ...]]:
    return {
        1: (
            _bar("2026-03-02", 10.0),
            _bar("2026-03-03", 11.0),
            _bar("2026-03-04", 12.1),
        )
    }


def _run(
    events: list[AccountEvent],
    bars: dict[int, tuple[TechnicalBar, ...]],
    *,
    end_date: str = "2026-03-05",
) -> ManualHistoryView:
    query, _ = _query(events, bars)
    request = _request(
        event_count=len(events),
        ledger_hash_value=ledger_hash(tuple(events)),
        end_date=end_date,
    )
    return query.history(request)


def test_query_replays_flow_adjusted_returns_from_prices_and_ledger() -> None:
    view = _run(_base_events(), _base_bars())
    assert [point.on_date for point in view.points] == [
        "2026-03-02",
        "2026-03-03",
        "2026-03-04",
    ]
    values = [point.total_value for point in view.points]
    assert values == [_D("100"), _D("110"), _D("221")]
    assert [point.cash for point in view.points] == [_D("0"), _D("0"), _D("100")]
    assert view.points[0].period_return is None
    assert view.points[1].period_return == _D("0.1")
    assert view.points[2].period_return == _D("221") / _D("210") - _D("1")
    assert view.segments[0].linked_return == (
        _D("11") / _D("10") * (_D("221") / _D("210")) - _D("1")
    )
    assert view.segments[0].closed_reason == "range_end"


def test_result_identity_binds_full_request_and_is_replayable() -> None:
    events = _base_events()
    bars = _base_bars()
    first = _run(events, bars)
    second = _run(events, bars)
    assert first.result_id == second.result_id
    assert first.result_id.startswith("manual-history:sha256:")
    assert first.method == "twr-linked-v1"
    assert first.valuation_policy_version == MANUAL_VALUATION_POLICY_VERSION
    assert first.currency == "CNY"
    assert first.ledger_revision.event_count == 3
    assert first.ledger_revision.ledger_hash == ledger_hash(tuple(events))
    assert first.knowledge_cutoff == _KNOWLEDGE


def test_future_ledger_writes_do_not_change_old_revision_results() -> None:
    events = _base_events()
    bars = _base_bars()
    query, journal = _query(events, bars)
    old_request = _request(
        event_count=3,
        ledger_hash_value=ledger_hash(tuple(events)),
    )
    before = query.history(old_request)

    correction = _event(
        "event-deposit-correction",
        AccountEventType.CORRECTION,
        trade_date="2026-03-04",
        gross_amount="200",
        flow_position=FlowPosition.START_OF_DAY,
        corrects_event_id="event-deposit",
        replacement_event_type=AccountEventType.DEPOSIT,
    )
    journal.append(correction)

    replay = query.history(old_request)
    assert replay.result_id == before.result_id
    assert replay.points[2].total_value == before.points[2].total_value

    new_request = _request(
        event_count=4,
        ledger_hash_value=ledger_hash(tuple(journal.events)),
    )
    revised = query.history(new_request)
    assert revised.result_id != before.result_id
    assert revised.points[2].total_value == _D("321")


def test_ledger_revision_hash_mismatch_fails_closed() -> None:
    events = _base_events()
    query, _ = _query(events, _base_bars())
    request = _request(
        event_count=3,
        ledger_hash_value="account-ledger:sha256:" + "0" * 64,
    )
    with pytest.raises(AppQueryError) as error:
        query.history(request)
    assert error.value.details["code"] == "MANUAL_HISTORY_LEDGER_REVISION_MISMATCH"


def test_ledger_revision_count_beyond_stream_fails_closed() -> None:
    events = _base_events()
    query, _ = _query(events, _base_bars())
    request = _request(
        event_count=4,
        ledger_hash_value=ledger_hash(tuple(events)),
    )
    with pytest.raises(AppQueryError) as error:
        query.history(request)
    assert error.value.details["code"] == "MANUAL_HISTORY_LEDGER_REVISION_COUNT_INVALID"


def test_non_manual_account_is_rejected() -> None:
    paper_account = _account(kind=AccountKind.PAPER)
    events = _base_events()
    events = [
        create_account_event(
            account=paper_account,
            draft=AccountEventDraft(
                event_type=AccountEventType.OPENING_CASH,
                event_id="paper-opening",
                trade_date="2026-03-02",
                settlement_date="2026-03-02",
                recorded_at=_RECORDED_AT,
                idempotency_key="idem-paper-opening",
                actor="user:chevy",
                source=AccountEventSource.PAPER_ENGINE,
                gross_amount=_D("100"),
            ),
        )
    ]
    query, _ = _query(events, _base_bars(), account=paper_account)
    request = _request(
        event_count=1,
        ledger_hash_value=ledger_hash(tuple(events)),
    )
    with pytest.raises(AppQueryError) as error:
        query.history(request)
    assert error.value.details["code"] == "MANUAL_HISTORY_ACCOUNT_KIND_MISMATCH"


def test_legacy_flow_without_declared_position_fails_that_leg_only() -> None:
    view = _run(_base_events(flow_position=None), _base_bars())
    codes = {mark.code for mark in view.points[2].quality}
    assert "timing_unknown" in codes
    assert view.points[2].period_return is None
    assert view.points[1].period_return == _D("0.1")
    assert view.segments[0].linked_return is None


def test_missing_prices_leave_null_rows_without_fabricating_values() -> None:
    # Instrument 1 stops trading after 03-03 with no resumption evidence
    # (possible delisting), instrument 2 keeps trading.
    bars = {
        1: (_bar("2026-03-02", 10.0), _bar("2026-03-03", 11.0)),
        2: (
            _bar("2026-03-02", 20.0),
            _bar("2026-03-03", 21.0),
            _bar("2026-03-04", 22.0),
            _bar("2026-03-05", 23.0),
        ),
    }
    events = [
        _event(
            "event-opening",
            AccountEventType.OPENING_CASH,
            trade_date="2026-03-02",
            gross_amount="100",
        ),
        _event(
            "event-buy-1",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=1,
            quantity="5",
            price="10",
        ),
        _event(
            "event-buy-2",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=2,
            quantity="2",
            price="20",
        ),
    ]
    view = _run(events, bars)
    by_date = {point.on_date: point for point in view.points}
    assert by_date["2026-03-04"].total_value is None
    assert by_date["2026-03-05"].total_value is None
    codes = {mark.code for mark in by_date["2026-03-04"].quality}
    assert "price_missing" in codes
    assert "price_missing" in {mark.code for mark in by_date["2026-03-05"].quality}
    # 03-03 was fully priced: 5*11 + 2*21 + 10 cash = 107.
    assert by_date["2026-03-03"].total_value == _D("107")


def test_suspended_carry_marks_stale_with_actual_price_day() -> None:
    bars = {
        1: (
            _bar("2026-03-02", 10.0),
            _bar("2026-03-03", 11.0),
            _bar("2026-03-09", 11.0),
        ),
        2: (
            _bar("2026-03-02", 20.0),
            _bar("2026-03-03", 21.0),
            _bar("2026-03-04", 22.0),
            _bar("2026-03-05", 23.0),
        ),
    }
    events = [
        _event(
            "event-opening",
            AccountEventType.OPENING_CASH,
            trade_date="2026-03-02",
            gross_amount="100",
        ),
        _event(
            "event-buy-1",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=1,
            quantity="5",
            price="10",
        ),
        _event(
            "event-buy-2",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=2,
            quantity="2",
            price="20",
        ),
    ]
    view = _run(events, bars)
    by_date = {point.on_date: point for point in view.points}
    stale_point = by_date["2026-03-04"]
    assert stale_point.stale is True
    stale_marks = [mark for mark in stale_point.quality if mark.code == "stale_price"]
    assert any(mark.detail.startswith("1:2026-03-03") for mark in stale_marks)
    # Carried 11.0 for instrument 1, fresh 22.0 for instrument 2, 10 cash.
    assert stale_point.total_value == _D("109")


def test_inverted_range_is_rejected() -> None:
    events = _base_events()
    query, _ = _query(events, _base_bars())
    request = _request(
        event_count=len(events),
        ledger_hash_value=ledger_hash(tuple(events)),
        start_date="2026-03-05",
        end_date="2026-03-02",
    )
    with pytest.raises(AppQueryError) as error:
        query.history(request)
    assert error.value.details["code"] == "MANUAL_HISTORY_REQUEST_INVALID"


def test_retrospective_knowledge_cutoff_after_range_end_is_accepted() -> None:
    # Knowing more after the range end must not change in-range valuations:
    # prices are still filtered per-date by publication time.
    events = _base_events()
    query, _ = _query(events, _base_bars())
    request = ManualHistoryRequest(
        account_id=_ACCOUNT_ID,
        start_date="2026-03-02",
        end_date="2026-03-03",
        knowledge_cutoff=datetime(2026, 3, 7, 0, 0, tzinfo=UTC),
        publication_cutoff=datetime(2026, 3, 7, 0, 0, tzinfo=UTC),
        source_snapshot_ids=(_SNAPSHOT_ID,),
        ledger_event_count=len(events),
        ledger_hash=ledger_hash(tuple(events)),
    )
    view = query.history(request)
    by_date = {point.on_date: point for point in view.points}
    assert by_date["2026-03-02"].total_value == _D("100")
    assert by_date["2026-03-03"].total_value == _D("110")


def test_price_snapshot_after_knowledge_cutoff_is_rejected() -> None:
    events = _base_events()
    late_snapshot = _snapshot(created_at=datetime(2026, 3, 9, 10, 0, tzinfo=UTC))
    journal = _Journal(_account(), events)
    query = GetManualHistoryQuery(
        journal=journal,
        snapshot_reader=_SnapshotReader(late_snapshot, expected_id=_SNAPSHOT_ID),
        valuation_source=_ValuationSource(_base_bars()),
    )
    request = _request(
        event_count=len(events),
        ledger_hash_value=ledger_hash(tuple(events)),
    )
    with pytest.raises(AppQueryError) as error:
        query.history(request)
    assert error.value.details["code"] == "MANUAL_HISTORY_SOURCE_SNAPSHOT_FUTURE"


def test_republished_bar_is_invisible_at_earlier_valuation_dates() -> None:
    # The 03-03 close is republished on 03-05: at the 03-03 close valuation
    # only the 03-02 bar is visible, so the carried 10.0 prices the position.
    bars = {
        1: (
            _bar("2026-03-02", 10.0),
            _bar("2026-03-03", 11.0, published_day="2026-03-05"),
        )
    }
    events = [
        _event(
            "event-opening",
            AccountEventType.OPENING_CASH,
            trade_date="2026-03-02",
            gross_amount="100",
        ),
        _event(
            "event-buy",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=1,
            quantity="10",
            price="10",
        ),
    ]
    view = _run(events, bars, end_date="2026-03-03")
    by_date = {point.on_date: point for point in view.points}
    assert by_date["2026-03-02"].total_value == _D("100")
    assert by_date["2026-03-03"].total_value == _D("100")


def test_ex_dividend_drop_with_dividend_cash_is_zero_return() -> None:
    """Position 10@10 drops to 9.5 ex-div; a 5 CNY dividend keeps total 100."""
    bars = {
        1: (
            _bar("2026-03-02", 10.0),
            _bar("2026-03-03", 9.5),
        )
    }
    events = [
        _event(
            "event-opening",
            AccountEventType.OPENING_CASH,
            trade_date="2026-03-02",
            gross_amount="100",
        ),
        _event(
            "event-buy",
            AccountEventType.BUY,
            trade_date="2026-03-02",
            instrument_id=1,
            quantity="10",
            price="10",
        ),
        _event(
            "event-dividend",
            AccountEventType.DIVIDEND,
            trade_date="2026-03-03",
            instrument_id=1,
            gross_amount="5",
        ),
    ]
    view = _run(events, bars, end_date="2026-03-03")
    by_date = {point.on_date: point for point in view.points}
    assert by_date["2026-03-02"].total_value == _D("100")
    # 10 shares at 9.5 (raw close) plus 5 dividend cash = 100, return 0%.
    assert by_date["2026-03-03"].total_value == _D("100.00")
    assert by_date["2026-03-03"].cash == _D("5.00")
    assert by_date["2026-03-03"].period_return == _D("0")
    assert by_date["2026-03-03"].external_flow == _D("0")
    assert view.segments[0].linked_return == _D("0")


def test_intraday_flow_without_boundary_valuations_fails_only_that_leg() -> None:
    events = _base_events(flow_position=FlowPosition.INTRADAY)
    view = _run(events, _base_bars())
    codes = {mark.code for mark in view.points[2].quality}
    assert codes == {"cash_flow_valuation_missing"}
    assert view.points[2].period_return is None
    assert view.points[1].period_return == _D("0.1")
