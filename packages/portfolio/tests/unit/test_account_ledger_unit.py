"""Account ledger contracts for MODEL, PAPER, and MANUAL portfolios."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
    ManualCorrectionEvent,
    ManualLedgerEvent,
    ManualReversalEvent,
    create_account_event,
)
from ditto_portfolio.account_projection import AccountLedgerRebuilder

RECORDED_AT = datetime(2026, 8, 31, 9, 30, tzinfo=UTC)


def _account(kind: AccountKind = AccountKind.MANUAL) -> AccountDefinition:
    return AccountDefinition(
        account_id=f"account-{kind.value}",
        kind=kind,
        name=f"{kind.value.title()} account",
        opened_at=RECORDED_AT,
    )


def _event(
    *,
    account: AccountDefinition | None = None,
    event_type: AccountEventType,
    event_id: str,
    instrument_id: InstrumentId | None = None,
    quantity: str = "0",
    price: str = "0",
    gross_amount: str = "0",
    fees: str = "0",
    tax: str = "0",
    net_cash: str | None = None,
    reverses_event_id: str | None = None,
    corrects_event_id: str | None = None,
    replacement_event_type: AccountEventType | None = None,
    settlement_date: str = "2026-08-31",
):
    resolved = account or _account()
    return create_account_event(
        account=resolved,
        draft=AccountEventDraft(
            event_type=event_type,
            event_id=event_id,
            trade_date="2026-08-31",
            settlement_date=settlement_date,
            recorded_at=RECORDED_AT,
            idempotency_key=f"idem-{event_id}",
            actor="user:chevy",
            source=AccountEventSource.MANUAL_ENTRY,
            instrument_id=instrument_id,
            quantity=Decimal(quantity),
            price=Decimal(price),
            gross_amount=Decimal(gross_amount),
            fees=Decimal(fees),
            tax=Decimal(tax),
            net_cash=None if net_cash is None else Decimal(net_cash),
            reverses_event_id=reverses_event_id,
            corrects_event_id=corrects_event_id,
            replacement_event_type=replacement_event_type,
        ),
    )


def test_account_kind_is_fixed_and_events_cannot_cross_account_boundaries() -> None:
    manual = _account(AccountKind.MANUAL)
    paper = AccountDefinition(
        account_id=manual.account_id,
        kind=AccountKind.PAPER,
        name="Paper account",
        opened_at=RECORDED_AT,
    )

    manual_event = _event(
        account=manual,
        event_type=AccountEventType.OPENING_CASH,
        event_id="event-opening",
        gross_amount="100000",
    )

    with pytest.raises(AccountLedgerError, match="account kind mismatch"):
        paper.assert_accepts(manual_event)

    with pytest.raises(AccountLedgerError, match="MODEL portfolios"):
        _event(
            account=_account(AccountKind.MODEL),
            event_type=AccountEventType.OPENING_CASH,
            event_id="model-event",
            gross_amount="1",
        )


def test_manual_event_union_and_money_precision_are_explicit() -> None:
    buy = _event(
        event_type=AccountEventType.BUY,
        event_id="buy-1",
        instrument_id=InstrumentId(600519),
        quantity="100",
        price="123.45678",
        fees="5.555",
        tax="0",
    )
    reversal = _event(
        event_type=AccountEventType.REVERSAL,
        event_id="reverse-1",
        reverses_event_id="buy-1",
    )
    correction = _event(
        event_type=AccountEventType.CORRECTION,
        event_id="correct-1",
        instrument_id=InstrumentId(600519),
        quantity="100",
        price="124",
        fees="5",
        corrects_event_id="buy-1",
        replacement_event_type=AccountEventType.BUY,
    )

    assert isinstance(buy, ManualLedgerEvent)
    assert isinstance(reversal, ManualReversalEvent)
    assert isinstance(correction, ManualCorrectionEvent)
    assert buy.price == Decimal("123.4568")
    assert buy.fees == Decimal("5.56")
    assert buy.gross_amount == Decimal("12345.68")
    assert buy.net_cash == Decimal("-12351.24")


def test_event_hash_is_deterministic_and_covers_business_payload() -> None:
    first = _event(
        event_type=AccountEventType.DEPOSIT,
        event_id="deposit-1",
        gross_amount="1000",
    )
    same = _event(
        event_type=AccountEventType.DEPOSIT,
        event_id="deposit-1",
        gross_amount="1000.00",
    )
    changed = _event(
        event_type=AccountEventType.DEPOSIT,
        event_id="deposit-1",
        gross_amount="1001",
    )

    assert first.event_hash == same.event_hash
    assert first.event_hash.startswith("account-event:sha256:")
    assert changed.event_hash != first.event_hash


def test_manual_event_field_rules_fail_closed() -> None:
    with pytest.raises(AccountLedgerError, match="instrument_id"):
        _event(event_type=AccountEventType.BUY, event_id="bad-buy")
    with pytest.raises(AccountLedgerError, match="quantity"):
        _event(
            event_type=AccountEventType.SELL,
            event_id="bad-sell",
            instrument_id=InstrumentId(600519),
            quantity="0",
            price="1",
        )
    with pytest.raises(AccountLedgerError, match="reverses_event_id"):
        _event(event_type=AccountEventType.REVERSAL, event_id="bad-reversal")
    with pytest.raises(AccountLedgerError, match="replacement_event_type"):
        _event(
            event_type=AccountEventType.CORRECTION,
            event_id="bad-correction",
            corrects_event_id="event-1",
        )


def test_rebuild_projects_cash_positions_cost_valuation_and_pnl() -> None:
    account = _account()
    events = (
        _event(
            account=account,
            event_type=AccountEventType.OPENING_CASH,
            event_id="cash",
            gross_amount="100000",
        ),
        _event(
            account=account,
            event_type=AccountEventType.BUY,
            event_id="buy",
            instrument_id=InstrumentId(600519),
            quantity="100",
            price="100",
            fees="5",
        ),
        _event(
            account=account,
            event_type=AccountEventType.SELL,
            event_id="sell",
            instrument_id=InstrumentId(600519),
            quantity="20",
            price="120",
            fees="5",
            tax="2.4",
        ),
        _event(
            account=account,
            event_type=AccountEventType.DIVIDEND,
            event_id="dividend",
            instrument_id=InstrumentId(600519),
            gross_amount="100",
            tax="10",
        ),
    )

    snapshot = AccountLedgerRebuilder().rebuild(
        account=account,
        events=events,
        as_of="2026-08-31",
        valuation_prices={InstrumentId(600519): Decimal("125")},
    )

    position = snapshot.position(InstrumentId(600519))
    assert snapshot.cash.available == Decimal("92477.60")
    assert position.quantity == Decimal("80")
    assert position.average_cost == Decimal("100.0500")
    assert position.market_value == Decimal("10000.00")
    assert position.realized_pnl == Decimal("391.60")
    assert position.unrealized_pnl == Decimal("1996.00")
    assert snapshot.total_value == Decimal("102477.60")
    assert snapshot.event_count == 4
    assert snapshot.ledger_hash.startswith("account-ledger:sha256:")


def test_reversal_and_correction_preserve_history_but_replace_effect() -> None:
    account = _account()
    opening = _event(
        account=account,
        event_type=AccountEventType.OPENING_CASH,
        event_id="cash",
        gross_amount="1000",
    )
    mistaken = _event(
        account=account,
        event_type=AccountEventType.WITHDRAWAL,
        event_id="mistaken",
        gross_amount="200",
    )
    corrected = _event(
        account=account,
        event_type=AccountEventType.CORRECTION,
        event_id="correction",
        corrects_event_id="mistaken",
        replacement_event_type=AccountEventType.WITHDRAWAL,
        gross_amount="50",
    )
    reversed_correction = _event(
        account=account,
        event_type=AccountEventType.REVERSAL,
        event_id="reversal",
        reverses_event_id="correction",
    )

    corrected_snapshot = AccountLedgerRebuilder().rebuild(
        account=account,
        events=(opening, mistaken, corrected),
        as_of="2026-08-31",
    )
    restored_snapshot = AccountLedgerRebuilder().rebuild(
        account=account,
        events=(opening, mistaken, corrected, reversed_correction),
        as_of="2026-08-31",
    )

    assert corrected_snapshot.cash.available == Decimal("950.00")
    assert corrected_snapshot.event_count == 3
    assert restored_snapshot.cash.available == Decimal("800.00")
    assert restored_snapshot.event_count == 4


def test_rebuild_rejects_duplicate_identity_and_unknown_correction_target() -> None:
    account = _account()
    event = _event(
        account=account,
        event_type=AccountEventType.DEPOSIT,
        event_id="same",
        gross_amount="10",
    )
    missing_target = _event(
        account=account,
        event_type=AccountEventType.REVERSAL,
        event_id="reverse-missing",
        reverses_event_id="missing",
    )

    with pytest.raises(AccountLedgerError, match="duplicate event_id"):
        AccountLedgerRebuilder().rebuild(
            account=account,
            events=(event, event),
            as_of="2026-08-31",
        )
    with pytest.raises(AccountLedgerError, match="unknown prior event"):
        AccountLedgerRebuilder().rebuild(
            account=account,
            events=(missing_target,),
            as_of="2026-08-31",
        )


def test_full_liquidation_preserves_account_level_realized_pnl_and_fees() -> None:
    account = _account()
    events = (
        _event(
            account=account,
            event_type=AccountEventType.OPENING_CASH,
            event_id="cash",
            gross_amount="10000",
        ),
        _event(
            account=account,
            event_type=AccountEventType.BUY,
            event_id="buy",
            instrument_id=InstrumentId(600519),
            quantity="10",
            price="100",
            fees="1",
        ),
        _event(
            account=account,
            event_type=AccountEventType.SELL,
            event_id="sell",
            instrument_id=InstrumentId(600519),
            quantity="10",
            price="120",
            fees="1",
            tax="1",
        ),
    )

    snapshot = AccountLedgerRebuilder().rebuild(
        account=account,
        events=events,
        as_of="2026-08-31",
    )

    assert snapshot.positions == ()
    assert snapshot.cash.available == Decimal("10197.00")
    assert snapshot.realized_pnl == Decimal("197.00")
    assert snapshot.total_fees == Decimal("3.00")


def test_settlement_date_separates_available_and_settled_balances() -> None:
    account = _account()
    events = (
        _event(
            account=account,
            event_type=AccountEventType.OPENING_CASH,
            event_id="cash",
            gross_amount="1000",
        ),
        _event(
            account=account,
            event_type=AccountEventType.BUY,
            event_id="buy",
            instrument_id=InstrumentId(600519),
            quantity="1",
            price="100",
            fees="1",
            settlement_date="2026-09-01",
        ),
    )

    trade_day = AccountLedgerRebuilder().rebuild(
        account=account,
        events=events,
        as_of="2026-08-31",
    )
    settlement_day = AccountLedgerRebuilder().rebuild(
        account=account,
        events=events,
        as_of="2026-09-01",
    )

    assert trade_day.cash.available == Decimal("899.00")
    assert trade_day.cash.settled == Decimal("1000.00")
    assert trade_day.position(InstrumentId(600519)).available_quantity == Decimal("0")
    assert settlement_day.cash.settled == Decimal("899.00")
    assert settlement_day.position(InstrumentId(600519)).available_quantity == Decimal(
        "1"
    )


def test_position_outflow_rejects_quantity_that_has_not_settled() -> None:
    account = _account()
    future_buy = _event(
        account=account,
        event_type=AccountEventType.BUY,
        event_id="buy",
        instrument_id=InstrumentId(600519),
        quantity="1",
        price="100",
        settlement_date="2026-09-01",
    )
    same_day_sell = _event(
        account=account,
        event_type=AccountEventType.SELL,
        event_id="sell",
        instrument_id=InstrumentId(600519),
        quantity="1",
        price="101",
    )

    with pytest.raises(AccountLedgerError, match="available position"):
        AccountLedgerRebuilder().rebuild(
            account=account,
            events=(future_buy, same_day_sell),
            as_of="2026-08-31",
        )


def test_settlement_date_cannot_precede_trade_date() -> None:
    with pytest.raises(AccountLedgerError, match="settlement_date"):
        _event(
            event_type=AccountEventType.DEPOSIT,
            event_id="invalid-settlement",
            gross_amount="100",
            settlement_date="2026-08-30",
        )
