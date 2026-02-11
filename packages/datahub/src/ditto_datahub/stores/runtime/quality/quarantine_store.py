"""
Quarantine store for failed DQ data.

Migrated from stores/quarantine_store.py to runtime/quality/
"""

from typing import Any

import orjson
import polars as pl
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import logger


class QuarantineStore:
    """SQLite-based quarantine store for DQ failed data."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize quarantine store with SQLite client.

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

    def get_quarantined_data(
        self,
        dataset: str | None = None,
        rule_id: str | None = None,
        limit: int = 1000,
    ) -> pl.DataFrame:
        """
        Get quarantined data.

        Args:
            dataset: Filter by dataset (optional)
            rule_id: Filter by rule ID (optional)
            limit: Maximum rows to return

        Returns:
            DataFrame with quarantined data

        """
        query = "SELECT * FROM quarantine_failed_data WHERE 1=1"
        params: list[Any] = []

        if dataset:
            query += " AND dataset = ?"
            params.append(dataset)

        if rule_id:
            query += " AND rule_id = ?"
            params.append(rule_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = self._client.execute(query, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        return pl.DataFrame(rows, schema=columns, orient="row")

    def get_failed_data_df(self, row_id: int) -> pl.DataFrame:
        """
        Get failed data DataFrame by row ID.

        Args:
            row_id: Quarantine record ID

        Returns:
            Failed data as DataFrame, or empty DataFrame if not found or parse failed

        """
        row = self._client.fetchone(
            "SELECT failed_data FROM quarantine_failed_data WHERE id = ?",
            (row_id,),
        )

        if not row:
            return pl.DataFrame()

        # Parse JSON back to DataFrame
        try:
            data_dicts = orjson.loads(row["failed_data"])
            return pl.DataFrame(data_dicts)
        except (orjson.JSONDecodeError, pl.exceptions.SchemaError) as e:
            logger.error(
                "Failed to parse quarantined data",
                event="quarantine_parse_failed",
                row_id=row_id,
                error=str(e),
            )
            return pl.DataFrame()

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

    def get_stats(self) -> list[dict[str, Any]]:
        """
        Get quarantine statistics.

        Returns:
            Dictionary with stats

        """
        rows = self._client.fetchall("""
            SELECT
                dataset,
                rule_id,
                severity,
                COUNT(*) as count,
                SUM(affected_rows) as total_affected
            FROM quarantine_failed_data
            GROUP BY dataset, rule_id, severity
            ORDER BY count DESC
        """)
        return [
            {
                "dataset": row["dataset"],
                "rule_id": row["rule_id"],
                "severity": row["severity"],
                "count": row["count"],
                "total_affected": row["total_affected"],
            }
            for row in rows
        ]

    def __enter__(self) -> "QuarantineStore":
        """Context manager entry."""
        return self

    def __exit__(self, *_args: Any) -> None:
        """
        Context manager exit.

        Connection is managed by SQLitePool, no need to close here.
        """
        pass
