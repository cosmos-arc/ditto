"""
SQLite provider for the portfolio ``AccountEventJournalPort`` contract.

The schema is intentionally fresh and separate from legacy execution snapshot
tables. Decimal values are stored as canonical strings inside the immutable JSON
payload, avoiding binary floating-point drift during replay.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)

from ditto_execution.errors import ExecutionError

__all__ = [
    "AccountJournalConflictError",
    "AccountJournalIntegrityError",
    "SqliteAccountEventJournal",
]


class AccountJournalConflictError(ExecutionError):
    """An immutable account identity or append-only event already exists."""


class AccountJournalIntegrityError(ExecutionError):
    """Persisted account-journal data failed validation."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_journal_accounts (
    account_id TEXT PRIMARY KEY,
    account_kind TEXT NOT NULL,
    account_name TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    currency TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_journal_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES account_journal_accounts(account_id),
    UNIQUE (account_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_account_journal_events_account_seq
    ON account_journal_events(account_id, event_seq);
"""

_INSERT_ACCOUNT = """
INSERT INTO account_journal_accounts
    (account_id, account_kind, account_name, opened_at, currency)
VALUES (?, ?, ?, ?, ?)
"""

_SELECT_ACCOUNT = """
SELECT account_id, account_kind, account_name, opened_at, currency
FROM account_journal_accounts
WHERE account_id = ?
"""

_INSERT_EVENT = """
INSERT INTO account_journal_events
    (event_id, account_id, idempotency_key, event_hash, payload_json)
VALUES (?, ?, ?, ?, ?)
"""

_SELECT_EVENT = """
SELECT payload_json
FROM account_journal_events
WHERE account_id = ? AND event_id = ?
"""

_SELECT_IDEMPOTENCY = """
SELECT payload_json
FROM account_journal_events
WHERE account_id = ? AND idempotency_key = ?
"""

_LIST_EVENTS = """
SELECT payload_json
FROM account_journal_events
WHERE account_id = ?
ORDER BY event_seq ASC
"""


class SqliteAccountEventJournal(AbstractContextManager["SqliteAccountEventJournal"]):
    """Fresh SQLite append-only journal for PAPER and MANUAL accounts."""

    _client: SQLiteClient | None

    def __init__(self, database: str | SQLiteClient) -> None:
        """Bind a pooled client or own a pool for a standalone database path."""
        if isinstance(database, str):
            owned_pool = SQLitePool(database)
            client = SQLiteClient(owned_pool)
        else:
            owned_pool = None
            client = database
        connection = client.conn
        connection.executescript(_SCHEMA)
        connection.commit()
        self._client = client
        self._owned_pool = owned_pool

    @property
    def _db(self) -> sqlite3.Connection:
        """Return the live connection or fail after close."""
        if self._client is None:
            raise AccountJournalIntegrityError("account journal is closed")
        return self._client.conn

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        """Create an immutable identity or replay the exact existing identity."""
        existing = self.get_account(account.account_id)
        if existing is not None:
            if existing != account:
                raise AccountJournalConflictError(
                    f"account identity conflict: {account.account_id}"
                )
            return existing
        try:
            self._db.execute(
                _INSERT_ACCOUNT,
                (
                    account.account_id,
                    account.kind.value,
                    account.name,
                    account.opened_at.isoformat(),
                    account.currency,
                ),
            )
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise AccountJournalConflictError(
                f"account identity conflict: {account.account_id}"
            ) from exc
        return account

    def get_account(self, account_id: str) -> AccountDefinition | None:
        """Read one exact account definition."""
        row = self._db.execute(_SELECT_ACCOUNT, (account_id,)).fetchone()
        if row is None:
            return None
        return _account_from_row(row)

    def append(self, event: AccountEvent) -> AccountEvent:
        """Append exactly one immutable event."""
        return self.append_many((event,))[0]

    def append_many(
        self,
        events: tuple[AccountEvent, ...],
    ) -> tuple[AccountEvent, ...]:
        """Append a batch atomically and roll back every row on any conflict."""
        if not events:
            return ()
        connection = self._db
        try:
            connection.execute("BEGIN IMMEDIATE")
            for event in events:
                self._append_uncommitted(event)
            connection.commit()
        except AccountJournalConflictError:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise AccountJournalConflictError("account event append conflict") from exc
        except Exception:
            connection.rollback()
            raise
        return events

    def _append_uncommitted(self, event: AccountEvent) -> None:
        account = self.get_account(event.account_id)
        if account is None:
            raise AccountJournalConflictError(f"account not found: {event.account_id}")
        account.assert_accepts(event)
        if self.get_event(event.account_id, event.event_id) is not None:
            raise AccountJournalConflictError(f"event_id conflict: {event.event_id}")
        if (
            self.find_by_idempotency_key(
                event.account_id,
                event.idempotency_key,
            )
            is not None
        ):
            raise AccountJournalConflictError(
                f"idempotency_key conflict: {event.idempotency_key}"
            )
        self._db.execute(
            _INSERT_EVENT,
            (
                event.event_id,
                event.account_id,
                event.idempotency_key,
                event.event_hash,
                _serialize_event(event),
            ),
        )

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        """Read one exact event without falling back to latest."""
        row = self._db.execute(_SELECT_EVENT, (account_id, event_id)).fetchone()
        return self._event_from_row(account_id, row) if row is not None else None

    def find_by_idempotency_key(
        self,
        account_id: str,
        idempotency_key: str,
    ) -> AccountEvent | None:
        """Resolve one exact idempotent append receipt."""
        row = self._db.execute(
            _SELECT_IDEMPOTENCY,
            (account_id, idempotency_key),
        ).fetchone()
        return self._event_from_row(account_id, row) if row is not None else None

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        """Read the complete stream in durable append order."""
        rows = self._db.execute(_LIST_EVENTS, (account_id,)).fetchall()
        return tuple(self._event_from_row(account_id, row) for row in rows)

    def _event_from_row(
        self,
        account_id: str,
        row: sqlite3.Row,
    ) -> AccountEvent:
        account = self.get_account(account_id)
        if account is None:
            raise AccountJournalIntegrityError(
                f"event account identity missing: {account_id}"
            )
        try:
            return _deserialize_event(_row_text(row, "payload_json"), account)
        except (KeyError, TypeError, ValueError) as exc:
            raise AccountJournalIntegrityError(
                f"invalid persisted account event: {account_id}"
            ) from exc

    def close(self) -> None:
        """Close the journal idempotently."""
        if self._client is not None:
            if self._owned_pool is not None:
                self._owned_pool.close_all()
            self._client = None
            self._owned_pool = None

    def __enter__(self) -> SqliteAccountEventJournal:
        """Enter a managed journal lifetime."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the journal when leaving a managed lifetime."""
        self.close()


def _serialize_event(event: AccountEvent) -> str:
    payload = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "trade_date": event.trade_date,
        "settlement_date": event.settlement_date,
        "recorded_at": event.recorded_at.isoformat(),
        "idempotency_key": event.idempotency_key,
        "actor": event.actor,
        "source": event.source.value,
        "instrument_id": (
            int(event.instrument_id) if event.instrument_id is not None else None
        ),
        "currency": event.currency,
        "quantity": format(event.quantity, "f"),
        "price": format(event.price, "f"),
        "gross_amount": format(event.gross_amount, "f"),
        "fees": format(event.fees, "f"),
        "tax": format(event.tax, "f"),
        "net_cash": format(event.net_cash, "f"),
        "note": event.note,
        "attachment_refs": event.attachment_refs,
        "external_reference": event.external_reference,
        "reverses_event_id": event.reverses_event_id,
        "corrects_event_id": event.corrects_event_id,
        "replacement_event_type": (
            event.replacement_event_type.value
            if event.replacement_event_type is not None
            else None
        ),
        "event_hash": event.event_hash,
    }
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()


def _deserialize_event(payload_json: str, account: AccountDefinition) -> AccountEvent:
    payload = cast("Mapping[str, object]", orjson.loads(payload_json))
    replacement_raw = _optional_text(payload, "replacement_event_type")
    instrument_raw = payload.get("instrument_id")
    instrument_id = (
        InstrumentId(_integer(instrument_raw, "instrument_id"))
        if instrument_raw is not None
        else None
    )
    attachment_raw = payload.get("attachment_refs", ())
    if not isinstance(attachment_raw, Sequence) or isinstance(
        attachment_raw, str | bytes
    ):
        raise ValueError("attachment_refs must be a sequence")
    attachments = tuple(str(item) for item in cast("Sequence[object]", attachment_raw))
    event = create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=AccountEventType(_text(payload, "event_type")),
            event_id=_text(payload, "event_id"),
            trade_date=_text(payload, "trade_date"),
            settlement_date=_text(payload, "settlement_date"),
            recorded_at=datetime.fromisoformat(_text(payload, "recorded_at")),
            idempotency_key=_text(payload, "idempotency_key"),
            actor=_text(payload, "actor"),
            source=AccountEventSource(_text(payload, "source")),
            instrument_id=instrument_id,
            currency=_text(payload, "currency"),
            quantity=Decimal(_text(payload, "quantity")),
            price=Decimal(_text(payload, "price")),
            gross_amount=Decimal(_text(payload, "gross_amount")),
            fees=Decimal(_text(payload, "fees")),
            tax=Decimal(_text(payload, "tax")),
            net_cash=Decimal(_text(payload, "net_cash")),
            note=_text(payload, "note"),
            attachment_refs=attachments,
            external_reference=_optional_text(payload, "external_reference"),
            reverses_event_id=_optional_text(payload, "reverses_event_id"),
            corrects_event_id=_optional_text(payload, "corrects_event_id"),
            replacement_event_type=(
                AccountEventType(replacement_raw)
                if replacement_raw is not None
                else None
            ),
        ),
    )
    if event.event_hash != _text(payload, "event_hash"):
        raise ValueError("persisted event hash mismatch")
    return event


def _account_from_row(row: sqlite3.Row) -> AccountDefinition:
    return AccountDefinition(
        account_id=_row_text(row, "account_id"),
        kind=AccountKind(_row_text(row, "account_kind")),
        name=_row_text(row, "account_name"),
        opened_at=datetime.fromisoformat(_row_text(row, "opened_at")),
        currency=_row_text(row, "currency"),
    )


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise AccountJournalIntegrityError(f"{key} must be text")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return value


def _optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text or null")
    return value


def _integer(value: object, key: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value
