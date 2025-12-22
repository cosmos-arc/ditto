"""SQLite connection pool for concurrent access."""

import sqlite3
import threading
from pathlib import Path
from typing import Any


class SQLitePool:
    """Simple SQLite connection wrapper."""

    def __init__(self, db_path: str) -> None:
        """Initialize with database path."""
        self._db_path = Path(db_path)
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn  # type: ignore[no-any-return]

    def execute(self, sql: str, params: list[Any] | None = None) -> sqlite3.Cursor:
        """Execute SQL query."""
        conn = self._get_connection()
        if params is None:
            params = []
        return conn.execute(sql, params)

    def rollback(self) -> None:
        """Rollback transaction."""
        conn = self._get_connection()
        conn.rollback()

    def commit(self) -> None:
        """Commit transaction."""
        conn = self._get_connection()
        conn.commit()

    def close(self) -> None:
        """Close connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")
