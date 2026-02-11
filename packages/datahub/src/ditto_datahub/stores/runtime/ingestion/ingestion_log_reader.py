"""
Ingestion log reader for tracking per-trade-date ingestion events.

Provides read-only access to ingestion log data.
"""

from typing import Any

from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.stores.sqlite_client import SQLiteClient


class IngestionLogReader:
    """
    Reader for ingestion event logs.

    Provides read-only access to ingestion logs that track ingestion events
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
        Initialize reader.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    def _row_to_log(self, row: dict[str, Any]) -> IngestionLog:
        """Convert database row to IngestionLog object."""
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

        return self._row_to_log(row)

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

        return [self._row_to_log(row) for row in rows]

    def get_last_success_date(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """获取最后成功的交易日期。"""
        sql = """
            SELECT MAX(trade_date) as last_success
            FROM ingestion_log
            WHERE dataset = ? AND source = ? AND status = 'SUCCESS'
        """
        row = self._client.fetchone(sql, [dataset, source])
        return row["last_success"] if row else None
