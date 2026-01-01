"""Ingestion cursor store for tracking ingestion progress (denormalized cache)."""

from datetime import datetime

from ditto_foundation import logger

from ditto_datahub.sources.metadata import IngestionCursor
from ditto_datahub.stores.sqlite_client import SQLiteClient


class IngestionCursorStore:
    """
    Store for ingestion cursors (denormalized progress cache).

    Cursors provide O(1) access to the last successful and attempted dates,
    avoiding expensive MAX() queries on the ingestion_log table.

    Table: ingestion_cursor
    - dataset: PRIMARY KEY
    - source: Data source identifier
    - last_success: Last successful trade date (YYYY-MM-DD)
    - last_attempted: Last attempted trade date including FAIL (YYYY-MM-DD)
    - updated_at: Cursor update timestamp (ISO format)

    Invariants:
    - last_success only updated on SUCCESS
    - last_attempted updated on any attempt (SUCCESS or FAIL)
    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize store.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client
        self._create_tables()
        logger.debug(
            "IngestionCursorStore initialized",
            event="ingestion_cursor_store_init",
        )

    def _create_tables(self) -> None:
        """Create ingestion_cursor table if not exists."""
        sql = """
            CREATE TABLE IF NOT EXISTS ingestion_cursor (
                dataset TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                last_success TEXT,
                last_attempted TEXT,
                updated_at TEXT NOT NULL
            )
        """
        self._client.execute(sql)
        self._client.commit()
        logger.debug(
            "ingestion_cursor table created/verified",
            event="ingestion_cursor_table_created",
        )

    def get_cursor(self, dataset: str) -> IngestionCursor | None:
        """
        Get cursor for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")

        Returns:
            IngestionCursor if found, None otherwise.

        """
        sql = """
            SELECT dataset, source, last_success, last_attempted, updated_at
            FROM ingestion_cursor
            WHERE dataset = ?
        """

        row = self._client.fetchone(sql, [dataset])

        if not row:
            return None

        return IngestionCursor(
            dataset=row["dataset"],
            source=row["source"],
            last_success=row["last_success"],
            last_attempted=row["last_attempted"],
            updated_at=row["updated_at"],
        )

    def update_success(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionCursor:
        """
        Update cursor on successful ingestion.

        Updates both last_success and last_attempted.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (e.g., "tushare")
            trade_date: Trade date (YYYY-MM-DD)

        Returns:
            The updated IngestionCursor.

        """
        now = datetime.now().isoformat()

        sql = """
            INSERT INTO ingestion_cursor (
                dataset, source, last_success, last_attempted, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (dataset) DO UPDATE SET
                last_success = excluded.last_success,
                last_attempted = excluded.last_attempted,
                source = excluded.source,
                updated_at = excluded.updated_at
        """

        self._client.execute(sql, [dataset, source, trade_date, trade_date, now])
        self._client.commit()

        logger.debug(
            "Ingestion cursor updated (success)",
            event="ingestion_cursor_updated_success",
            dataset=dataset,
            last_success=trade_date,
        )

        return IngestionCursor(
            dataset=dataset,
            source=source,
            last_success=trade_date,
            last_attempted=trade_date,
            updated_at=now,
        )

    def update_attempted(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionCursor:
        """
        Update cursor on any attempt (success or fail).

        Only updates last_attempted, NOT last_success.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (e.g., "tushare")
            trade_date: Trade date (YYYY-MM-DD)

        Returns:
            The updated IngestionCursor.

        """
        now = datetime.now().isoformat()

        # First check if cursor exists
        existing = self.get_cursor(dataset)

        if existing:
            # Update only last_attempted, preserve last_success
            sql = """
                UPDATE ingestion_cursor
                SET last_attempted = ?,
                    source = ?,
                    updated_at = ?
                WHERE dataset = ?
            """
            self._client.execute(sql, [trade_date, source, now, dataset])
        else:
            # Create new cursor with last_success=NULL
            sql = """
                INSERT INTO ingestion_cursor (
                    dataset, source, last_success, last_attempted, updated_at
                )
                VALUES (?, ?, NULL, ?, ?)
            """
            self._client.execute(sql, [dataset, source, trade_date, now])

        self._client.commit()

        logger.debug(
            "Ingestion cursor updated (attempted)",
            event="ingestion_cursor_updated_attempted",
            dataset=dataset,
            last_attempted=trade_date,
        )

        # Return updated cursor
        return self.get_cursor(dataset)  # type: ignore[return-value]

    def get_all_cursors(self, source: str = "tushare") -> list[IngestionCursor]:
        """
        Get all cursors for a source.

        Args:
            source: Data source identifier (default: "tushare")

        Returns:
            List of IngestionCursor.

        """
        sql = """
            SELECT dataset, source, last_success, last_attempted, updated_at
            FROM ingestion_cursor
            WHERE source = ?
            ORDER BY dataset
        """

        rows = self._client.fetchall(sql, [source])

        return [
            IngestionCursor(
                dataset=row["dataset"],
                source=row["source"],
                last_success=row["last_success"],
                last_attempted=row["last_attempted"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
