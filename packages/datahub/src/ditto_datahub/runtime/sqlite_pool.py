"""SQLite connection pool for concurrent access."""

import sqlite3
import threading
from pathlib import Path
from typing import Any

from ditto_foundation import logger

# Get the directory containing this file
_CURRENT_DIR = Path(__file__).parent


class SQLitePool:
    """Simple SQLite connection wrapper."""

    def __init__(self, db_path: str) -> None:
        """Initialize with database path."""
        self._db_path = Path(db_path)
        self._local = threading.local()

        logger.debug(
            "SQLite pool initialized",
            event="pool_init_complete",
            db_path=str(self._db_path),
        )

    def get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn

            logger.debug(
                "SQLite connection created",
                event="connection_created",
                thread_id=threading.get_ident(),
            )
        # Type is correctly inferred but mypy sees Any from threading.local
        return self._local.conn  # type: ignore[no-any-return]

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection (deprecated, use get_connection)."""
        return self.get_connection()

    def execute(self, sql: str, params: list[Any] | None = None) -> sqlite3.Cursor:
        """Execute SQL query."""
        conn = self.get_connection()
        if params is None:
            params = []
        return conn.execute(sql, params)

    def rollback(self) -> None:
        """Rollback transaction."""
        conn = self.get_connection()
        conn.rollback()
        logger.debug(
            "Rolling back transaction",
            event="transaction_rollback",
        )

    def commit(self) -> None:
        """Commit transaction."""
        conn = self.get_connection()
        conn.commit()
        logger.debug(
            "Committing transaction",
            event="transaction_commit",
        )

    def init_schema(self) -> None:
        """Initialize database schema."""
        logger.info(
            "Initializing database schema",
            event="schema_init_start",
            db_path=str(self._db_path),
        )

        conn = self.get_connection()
        schema = self._get_schema()
        conn.executescript(schema)
        conn.commit()

        logger.info(
            "Database schema initialized successfully",
            event="schema_init_complete",
            status="success",
        )

    def _get_schema(self) -> str:
        """Get database schema DDL from external file."""
        schema_path = _CURRENT_DIR / "schema.sql"
        return schema_path.read_text(encoding="utf-8")

    def close(self) -> None:
        """Close connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

            logger.debug(
                "SQLite connection closed",
                event="connection_closed",
                thread_id=threading.get_ident(),
            )
