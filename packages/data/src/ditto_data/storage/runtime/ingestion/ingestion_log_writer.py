"""
Ingestion log writer for tracking per-trade-date ingestion events.

Provides write access to ingestion log data.
"""

from datetime import datetime
from typing import Any

from ditto_infra.foundation import logger

from ditto_data.models.ingestion import IngestionLog
from ditto_data.storage.sqlite_client import SQLiteClient


class IngestionLogWriter:
    """
    Writer for ingestion event logs.

    Provides write access to ingestion logs that track ingestion events
    per trade date with SUCCESS/FAIL status.

    Table: ingestion_log
    - dataset, source, trade_date: PRIMARY KEY
    - status: 'SUCCESS' or 'FAIL'
    - checksum, rows: populated when SUCCESS
    - error_code, error_message: populated when FAIL
    - attempts: incremented on retry
    - first_attempt_at, last_attempt_at: timestamps
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
            "IngestionLogWriter initialized",
            event="ingestion_log_writer_init",
        )

    def _create_tables(self) -> None:
        """Create ingestion_log table if not exists."""
        sql = """
            CREATE TABLE IF NOT EXISTS ingestion_log (
                dataset TEXT NOT NULL,
                source TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                status TEXT NOT NULL,
                checksum TEXT,
                rows INTEGER,
                error_code TEXT,
                error_message TEXT,
                attempts INTEGER DEFAULT 1,
                first_attempt_at TEXT,
                last_attempt_at TEXT,
                PRIMARY KEY (dataset, source, trade_date)
            )
        """
        self._client.execute(sql)

        # Drop old index (doesn't match query patterns)
        self._client.execute("DROP INDEX IF EXISTS idx_ingestion_log_status_date")

        # Create new index that matches actual query patterns
        # All queries include dataset and source prefix
        index_sql = """
            CREATE INDEX IF NOT EXISTS idx_ingestion_log_dataset_source_status_date
            ON ingestion_log(dataset, source, status, trade_date)
        """
        self._client.execute(index_sql)

        self._client.commit()
        logger.debug(
            "ingestion_log table created/verified",
            event="ingestion_log_table_created",
        )

    def _row_to_log(self, row: dict[str, Any]) -> IngestionLog:
        """Convert database row to IngestionLog object."""
        return IngestionLog(
            dataset=row["dataset"],
            source=row["source"],
            trade_date=row["trade_date"],
            status=row["status"],
            checksum=row["checksum"],
            rows=row["rows"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            attempts=row["attempts"],
            first_attempt_at=row["first_attempt_at"],
            last_attempt_at=row["last_attempt_at"],
        )

    def save_log(self, log: IngestionLog) -> IngestionLog:
        """
        Save or update ingestion log record (atomic UPSERT).

        Uses SQLite's ON CONFLICT clause to atomically handle concurrent writes.
        If record exists, increments attempts atomically at database level.

        Args:
            log: IngestionLog object to save.

        Returns:
            The saved IngestionLog with updated timestamps and attempts.

        """
        now = datetime.now().isoformat()

        sql = """
            INSERT INTO ingestion_log
            (dataset, source, trade_date, status, checksum, rows,
             error_code, error_message, attempts, first_attempt_at, last_attempt_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(dataset, source, trade_date)
            DO UPDATE SET
                status = excluded.status,
                checksum = excluded.checksum,
                rows = excluded.rows,
                error_code = excluded.error_code,
                error_message = excluded.error_message,
                attempts = attempts + 1,
                last_attempt_at = excluded.last_attempt_at
            RETURNING dataset, source, trade_date, status,
                      checksum, rows, error_code, error_message,
                      attempts, first_attempt_at, last_attempt_at
        """

        row = self._client.fetchone(
            sql,
            [
                log.dataset,
                log.source,
                log.trade_date,
                log.status.value,
                log.checksum,
                log.rows,
                log.error_code,
                log.error_message,
                now,
                now,
            ],
        )

        # UPSERT with RETURNING always returns a row
        if row is None:
            raise RuntimeError(
                "UPSERT RETURNING should always return a row but got None"
            )

        self._client.commit()

        result = self._row_to_log(row)

        logger.debug(
            "Ingestion log saved",
            event="ingestion_log_saved",
            dataset=log.dataset,
            source=log.source,
            trade_date=log.trade_date,
            status=log.status.value,
            attempts=result.attempts,
        )

        return result
