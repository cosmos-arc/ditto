"""SQLite readers and writers for execution account snapshots."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import SQLiteClient

from ditto_execution.models import AccountSnapshotRecord

__all__ = [
    "ACCOUNT_SNAPSHOTS_DDL",
    "AccountSnapshotReader",
    "AccountSnapshotWriter",
]

_CREATE_ACCOUNT_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    snapshot_id     TEXT PRIMARY KEY,
    run_id          TEXT    NOT NULL,
    strategy_id     TEXT    NOT NULL,
    account_id      TEXT    NOT NULL,
    snapshot_date   TEXT    NOT NULL,
    cash_available  REAL    NOT NULL,
    cash_settled    REAL    NOT NULL,
    cash_frozen     REAL    NOT NULL,
    total_value     REAL    NOT NULL,
    nav             REAL    NOT NULL,
    exposure        REAL    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_ACCOUNT_SNAPSHOTS_RUN_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_account_snapshots_run_date "
    "ON account_snapshots(run_id, snapshot_date);"
)

_CREATE_IDX_ACCOUNT_SNAPSHOTS_STRATEGY_ACCOUNT_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_account_snapshots_strategy_account_date "
    "ON account_snapshots(strategy_id, account_id, snapshot_date);"
)

_INSERT_ACCOUNT_SNAPSHOT = """
INSERT OR REPLACE INTO account_snapshots
    (snapshot_id, run_id, strategy_id, account_id, snapshot_date,
     cash_available, cash_settled, cash_frozen, total_value, nav,
     exposure, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_LATEST_ACCOUNT_SNAPSHOT = """
SELECT * FROM account_snapshots
WHERE run_id = ? AND account_id = ?
ORDER BY snapshot_date DESC, created_at DESC
LIMIT 1
"""

_LIST_ACCOUNT_SNAPSHOTS = """
SELECT * FROM account_snapshots
WHERE run_id = ?
  AND (? IS NULL OR strategy_id = ?)
  AND (? IS NULL OR account_id = ?)
  AND (? IS NULL OR snapshot_date = ?)
ORDER BY snapshot_date ASC, created_at ASC
"""

ACCOUNT_SNAPSHOTS_DDL = (
    _CREATE_ACCOUNT_SNAPSHOTS_TABLE
    + _CREATE_IDX_ACCOUNT_SNAPSHOTS_RUN_DATE
    + _CREATE_IDX_ACCOUNT_SNAPSHOTS_STRATEGY_ACCOUNT_DATE
)


class AccountSnapshotReader:
    """Read execution account snapshots from the ``account_snapshots`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get_latest(
        self,
        run_id: str,
        account_id: str,
    ) -> AccountSnapshotRecord | None:
        """Return the latest account snapshot for one run and account."""
        row = self._client.fetchone(_GET_LATEST_ACCOUNT_SNAPSHOT, (run_id, account_id))
        return self._row_to_account_snapshot(row) if row else None

    def list(
        self,
        run_id: str,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        snapshot_date: str | None = None,
    ) -> list[AccountSnapshotRecord]:
        """Return account snapshots matching the requested filters."""
        rows = self._client.fetchall(
            _LIST_ACCOUNT_SNAPSHOTS,
            (
                run_id,
                strategy_id,
                strategy_id,
                account_id,
                account_id,
                snapshot_date,
                snapshot_date,
            ),
        )
        return [self._row_to_account_snapshot(row) for row in rows]

    @staticmethod
    def _row_to_account_snapshot(row: dict[str, Any]) -> AccountSnapshotRecord:
        return AccountSnapshotRecord(**row)


class AccountSnapshotWriter:
    """Write execution account snapshots to the ``account_snapshots`` table."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: AccountSnapshotRecord) -> None:
        """Persist an account snapshot."""
        self._client.execute(
            _INSERT_ACCOUNT_SNAPSHOT,
            (
                record.snapshot_id,
                record.run_id,
                record.strategy_id,
                record.account_id,
                record.snapshot_date,
                record.cash_available,
                record.cash_settled,
                record.cash_frozen,
                record.total_value,
                record.nav,
                record.exposure,
                record.created_at,
            ),
        )
        self._client.commit()
