"""Ingestion log store for tracking per-trade-date ingestion events."""

from datetime import datetime

from ditto_foundation import logger

from ditto_datahub.sources.metadata import IngestionLog, IngestionStatus
from ditto_datahub.stores.sqlite_client import SQLiteClient


class IngestionLogStore:
    """
    Store for ingestion event logs.

    Tracks ingestion events per trade date with SUCCESS/FAIL status.
    Each trade date has exactly one record that can be updated on retry.

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
        Initialize store.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client
        self._create_tables()
        logger.debug(
            "IngestionLogStore initialized",
            event="ingestion_log_store_init",
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

        # Create index for status queries
        index_sql = """
            CREATE INDEX IF NOT EXISTS idx_ingestion_log_status_date
            ON ingestion_log(status, trade_date)
        """
        self._client.execute(index_sql)

        self._client.commit()
        logger.debug(
            "ingestion_log table created/verified",
            event="ingestion_log_table_created",
        )

    def save_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
        status: IngestionStatus,
        checksum: str | None = None,
        rows: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> IngestionLog:
        """
        Save or update ingestion log record (UPSERT).

        If record exists, increments attempts and updates last_attempt_at.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (e.g., "tushare")
            trade_date: Trade date (YYYY-MM-DD)
            status: Current status (SUCCESS or FAIL)
            checksum: Data checksum (only when SUCCESS)
            rows: Number of rows (only when SUCCESS)
            error_code: Error code (only when FAIL)
            error_message: Error message (only when FAIL)

        Returns:
            The saved IngestionLog.

        """
        now = datetime.now().isoformat()

        # Check if record exists
        existing = self.get_log(dataset, source, trade_date)

        if existing:
            # Update existing record
            new_attempts = existing.attempts + 1
            sql = """
                UPDATE ingestion_log
                SET status = ?,
                    checksum = ?,
                    rows = ?,
                    error_code = ?,
                    error_message = ?,
                    attempts = ?,
                    last_attempt_at = ?
                WHERE dataset = ? AND source = ? AND trade_date = ?
            """
            self._client.execute(
                sql,
                [
                    status.value,
                    checksum,
                    rows,
                    error_code,
                    error_message,
                    new_attempts,
                    now,
                    dataset,
                    source,
                    trade_date,
                ],
            )
            log = IngestionLog(
                dataset=dataset,
                source=source,
                trade_date=trade_date,
                status=status,
                checksum=checksum,
                rows=rows,
                error_code=error_code,
                error_message=error_message,
                attempts=new_attempts,
                first_attempt_at=existing.first_attempt_at,
                last_attempt_at=now,
            )
        else:
            # Insert new record
            sql = """
                INSERT INTO ingestion_log
                (dataset, source, trade_date, status, checksum, rows,
                 error_code, error_message, attempts, first_attempt_at, last_attempt_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self._client.execute(
                sql,
                [
                    dataset,
                    source,
                    trade_date,
                    status.value,
                    checksum,
                    rows,
                    error_code,
                    error_message,
                    1,
                    now,
                    now,
                ],
            )
            log = IngestionLog(
                dataset=dataset,
                source=source,
                trade_date=trade_date,
                status=status,
                checksum=checksum,
                rows=rows,
                error_code=error_code,
                error_message=error_message,
                attempts=1,
                first_attempt_at=now,
                last_attempt_at=now,
            )

        self._client.commit()

        logger.debug(
            "Ingestion log saved",
            event="ingestion_log_saved",
            dataset=dataset,
            source=source,
            trade_date=trade_date,
            status=status.value,
            attempts=log.attempts,
        )

        return log

    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """
        Get ingestion log for a specific date.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (e.g., "tushare")
            trade_date: Trade date (YYYY-MM-DD)

        Returns:
            IngestionLog if found, None otherwise.

        """
        sql = """
            SELECT dataset, source, trade_date, status,
                   checksum, rows, error_code, error_message,
                   attempts, first_attempt_at, last_attempt_at
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND trade_date = ?
        """

        row = self._client.fetchone(sql, [dataset, source, trade_date])

        if not row:
            return None

        return IngestionLog(
            dataset=row["dataset"],
            source=row["source"],
            trade_date=row["trade_date"],
            status=IngestionStatus(row["status"]),
            checksum=row["checksum"],
            rows=row["rows"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            attempts=row["attempts"],
            first_attempt_at=row["first_attempt_at"],
            last_attempt_at=row["last_attempt_at"],
        )

    def get_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """
        Get failed trade dates that need retry.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            limit: Maximum number of dates to return
            max_attempts: Only return dates with attempts < max_attempts

        Returns:
            List of trade dates (YYYY-MM-DD) that need retry.

        """
        sql = """
            SELECT trade_date
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND status = 'FAIL'
              AND attempts < ?
            ORDER BY trade_date ASC
            LIMIT ?
        """

        rows = self._client.fetchall(sql, [dataset, source, max_attempts, limit])
        return [row["trade_date"] for row in rows]

    def get_success_rate(
        self,
        dataset: str,
        source: str = "tushare",
        start_date: str | None = None,
    ) -> float:
        """
        Calculate success rate for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            start_date: Optional start date filter (YYYY-MM-DD)

        Returns:
            Success rate as a float (0.0 to 1.0).

        """
        if start_date:
            sql = """
                SELECT
                    COUNT(CASE WHEN status = 'SUCCESS'
                        THEN 1 END) * 1.0 / COUNT(*) as rate
                FROM ingestion_log
                WHERE dataset = ? AND source = ? AND trade_date >= ?
            """
            row = self._client.fetchone(sql, [dataset, source, start_date])
        else:
            sql = """
                SELECT
                    COUNT(CASE WHEN status = 'SUCCESS'
                        THEN 1 END) * 1.0 / COUNT(*) as rate
                FROM ingestion_log
                WHERE dataset = ? AND source = ?
            """
            row = self._client.fetchone(sql, [dataset, source])

        return float(row["rate"]) if row and row["rate"] is not None else 0.0

    def get_stats(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> dict[str, int]:
        """
        Get ingestion statistics for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")

        Returns:
            Dictionary with statistics: success_count, fail_count, total_count

        """
        sql = """
            SELECT
                COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as success_count,
                COUNT(CASE WHEN status = 'FAIL' THEN 1 END) as fail_count,
                COUNT(*) as total_count
            FROM ingestion_log
            WHERE dataset = ? AND source = ?
        """

        row = self._client.fetchone(sql, [dataset, source])

        return {
            "success_count": row["success_count"] if row else 0,
            "fail_count": row["fail_count"] if row else 0,
            "total_count": row["total_count"] if row else 0,
        }

    def get_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
        status: IngestionStatus | None = None,
    ) -> list[str]:
        """
        Get all ingested trade dates for a dataset.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            status: Optional status filter (SUCCESS or FAIL). If None,
                returns all dates.

        Returns:
            List of trade dates (YYYY-MM-DD) that have been ingested.

        """
        if status:
            sql = """
                SELECT trade_date
                FROM ingestion_log
                WHERE dataset = ? AND source = ? AND status = ?
                ORDER BY trade_date ASC
            """
            rows = self._client.fetchall(sql, [dataset, source, status.value])
        else:
            sql = """
                SELECT trade_date
                FROM ingestion_log
                WHERE dataset = ? AND source = ?
                ORDER BY trade_date ASC
            """
            rows = self._client.fetchall(sql, [dataset, source])

        return [row["trade_date"] for row in rows]

    def get_failed_logs(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[IngestionLog]:
        """
        Get failed ingestion logs that need retry.

        Args:
            dataset: Dataset name (e.g., "stock_daily")
            source: Data source identifier (default: "tushare")
            limit: Maximum number of logs to return
            max_attempts: Only return logs with attempts < max_attempts

        Returns:
            List of IngestionLog that need retry.

        """
        sql = """
            SELECT dataset, source, trade_date, status,
                   checksum, rows, error_code, error_message,
                   attempts, first_attempt_at, last_attempt_at
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND status = 'FAIL'
              AND attempts < ?
            ORDER BY trade_date ASC
            LIMIT ?
        """

        rows = self._client.fetchall(sql, [dataset, source, max_attempts, limit])

        return [
            IngestionLog(
                dataset=row["dataset"],
                source=row["source"],
                trade_date=row["trade_date"],
                status=IngestionStatus(row["status"]),
                checksum=row["checksum"],
                rows=row["rows"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                attempts=row["attempts"],
                first_attempt_at=row["first_attempt_at"],
                last_attempt_at=row["last_attempt_at"],
            )
            for row in rows
        ]
