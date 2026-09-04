"""Account-ledger queries rebuild exact as-of views without latest fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)

NOW = datetime(2026, 8, 31, 9, 30, tzinfo=UTC)


class _Journal:
    def __init__(self, account: AccountDefinition, events: tuple[AccountEvent, ...]):
        self.account = account
        self.events = events

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        raise AssertionError("query must not write")

    def get_account(self, account_id: str) -> AccountDefinition | None:
        return self.account if account_id == self.account.account_id else None

    def append(self, event: AccountEvent) -> AccountEvent:
        raise AssertionError("query must not write")

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        return next(
            (event for event in self.events if event.event_id == event_id),
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
                if event.idempotency_key == idempotency_key
            ),
            None,
        )

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        return self.events if account_id == self.account.account_id else ()


def _fixture() -> tuple[AccountDefinition, tuple[AccountEvent, ...]]:
    account = AccountDefinition(
        account_id="manual-main",
        kind=AccountKind.MANUAL,
        name="我的账户",
        opened_at=NOW,
    )
    events = (
        create_account_event(
            account=account,
            draft=AccountEventDraft(
                event_type=AccountEventType.OPENING_CASH,
                event_id="cash",
                trade_date="2026-08-30",
                settlement_date="2026-08-30",
                recorded_at=NOW,
                idempotency_key="cash",
                actor="user:chevy",
                source=AccountEventSource.MANUAL_ENTRY,
                gross_amount=Decimal("100000"),
            ),
        ),
        create_account_event(
            account=account,
            draft=AccountEventDraft(
                event_type=AccountEventType.BUY,
                event_id="buy",
                trade_date="2026-08-31",
                settlement_date="2026-09-01",
                recorded_at=NOW,
                idempotency_key="buy",
                actor="user:chevy",
                source=AccountEventSource.MANUAL_ENTRY,
                instrument_id=InstrumentId(600519),
                quantity=Decimal("100"),
                price=Decimal("100"),
            ),
        ),
    )
    return account, events


def test_query_returns_exact_as_of_events_and_rebuilt_snapshot() -> None:
    account, events = _fixture()
    query = AccountLedgerQuery(journal=_Journal(account, events))

    before_buy = query.get(account_id=account.account_id, as_of="2026-08-30")
    after_buy = query.get(
        account_id=account.account_id,
        as_of="2026-08-31",
        valuation_prices={InstrumentId(600519): Decimal("120")},
    )

    assert tuple(event.event_id for event in before_buy.events) == ("cash",)
    assert before_buy.snapshot.total_value == Decimal("100000.00")
    assert tuple(event.event_id for event in after_buy.events) == ("cash", "buy")
    assert after_buy.snapshot.total_value == Decimal("102000.00")
    assert after_buy.snapshot.valuation_complete is True


def test_query_fails_closed_for_unknown_account_and_invalid_as_of() -> None:
    account, events = _fixture()
    query = AccountLedgerQuery(journal=_Journal(account, events))

    with pytest.raises(AppQueryError) as missing:
        query.get(account_id="missing", as_of="2026-08-31")
    assert missing.value.details == {
        "code": "ACCOUNT_NOT_FOUND",
        "account_id": "missing",
    }

    with pytest.raises(AppQueryError) as invalid:
        query.get(account_id=account.account_id, as_of="latest")
    assert invalid.value.details == {
        "code": "ACCOUNT_AS_OF_INVALID",
        "account_id": account.account_id,
        "as_of": "latest",
    }
