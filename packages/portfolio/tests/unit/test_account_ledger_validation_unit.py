"""Fail-closed validation tests for immutable account ledger facts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
    create_account_event,
)

_NOW = datetime(2026, 9, 4, 9, 30, tzinfo=UTC)


def _account(kind: AccountKind = AccountKind.MANUAL) -> AccountDefinition:
    return AccountDefinition(
        account_id=f"account-{kind.value}",
        kind=kind,
        name=f"{kind.value} account",
        opened_at=_NOW,
    )


def _draft(
    event_type: AccountEventType = AccountEventType.DEPOSIT,
) -> AccountEventDraft:
    return AccountEventDraft(
        event_type=event_type,
        event_id="event-1",
        trade_date="2026-09-04",
        settlement_date="2026-09-04",
        recorded_at=_NOW,
        idempotency_key="request-1",
        actor="user:chevy",
        source=AccountEventSource.MANUAL_ENTRY,
        gross_amount=Decimal("100"),
    )


def _event(
    *,
    account: AccountDefinition | None = None,
    draft: AccountEventDraft | None = None,
):
    return create_account_event(
        account=account or _account(),
        draft=draft or _draft(),
    )


def test_account_definition_requires_stable_local_identity() -> None:
    valid = _account()
    with pytest.raises(AccountLedgerError, match="account_id"):
        replace(valid, account_id=" ")
    with pytest.raises(AccountLedgerError, match="name"):
        replace(valid, name=" ")
    with pytest.raises(AccountLedgerError, match="opened_at"):
        replace(valid, opened_at=_NOW.replace(tzinfo=None))
    with pytest.raises(AccountLedgerError, match="currency"):
        replace(valid, currency="USD")


def test_account_acceptance_prevents_cross_account_and_cross_authority_events() -> None:
    manual = _account()
    manual_event = _event(account=manual)
    with pytest.raises(AccountLedgerError, match="account_id mismatch"):
        manual.assert_accepts(replace(manual_event, account_id="another-account"))

    paper = _account(AccountKind.PAPER)
    manual_source_event = _event(
        account=manual,
        draft=replace(_draft(), source=AccountEventSource.MANUAL_ENTRY),
    )
    with pytest.raises(AccountLedgerError, match="PAPER events"):
        paper.assert_accepts(
            replace(
                manual_source_event,
                account_id=paper.account_id,
                account_kind=AccountKind.PAPER,
            )
        )

    paper_source_event = replace(
        manual_event,
        source=AccountEventSource.PAPER_ENGINE,
    )
    with pytest.raises(AccountLedgerError, match="MANUAL events"):
        manual.assert_accepts(paper_source_event)


@pytest.mark.parametrize(
    ("draft", "message"),
    [
        (replace(_draft(), event_type=cast(AccountEventType, "unknown")), "event_type"),
        (replace(_draft(), event_id=" "), "event_id"),
        (replace(_draft(), idempotency_key=" "), "idempotency_key"),
        (replace(_draft(), actor=" "), "actor"),
        (replace(_draft(), recorded_at=_NOW.replace(tzinfo=None)), "recorded_at"),
        (replace(_draft(), currency="USD"), "currency"),
    ],
)
def test_common_event_evidence_is_required(
    draft: AccountEventDraft,
    message: str,
) -> None:
    with pytest.raises(AccountLedgerError, match=message):
        _event(draft=draft)


def test_reversal_cannot_smuggle_correction_or_business_fields() -> None:
    reversal = replace(
        _draft(AccountEventType.REVERSAL),
        gross_amount=Decimal("0"),
        reverses_event_id="event-before",
    )
    with pytest.raises(AccountLedgerError, match="correction fields"):
        _event(draft=replace(reversal, corrects_event_id="event-other"))
    with pytest.raises(AccountLedgerError, match="reversal quantity"):
        _event(draft=replace(reversal, quantity=Decimal("1")))
    with pytest.raises(AccountLedgerError, match="instrument_id must be empty"):
        _event(draft=replace(reversal, instrument_id=InstrumentId(600519)))


def test_correction_requires_one_prior_business_fact_and_business_replacement() -> None:
    correction = replace(
        _draft(AccountEventType.CORRECTION),
        corrects_event_id="event-before",
        replacement_event_type=AccountEventType.DEPOSIT,
    )
    with pytest.raises(AccountLedgerError, match="corrects_event_id"):
        _event(draft=replace(correction, corrects_event_id=None))
    with pytest.raises(AccountLedgerError, match="reverses_event_id"):
        _event(draft=replace(correction, reverses_event_id="event-other"))
    with pytest.raises(AccountLedgerError, match="replacement_event_type is invalid"):
        _event(
            draft=replace(
                correction,
                replacement_event_type=cast(AccountEventType, "unknown"),
            )
        )
    with pytest.raises(AccountLedgerError, match="must be a business event"):
        _event(
            draft=replace(
                correction,
                replacement_event_type=AccountEventType.REVERSAL,
            )
        )


def test_plain_business_event_cannot_carry_control_references() -> None:
    with pytest.raises(AccountLedgerError, match="correction references"):
        _event(draft=replace(_draft(), reverses_event_id="event-before"))
    with pytest.raises(AccountLedgerError, match="replacement_event_type"):
        _event(
            draft=replace(
                _draft(),
                replacement_event_type=AccountEventType.DEPOSIT,
            )
        )


@pytest.mark.parametrize(
    ("draft", "message"),
    [
        (replace(_draft(), gross_amount=Decimal("-1")), "non-negative"),
        (
            replace(
                _draft(AccountEventType.BUY),
                instrument_id=InstrumentId(600519),
                quantity=Decimal("1"),
                price=Decimal("0"),
                gross_amount=Decimal("0"),
            ),
            "price must be positive",
        ),
        (replace(_draft(), gross_amount=Decimal("0")), "gross_amount must be positive"),
        (
            replace(
                _draft(AccountEventType.SPLIT),
                instrument_id=InstrumentId(600519),
                quantity=Decimal("0"),
                gross_amount=Decimal("0"),
            ),
            "quantity must be positive",
        ),
    ],
)
def test_business_economics_fail_closed(
    draft: AccountEventDraft,
    message: str,
) -> None:
    with pytest.raises(AccountLedgerError, match=message):
        _event(draft=draft)


@pytest.mark.parametrize(
    "quantity",
    [cast(Decimal, "1"), Decimal("NaN")],
)
def test_decimal_fields_reject_wrong_type_and_non_finite_values(
    quantity: Decimal,
) -> None:
    with pytest.raises(AccountLedgerError, match="quantity must be"):
        _event(draft=replace(_draft(), quantity=quantity))
