"""Closed-state guarantees for the append-only order journal."""

from __future__ import annotations

import pytest
from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal


def test_sqlite_order_journal_close_is_idempotent_and_fails_closed_afterward() -> None:
    journal = SqliteOrderEventJournal(db_path=":memory:")

    journal.close()
    journal.close()

    with pytest.raises(RuntimeError, match="Journal is closed"):
        journal.all_events()
