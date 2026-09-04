"""Physical store diagnostics used by the Q4 acceptance composition root."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal

__all__ = ["acceptance_opened_at", "count_acceptance_rows"]

_COUNT_TABLES = frozenset({"paper_sessions", "paper_executions"})


def acceptance_opened_at(
    database: Path,
    *,
    account_ids: tuple[str, ...],
) -> datetime | None:
    """Recover the immutable bootstrap time from any persisted account identity."""
    if not database.exists():
        return None
    with SqliteAccountEventJournal(str(database)) as journal:
        accounts = tuple(
            account
            for account_id in account_ids
            if (account := journal.get_account(account_id)) is not None
        )
    opened_at = {account.opened_at for account in accounts}
    if len(opened_at) > 1:
        raise ValueError("acceptance account bootstrap timestamps drifted")
    return next(iter(opened_at)) if opened_at else None


def count_acceptance_rows(database: Path, table: str) -> int:
    """Count rows in one fixed acceptance table after stores have closed."""
    if table not in _COUNT_TABLES:
        raise ValueError("unsupported acceptance count table")
    with sqlite3.connect(database) as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 - exact allowlist above
    return int(row[0]) if row is not None else 0
