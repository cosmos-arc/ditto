"""
Quarantine reader for failed DQ data.

Provides read-only access to quarantine data.
"""

from typing import Any

import orjson
import polars as pl
from ditto_platform.foundation import logger
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient


class QuarantineReader:
    """SQLite-based quarantine reader for DQ failed data."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize quarantine reader with SQLite client.

        Args:
            sqlite_client: SQLite client with pooled connection

        """
        self._client = sqlite_client

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
