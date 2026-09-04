"""SQLite account-event journal conformance and atomicity tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_execution.storage.sqlite.account_journal import (
    AccountJournalConflictError,
    SqliteAccountEventJournal,
)
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventJournalPort,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)

NOW = datetime(2026, 8, 31, 9, 30, tzinfo=UTC)


def _account(
    *,
    account_id: str = "manual-main",
    name: str = "我的账户",
) -> AccountDefinition:
    return AccountDefinition(
        account_id=account_id,
        kind=AccountKind.MANUAL,
        name=name,
        opened_at=NOW,
    )


def _buy(
    account: AccountDefinition,
    *,
    event_id: str = "event-buy",
    idempotency_key: str = "idem-buy",
    price: str = "100.1234",
):
    return create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=AccountEventType.BUY,
            event_id=event_id,
            trade_date="2026-08-31",
            settlement_date="2026-09-01",
            recorded_at=NOW,
            idempotency_key=idempotency_key,
            actor="user:chevy",
            source=AccountEventSource.MANUAL_ENTRY,
            instrument_id=InstrumentId(600519),
            quantity=Decimal("100"),
            price=Decimal(price),
            fees=Decimal("5.25"),
            note="逐笔录入",
            attachment_refs=("attachment:receipt-1",),
            external_reference="broker-ref-1",
        ),
    )


def test_sqlite_journal_conforms_and_round_trips_exact_decimal_payload() -> None:
    journal = SqliteAccountEventJournal(":memory:")
    account = journal.create_account(_account())
    event = journal.append(_buy(account))

    assert isinstance(journal, AccountEventJournalPort)
    assert journal.get_account(account.account_id) == account
    assert journal.get_event(account.account_id, event.event_id) == event
    assert (
        journal.find_by_idempotency_key(
            account.account_id,
            event.idempotency_key,
        )
        == event
    )
    assert journal.list_events(account.account_id) == (event,)
    assert journal.list_events(account.account_id)[0].price == Decimal("100.1234")
    journal.close()


def test_account_identity_and_events_are_append_only() -> None:
    journal = SqliteAccountEventJournal(":memory:")
    account = journal.create_account(_account())
    event = journal.append(_buy(account))

    with pytest.raises(AccountJournalConflictError, match="account identity"):
        journal.create_account(_account(name="另一个名字"))
    with pytest.raises(AccountJournalConflictError, match="event_id"):
        journal.append(
            _buy(
                account,
                event_id=event.event_id,
                idempotency_key="another-key",
                price="101",
            )
        )
    with pytest.raises(AccountJournalConflictError, match="idempotency_key"):
        journal.append(
            _buy(
                account,
                event_id="another-event",
                idempotency_key=event.idempotency_key,
                price="101",
            )
        )

    assert journal.list_events(account.account_id) == (event,)
    journal.close()


def test_append_many_rolls_back_every_event_on_conflict() -> None:
    journal = SqliteAccountEventJournal(":memory:")
    account = journal.create_account(_account())
    first = _buy(account, event_id="first", idempotency_key="first-key")
    duplicate_key = _buy(
        account,
        event_id="second",
        idempotency_key="first-key",
    )

    with pytest.raises(AccountJournalConflictError, match="idempotency_key"):
        journal.append_many((first, duplicate_key))

    assert journal.list_events(account.account_id) == ()
    journal.close()


def test_file_journal_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "account-journal.sqlite3"
    account = _account()
    event = _buy(account)

    with SqliteAccountEventJournal(str(path)) as journal:
        journal.create_account(account)
        journal.append(event)

    with SqliteAccountEventJournal(str(path)) as reopened:
        assert reopened.get_account(account.account_id) == account
        assert reopened.list_events(account.account_id) == (event,)


def test_control_event_zero_cash_roundtrips_with_identical_hash(tmp_path: Path) -> None:
    account = _account()
    business = _buy(account)
    reversal = create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=AccountEventType.REVERSAL,
            event_id="reversal",
            trade_date="2026-08-31",
            settlement_date="2026-08-31",
            recorded_at=NOW,
            idempotency_key="reversal",
            actor="user:chevy",
            source=AccountEventSource.MANUAL_ENTRY,
            reverses_event_id=business.event_id,
        ),
    )

    with SqliteAccountEventJournal(str(tmp_path / "journal.sqlite")) as journal:
        journal.create_account(account)
        journal.append_many((business, reversal))

        recovered = journal.get_event(account.account_id, reversal.event_id)

    assert recovered == reversal
    assert recovered.event_hash == reversal.event_hash
