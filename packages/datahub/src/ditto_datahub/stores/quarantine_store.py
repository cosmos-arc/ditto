"""Quarantine store for failed DQ data."""

import sqlite3
from pathlib import Path
from typing import Any

import polars as pl


class QuarantineStore:
    """SQLite-based quarantine store for DQ failed data."""

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize quarantine store.

        Args:
            db_path: Path to SQLite database

        """
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize quarantine table schema."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS quarantine_failed_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                failed_data TEXT,  -- JSON stored failed records
                affected_rows INTEGER DEFAULT 0,
                trade_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

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
        # Use arrow format for reliable serialization
        import json

        # Convert to list of dicts (records format)
        data_dicts = failed_data.to_dicts()
        data_json = json.dumps(data_dicts)

        cursor = self._conn.execute(
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
        self._conn.commit()
        row_id = cursor.lastrowid
        if row_id is None:
            # Fallback: get the last inserted row ID
            cursor = self._conn.execute("SELECT last_insert_rowid()")
            row_id = cursor.fetchone()[0]
        return row_id

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

        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        return pl.DataFrame(rows, schema=columns, orient="row")

    def get_failed_data_df(self, row_id: int) -> pl.DataFrame | None:
        """
        Get failed data DataFrame by row ID.

        Args:
            row_id: Quarantine record ID

        Returns:
            Failed data as DataFrame, or None if not found

        """
        import json

        cursor = self._conn.execute(
            "SELECT failed_data FROM quarantine_failed_data WHERE id = ?",
            (row_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        # Parse JSON back to DataFrame
        try:
            data_dicts = json.loads(row[0])
            return pl.DataFrame(data_dicts)
        except Exception:
            return None

    def clear_old_records(self, days: int = 30) -> int:
        """
        Clear old quarantine records.

        Args:
            days: Delete records older than this many days

        Returns:
            Number of records deleted

        """
        cursor = self._conn.execute(
            """
            DELETE FROM quarantine_failed_data
            WHERE julianday('now') - julianday(created_at) > ?
            """,
            (days,),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_stats(self) -> list[dict[str, Any]]:
        """
        Get quarantine statistics.

        Returns:
            Dictionary with stats

        """
        cursor = self._conn.execute("""
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

        rows = cursor.fetchall()
        return [
            {
                "dataset": row[0],
                "rule_id": row[1],
                "severity": row[2],
                "count": row[3],
                "total_affected": row[4],
            }
            for row in rows
        ]

    def close(self) -> None:
        """Close database connection."""
        self._conn.close()

    def __enter__(self) -> "QuarantineStore":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
