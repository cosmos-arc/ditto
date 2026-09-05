"""SQLite account-event journal conformance and atomicity tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_execution.storage.sqlite.account_journal import (
    AccountJournalConflictError,
    AccountJournalIntegrityError,
    SqliteAccountEventJournal,
)
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient
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


def _stored_payload(client: SQLiteClient, event_id: str) -> dict[str, object]:
    row = client.conn.execute(
        "SELECT payload_json FROM account_journal_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    assert row is not None
    return cast(dict[str, object], orjson.loads(cast(str, row["payload_json"])))


def _replace_stored_payload(
    client: SQLiteClient,
    event_id: str,
    payload: dict[str, object],
) -> None:
    client.conn.execute(
        "UPDATE account_journal_events SET payload_json = ? WHERE event_id = ?",
        (orjson.dumps(payload).decode(), event_id),
    )
    client.conn.commit()


def test_empty_append_exact_account_replay_and_missing_account_fail_closed() -> None:
    journal = SqliteAccountEventJournal(":memory:")
    account = _account()

    assert journal.get_account(account.account_id) is None
    assert journal.append_many(()) == ()
    assert journal.create_account(account) == account
    assert journal.create_account(account) == account

    missing_account = _account(account_id="missing")
    with pytest.raises(AccountJournalConflictError, match="account not found"):
        journal.append(_buy(missing_account))

    journal.close()
    journal.close()
    with pytest.raises(AccountJournalIntegrityError, match="closed"):
        journal.get_account(account.account_id)


def test_recovery_requires_event_account_identity(sqlite_client: SQLiteClient) -> None:
    journal = SqliteAccountEventJournal(sqlite_client)
    account = journal.create_account(_account())
    event = journal.append(_buy(account))

    sqlite_client.conn.execute("PRAGMA foreign_keys = OFF")
    sqlite_client.conn.execute(
        "DELETE FROM account_journal_accounts WHERE account_id = ?",
        (account.account_id,),
    )
    sqlite_client.conn.commit()

    with pytest.raises(AccountJournalIntegrityError, match="identity missing"):
        journal.get_event(account.account_id, event.event_id)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("attachment_refs", "not-a-sequence", "attachment_refs"),
        ("event_type", 1, "event_type must be text"),
        ("external_reference", 1, "external_reference must be text"),
        ("instrument_id", "600519", "instrument_id must be an integer"),
        ("event_hash", "tampered", "hash mismatch"),
    ],
)
def test_recovery_rejects_tampered_event_payload(
    sqlite_client: SQLiteClient,
    field: str,
    value: object,
    message: str,
) -> None:
    journal = SqliteAccountEventJournal(sqlite_client)
    account = journal.create_account(_account())
    event = journal.append(_buy(account))
    payload = _stored_payload(sqlite_client, event.event_id)
    payload[field] = value
    _replace_stored_payload(sqlite_client, event.event_id, payload)

    with pytest.raises(
        AccountJournalIntegrityError,
        match="invalid persisted account event",
    ) as exc_info:
        journal.get_event(account.account_id, event.event_id)
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert message in str(exc_info.value.__cause__)


def test_recovery_rejects_non_text_account_columns(
    sqlite_client: SQLiteClient,
) -> None:
    journal = SqliteAccountEventJournal(sqlite_client)
    account = journal.create_account(_account())
    sqlite_client.conn.execute(
        "UPDATE account_journal_accounts SET account_name = ? WHERE account_id = ?",
        (sqlite3.Binary(b"invalid"), account.account_id),
    )
    sqlite_client.conn.commit()

    with pytest.raises(AccountJournalIntegrityError, match="account_name must be text"):
        journal.get_account(account.account_id)
