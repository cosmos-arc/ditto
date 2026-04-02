"""
Ingestion cursor writer for tracking ingestion progress.

Provides write access to ingestion cursor data.
"""

from datetime import datetime
from typing import Any

from ditto_data.models.ingestion import IngestionCursor
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import logger


class IngestionCursorWriter:
    """
    Writer for ingestion cursors.

    Provides write access to ingestion cursors that track the last
    successful and attempted dates per dataset/source pair.

    Table: ingestion_cursor
    - dataset, source: PRIMARY KEY
    - last_success: Last successful trade date (YYYY-MM-DD)
    - last_attempted: Last attempted trade date (YYYY-MM-DD)
    - updated_at: Cursor update timestamp (ISO format)
    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize writer.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client
        self._create_tables()
        logger.debug(
            "IngestionCursorWriter initialized",
            event="ingestion_cursor_writer_init",
        )

    def _create_tables(self) -> None:
        """Create ingestion_cursor table if not exists."""
        sql = """
            CREATE TABLE IF NOT EXISTS ingestion_cursor (
                dataset TEXT NOT NULL,
                source TEXT NOT NULL,
                last_success TEXT,
                last_attempted TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (dataset, source)
            )
        """
        self._client.execute(sql)

        index_sql = """
            CREATE INDEX IF NOT EXISTS idx_ingestion_cursor_source
            ON ingestion_cursor(source)
        """
        self._client.execute(index_sql)

        self._client.commit()
        logger.debug(
            "ingestion_cursor table created/verified",
            event="ingestion_cursor_table_created",
        )

    def _row_to_cursor(self, row: dict[str, Any]) -> IngestionCursor:
        """Convert database row to IngestionCursor object."""
        return IngestionCursor(
            dataset=row["dataset"],
            source=row["source"],
            last_success=row["last_success"],
            last_attempted=row["last_attempted"],
            updated_at=row["updated_at"],
        )

    def upsert_cursor(self, cursor: IngestionCursor) -> IngestionCursor:
        """
        Save or update ingestion cursor record (atomic UPSERT).

        Uses SQLite's ON CONFLICT clause to atomically handle concurrent writes.

        Args:
            cursor: IngestionCursor object to save.

        Returns:
            The saved IngestionCursor with updated timestamp.

        """
        now = datetime.now().isoformat()

        sql = """
            INSERT INTO ingestion_cursor
            (dataset, source, last_success, last_attempted, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(dataset, source)
            DO UPDATE SET
                last_success = excluded.last_success,
                last_attempted = excluded.last_attempted,
                updated_at = excluded.updated_at
            RETURNING dataset, source, last_success, last_attempted, updated_at
        """

        row = self._client.fetchone(
            sql,
            [
                cursor.dataset,
                cursor.source,
                cursor.last_success,
                cursor.last_attempted,
                now,
            ],
        )

        if row is None:
            raise RuntimeError(
                "UPSERT RETURNING should always return a row but got None"
            )

        self._client.commit()

        result = self._row_to_cursor(row)

        logger.debug(
            "Ingestion cursor saved",
            event="ingestion_cursor_saved",
            dataset=cursor.dataset,
            source=cursor.source,
            last_success=cursor.last_success,
            last_attempted=cursor.last_attempted,
        )

        return result
