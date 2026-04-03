"""
Ingestion cursor reader for tracking ingestion progress.

Provides read-only access to ingestion cursor data.
"""

from typing import Any

from ditto_data.models.ingestion import IngestionCursor
from ditto_data.storage.sqlite_client import SQLiteClient


class IngestionCursorReader:
    """
    Reader for ingestion cursors.

    Provides read-only access to ingestion cursors that track the last
    successful and attempted dates per dataset/source pair.

    Table: ingestion_cursor
    - dataset, source: PRIMARY KEY
    - last_success: Last successful trade date (YYYY-MM-DD)
    - last_attempted: Last attempted trade date (YYYY-MM-DD)
    - updated_at: Cursor update timestamp (ISO format)
    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize reader.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    def _row_to_cursor(self, row: dict[str, Any]) -> IngestionCursor:
        """Convert database row to IngestionCursor object."""
        return IngestionCursor(
            dataset=row["dataset"],
            source=row["source"],
            last_success=row["last_success"],
            last_attempted=row["last_attempted"],
            updated_at=row["updated_at"],
        )

    def get_cursor(
        self,
        dataset: str,
        source: str,
    ) -> IngestionCursor | None:
        """
        Get ingestion cursor for a specific dataset/source pair.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (e.g., "tushare")

        Returns:
            IngestionCursor if found, None otherwise.

        """
        sql = """
            SELECT dataset, source, last_success, last_attempted, updated_at
            FROM ingestion_cursor
            WHERE dataset = ? AND source = ?
        """

        row = self._client.fetchone(sql, [dataset, source])

        if not row:
            return None

        return self._row_to_cursor(row)

    def list_cursors(self, source: str | None = None) -> list[IngestionCursor]:
        """
        List all ingestion cursors, optionally filtered by source.

        Args:
            source: Optional data source identifier to filter by.

        Returns:
            List of IngestionCursor objects.

        """
        if source:
            sql = """
                SELECT dataset, source, last_success, last_attempted, updated_at
                FROM ingestion_cursor
                WHERE source = ?
            """
            rows = self._client.fetchall(sql, [source])
        else:
            sql = """
                SELECT dataset, source, last_success, last_attempted, updated_at
                FROM ingestion_cursor
            """
            rows = self._client.fetchall(sql)

        return [self._row_to_cursor(row) for row in rows]

    def get_last_success(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """
        Get the last successful ingestion date for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")

        Returns:
            Last successful trade date (YYYY-MM-DD), or None if no success recorded.

        """
        sql = """
            SELECT last_success
            FROM ingestion_cursor
            WHERE dataset = ? AND source = ?
        """

        row = self._client.fetchone(sql, [dataset, source])

        if not row:
            return None

        return row["last_success"]
