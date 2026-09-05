"""Replay-integrity and position-transition tests for account projections."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
    create_account_event,
    ledger_event_hash,
    ledger_event_values,
)
from ditto_portfolio.account_projection import AccountLedgerRebuilder

_NOW = datetime(2026, 9, 4, 9, 30, tzinfo=UTC)
_AS_OF = "2026-09-04"


def _account() -> AccountDefinition:
    return AccountDefinition(
        account_id="manual-main",
        kind=AccountKind.MANUAL,
        name="Manual account",
        opened_at=_NOW,
    )


def _event(
    event_type: AccountEventType,
    event_id: str,
    *,
    instrument_id: InstrumentId | None = None,
    quantity: str = "0",
    price: str = "0",
    gross_amount: str = "0",
    fees: str = "0",
    idempotency_key: str | None = None,
    settlement_date: str = _AS_OF,
    reverses_event_id: str | None = None,
    corrects_event_id: str | None = None,
    replacement_event_type: AccountEventType | None = None,
) -> AccountEvent:
    return create_account_event(
        account=_account(),
        draft=AccountEventDraft(
            event_type=event_type,
            event_id=event_id,
            trade_date=_AS_OF,
            settlement_date=settlement_date,
            recorded_at=_NOW,
            idempotency_key=idempotency_key or f"request-{event_id}",
            actor="user:chevy",
            source=AccountEventSource.MANUAL_ENTRY,
            instrument_id=instrument_id,
            quantity=Decimal(quantity),
            price=Decimal(price),
            gross_amount=Decimal(gross_amount),
            fees=Decimal(fees),
            reverses_event_id=reverses_event_id,
            corrects_event_id=corrects_event_id,
            replacement_event_type=replacement_event_type,
        ),
    )


def _rehash(event: AccountEvent) -> AccountEvent:
    return replace(event, event_hash=ledger_event_hash(ledger_event_values(event)))


def test_snapshot_position_lookup_scans_exact_identity_and_fails_closed() -> None:
    first = InstrumentId(1)
    second = InstrumentId(2)
    snapshot = AccountLedgerRebuilder().rebuild(
        account=_account(),
        events=(
            _event(
                AccountEventType.OPENING_POSITION,
                "first",
                instrument_id=first,
                quantity="1",
                price="10",
                gross_amount="10",
            ),
            _event(
                AccountEventType.OPENING_POSITION,
                "second",
                instrument_id=second,
                quantity="2",
                price="10",
                gross_amount="20",
            ),
        ),
        as_of=_AS_OF,
    )

    assert snapshot.position(second).quantity == Decimal("2")
    with pytest.raises(AccountLedgerError, match="position not found"):
        snapshot.position(InstrumentId(3))


def test_stream_rejects_duplicate_idempotency_and_tampered_hash() -> None:
    first = _event(
        AccountEventType.DEPOSIT,
        "first",
        gross_amount="10",
        idempotency_key="same-request",
    )
    second = _event(
        AccountEventType.DEPOSIT,
        "second",
        gross_amount="20",
        idempotency_key="same-request",
    )
    with pytest.raises(AccountLedgerError, match="duplicate idempotency_key"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(first, second), as_of=_AS_OF
        )

    with pytest.raises(AccountLedgerError, match="event hash mismatch"):
        AccountLedgerRebuilder().rebuild(
            account=_account(),
            events=(replace(first, event_hash="tampered"),),
            as_of=_AS_OF,
        )


def test_correction_can_target_only_a_prior_business_event() -> None:
    business = _event(AccountEventType.DEPOSIT, "business", gross_amount="10")
    correction = _event(
        AccountEventType.CORRECTION,
        "correction-1",
        gross_amount="20",
        corrects_event_id=business.event_id,
        replacement_event_type=AccountEventType.DEPOSIT,
    )
    nested_correction = _event(
        AccountEventType.CORRECTION,
        "correction-2",
        gross_amount="30",
        corrects_event_id=correction.event_id,
        replacement_event_type=AccountEventType.DEPOSIT,
    )

    with pytest.raises(AccountLedgerError, match="prior business event"):
        AccountLedgerRebuilder().rebuild(
            account=_account(),
            events=(business, correction, nested_correction),
            as_of=_AS_OF,
        )


def test_reversal_suppresses_exact_prior_effect_without_deleting_history() -> None:
    business = _event(AccountEventType.DEPOSIT, "business", gross_amount="10")
    reversal = _event(
        AccountEventType.REVERSAL,
        "reversal",
        reverses_event_id=business.event_id,
    )
    snapshot = AccountLedgerRebuilder().rebuild(
        account=_account(),
        events=(business, reversal),
        as_of=_AS_OF,
    )
    assert snapshot.cash.available == Decimal("0.00")
    assert snapshot.event_count == 2


def test_replay_rejects_tampered_non_business_event_type() -> None:
    business = _event(AccountEventType.DEPOSIT, "business", gross_amount="10")
    tampered = replace(
        business,
        event_type=cast(AccountEventType, "unknown"),
    )
    tampered = _rehash(tampered)

    with pytest.raises(AccountLedgerError, match="no applicable business type"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(tampered,), as_of=_AS_OF
        )


def test_fee_and_sell_events_update_account_level_economics() -> None:
    instrument_id = InstrumentId(600519)
    opening = _event(
        AccountEventType.OPENING_POSITION,
        "opening",
        instrument_id=instrument_id,
        quantity="10",
        price="10",
        gross_amount="100",
    )
    sell = _event(
        AccountEventType.SELL,
        "sell",
        instrument_id=instrument_id,
        quantity="1",
        price="12",
        gross_amount="12",
        fees="1",
    )
    fee = _event(AccountEventType.FEE, "fee", gross_amount="2")
    snapshot = AccountLedgerRebuilder().rebuild(
        account=_account(), events=(opening, sell, fee), as_of=_AS_OF
    )

    assert snapshot.position(instrument_id).quantity == Decimal("9")
    assert snapshot.realized_pnl == Decimal("1.00")
    assert snapshot.total_fees == Decimal("3.00")


def test_replay_rejects_position_event_with_tampered_instrument_identity() -> None:
    buy = _event(
        AccountEventType.BUY,
        "buy",
        instrument_id=InstrumentId(600519),
        quantity="1",
        price="10",
        gross_amount="10",
    )
    tampered = _rehash(replace(buy, instrument_id=None))

    with pytest.raises(AccountLedgerError, match="position event requires"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(tampered,), as_of=_AS_OF
        )


def test_corporate_action_requires_existing_position_and_instrument_identity() -> None:
    split = _event(
        AccountEventType.SPLIT,
        "split",
        instrument_id=InstrumentId(600519),
        quantity="1",
    )
    with pytest.raises(AccountLedgerError, match="position not found"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(split,), as_of=_AS_OF
        )

    tampered = _rehash(replace(split, instrument_id=None))
    with pytest.raises(AccountLedgerError, match="requires instrument_id"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(tampered,), as_of=_AS_OF
        )


def test_merge_must_leave_positive_total_and_available_quantities() -> None:
    instrument_id = InstrumentId(600519)
    opening = _event(
        AccountEventType.OPENING_POSITION,
        "opening",
        instrument_id=instrument_id,
        quantity="10",
        price="10",
        gross_amount="100",
    )
    remove_all = _event(
        AccountEventType.MERGE,
        "merge-all",
        instrument_id=instrument_id,
        quantity="10",
    )
    with pytest.raises(AccountLedgerError, match="leave positive quantity"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(opening, remove_all), as_of=_AS_OF
        )

    unsettled = replace(opening, settlement_date="2026-09-05")
    unsettled = _rehash(unsettled)
    remove_one = _event(
        AccountEventType.MERGE,
        "merge-one",
        instrument_id=instrument_id,
        quantity="1",
    )
    with pytest.raises(AccountLedgerError, match="available quantity"):
        AccountLedgerRebuilder().rebuild(
            account=_account(), events=(unsettled, remove_one), as_of=_AS_OF
        )
