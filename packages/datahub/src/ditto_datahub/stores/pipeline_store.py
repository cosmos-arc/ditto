"""
Pipeline run tracking storage.

Manages pipeline execution records and data quality issues.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ditto_datahub.stores.sqlite_client import SQLiteClient


def _row_to_dict(row: Any) -> dict[str, Any]:
    """
    Convert SQLite row to dict with proper type conversions.

    SQLite stores BOOLEAN as INTEGER (0/1), so we convert them back.

    """
    if row is None:
        return {}

    result = dict(row)
    # Convert integer booleans back to bool
    for key, value in result.items():
        if key in (
            "dq_passed",
            "is_open",
            "is_st",
            "is_active",
            "is_week_end",
            "is_month_end",
            "is_quarter_end",
            "is_primary",
        ) and isinstance(value, int):
            result[key] = bool(value)
    return result


class PipelineStore:
    """
    Pipeline run tracking storage.

    Manages pipeline execution records, DQ issues, and freeze points.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize PipelineStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client

    # ============ Pipeline run operations ============

    def insert_run(  # noqa: PLR0913
        self,
        run_id: str,
        task_name: str,
        dataset_id: str,
        year: int | None = None,
        rows_read: int | None = None,
        rows_written: int | None = None,
        status: str = "running",
        error_message: str | None = None,
        dq_passed: bool | None = None,
        dq_fail_count: int = 0,
        dq_warn_count: int = 0,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """
        Insert pipeline run record.

        Args:
            run_id: Unique run identifier.
            task_name: Task name.
            dataset_id: Dataset identifier.
            year: Data year (for partitioned datasets).
            rows_read: Number of rows read.
            rows_written: Number of rows written.
            status: Run status (running/completed/failed).
            error_message: Error message if failed.
            dq_passed: Data quality check result.
            dq_fail_count: Number of failed DQ checks.
            dq_warn_count: Number of warning DQ checks.
            started_at: Start timestamp.
            finished_at: Finish timestamp.

        """
        duration_sec: float | None = None
        if started_at and finished_at:
            duration_sec = (finished_at - started_at).total_seconds()

        try:
            self._client.execute(
                """INSERT INTO pipeline_run
                (run_id, task_name, dataset_id, year, rows_read, rows_written,
                status, error_message, dq_passed, dq_fail_count, dq_warn_count,
                started_at, finished_at, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    run_id,
                    task_name,
                    dataset_id,
                    year,
                    rows_read,
                    rows_written,
                    status,
                    error_message,
                    dq_passed if dq_passed is not None else (status == "completed"),
                    dq_fail_count,
                    dq_warn_count,
                    started_at,
                    finished_at,
                    duration_sec,
                ],
            )
            self._client.commit()

        except Exception:
            self._client.rollback()
            raise

    def update_run(  # noqa: PLR0913
        self,
        run_id: str,
        status: str | None = None,
        error_message: str | None = None,
        rows_read: int | None = None,
        rows_written: int | None = None,
        dq_passed: bool | None = None,
        dq_fail_count: int | None = None,
        dq_warn_count: int | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """
        Update pipeline run record.

        Args:
            run_id: Run identifier.
            status: New status.
            error_message: Error message.
            rows_read: Number of rows read.
            rows_written: Number of rows written.
            dq_passed: Data quality check result.
            dq_fail_count: Number of failed DQ checks.
            dq_warn_count: Number of warning DQ checks.
            finished_at: Finish timestamp.

        """
        updates: list[str] = []
        params: list[Any] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if rows_read is not None:
            updates.append("rows_read = ?")
            params.append(rows_read)

        if rows_written is not None:
            updates.append("rows_written = ?")
            params.append(rows_written)

        if dq_passed is not None:
            updates.append("dq_passed = ?")
            params.append(dq_passed)

        if dq_fail_count is not None:
            updates.append("dq_fail_count = ?")
            params.append(dq_fail_count)

        if dq_warn_count is not None:
            updates.append("dq_warn_count = ?")
            params.append(dq_warn_count)

        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
            # Update duration if we have start time
            start_row = self._client.fetchone(
                "SELECT started_at FROM pipeline_run WHERE run_id = ?",
                [run_id],
            )
            if start_row and start_row["started_at"]:
                started_at = datetime.fromisoformat(start_row["started_at"])
                duration_sec = (finished_at - started_at).total_seconds()
                updates.append("duration_sec = ?")
                params.append(duration_sec)

        if updates:
            params.append(run_id)
            self._client.execute(
                f"UPDATE pipeline_run SET {', '.join(updates)} WHERE run_id = ?",
                params,
            )
            self._client.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """
        Get pipeline run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            Run record as dict, or None if not found.

        """
        row = self._client.fetchone(
            "SELECT * FROM pipeline_run WHERE run_id = ?",
            [run_id],
        )
        return _row_to_dict(row) if row else None

    def list_runs(
        self,
        dataset_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List pipeline runs.

        Args:
            dataset_id: Filter by dataset ID.
            status: Filter by status.
            limit: Maximum number of records to return.

        Returns:
            List of run records.

        """
        sql = "SELECT * FROM pipeline_run WHERE 1=1"
        params: list[Any] = []

        if dataset_id:
            sql += " AND dataset_id = ?"
            params.append(dataset_id)

        if status:
            sql += " AND status = ?"
            params.append(status)

        # Order by rowid (insertion order) to get latest first
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)

        rows = self._client.fetchall(sql, params)
        return [_row_to_dict(row) for row in rows]

    def get_latest_run(
        self, dataset_id: str, year: int | None = None
    ) -> dict[str, Any] | None:
        """
        Get latest run for dataset.

        Args:
            dataset_id: Dataset identifier.
            year: Filter by year (optional).

        Returns:
            Latest run record, or None if not found.

        """
        sql = "SELECT * FROM pipeline_run WHERE dataset_id = ?"
        params: list[Any] = [dataset_id]

        if year is not None:
            sql += " AND year = ?"
            params.append(year)

        # Order by rowid (insertion order) to get the latest
        sql += " ORDER BY rowid DESC LIMIT 1"

        row = self._client.fetchone(sql, params)
        return _row_to_dict(row) if row else None

    def count_runs(
        self, dataset_id: str | None = None, status: str | None = None
    ) -> int:
        """
        Count pipeline runs.

        Args:
            dataset_id: Filter by dataset ID.
            status: Filter by status.

        Returns:
            Number of runs.

        """
        where: str | None = None
        params: list[Any] = []

        conditions: list[str] = []
        if dataset_id:
            conditions.append("dataset_id = ?")
            params.append(dataset_id)

        if status:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            where = " AND ".join(conditions)

        result: int = self._client.count("pipeline_run", where, params) or 0
        return result

    def delete_run(self, run_id: str) -> bool:
        """
        Delete pipeline run.

        Args:
            run_id: Run identifier.

        Returns:
            True if deleted, False if not found.

        """
        existing = self._client.exists(
            "SELECT 1 FROM pipeline_run WHERE run_id = ?",
            [run_id],
        )

        if not existing:
            return False

        self._client.execute(
            "DELETE FROM pipeline_run WHERE run_id = ?",
            [run_id],
        )
        self._client.commit()
        return True

    # ============ DQ issue operations ============

    def insert_dq_issue(  # noqa: PLR0913
        self,
        run_id: str,
        dataset_id: str,
        rule_name: str,
        severity: str,
        message: str | None = None,
        year: int | None = None,
        sid: int | None = None,
        trade_date: str | None = None,
    ) -> None:
        """
        Insert DQ issue record.

        Args:
            run_id: Run identifier.
            dataset_id: Dataset identifier.
            rule_name: DQ rule name.
            severity: Issue severity (error/warning).
            message: Issue message.
            year: Data year.
            sid: Security ID.
            trade_date: Trade date.

        """
        self._client.execute(
            """INSERT INTO dq_issue
            (run_id, dataset_id, year, sid, trade_date, rule_name, severity, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [run_id, dataset_id, year, sid, trade_date, rule_name, severity, message],
        )
        self._client.commit()

    def list_dq_issues(
        self,
        run_id: str | None = None,
        dataset_id: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List DQ issues.

        Args:
            run_id: Filter by run ID.
            dataset_id: Filter by dataset ID.
            severity: Filter by severity.
            limit: Maximum number of records to return.

        Returns:
            List of DQ issue records.

        """
        sql = "SELECT * FROM dq_issue WHERE 1=1"
        params: list[Any] = []

        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)

        if dataset_id:
            sql += " AND dataset_id = ?"
            params.append(dataset_id)

        if severity:
            sql += " AND severity = ?"
            params.append(severity)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._client.fetchall(sql, params)
        return [_row_to_dict(row) for row in rows]

    def count_dq_issues(
        self,
        run_id: str | None = None,
        dataset_id: str | None = None,
        severity: str | None = None,
    ) -> int:
        """
        Count DQ issues.

        Args:
            run_id: Filter by run ID.
            dataset_id: Filter by dataset ID.
            severity: Filter by severity.

        Returns:
            Number of DQ issues.

        """
        where: str | None = None
        params: list[Any] = []

        conditions: list[str] = []
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)

        if dataset_id:
            conditions.append("dataset_id = ?")
            params.append(dataset_id)

        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        if conditions:
            where = " AND ".join(conditions)

        result: int = self._client.count("dq_issue", where, params) or 0
        return result
