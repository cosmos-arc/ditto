"""
Quarantine writer for failed DQ data.

Provides write access to quarantine data.
"""

import orjson
import polars as pl
from ditto_platform.foundation import SQLiteClient


class QuarantineWriter:
    """SQLite-based quarantine writer for DQ failed data."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize quarantine writer with SQLite client.

        Args:
            sqlite_client: SQLite client with pooled connection

        """
        self._client = sqlite_client

    def save_failed_data(
        self,
        dataset: str,
        rule_id: str,
        severity: str,
        failed_data: pl.DataFrame,
        trade_date: str | None = None,
    ) -> int:
        """
        Save failed data to quarantine.

        Args:
            dataset: Dataset name
            rule_id: Rule that failed
            severity: Severity level (error/warning/alert)
            failed_data: Failed data rows
            trade_date: Optional trade date

        Returns:
            Row ID of inserted record

        """
        # Convert DataFrame to dict for JSON serialization
        # Convert to list of dicts (records format)
        data_dicts = failed_data.to_dicts()
        data_json = orjson.dumps(data_dicts).decode("utf-8")

        cursor = self._client.execute(
            """
            INSERT INTO quarantine_failed_data
            (dataset, rule_id, severity, failed_data, affected_rows, trade_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dataset,
                rule_id,
                severity,
                data_json,
                failed_data.height,
                trade_date,
            ),
        )
        self._client.commit()
        row_id = cursor.lastrowid
        if row_id is None:
            # Fallback: get the last inserted row ID
            row_id = self._client.fetchval("SELECT last_insert_rowid()")
        # Ensure we return int (fetchval returns str | int | float)
        return int(row_id) if row_id is not None else 0

    def clear_old_records(self, days: int = 30) -> int:
        """
        Clear old quarantine records.

        Args:
            days: Delete records older than this many days

        Returns:
            Number of records deleted

        """
        cursor = self._client.execute(
            """
            DELETE FROM quarantine_failed_data
            WHERE julianday('now') - julianday(created_at) > ?
            """,
            (days,),
        )
        self._client.commit()
        return cursor.rowcount
