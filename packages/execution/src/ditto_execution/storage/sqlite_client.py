"""SQLite client for execution storage operations."""

import sqlite3
from typing import Any, cast

from ditto_platform.foundation import SQLitePool, logger, span

_MAX_SQL_LOG_LENGTH = 100


def _truncated(sql: str) -> str:
    return sql[:_MAX_SQL_LOG_LENGTH] if len(sql) > _MAX_SQL_LOG_LENGTH else sql


class SQLiteClient:
    """SQLite database client for execution storage."""

    def __init__(self, pool: SQLitePool) -> None:
        """Initialize client."""
        self._pool = pool
        logger.debug("SQLite client initialized", event="client_init_complete")

    @property
    def conn(self) -> sqlite3.Connection:
        """Get current thread database connection."""
        return self._pool.get_connection()

    def execute(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> sqlite3.Cursor:
        """Execute SQL statement."""
        with span("execution.sql_execute"):
            logger.debug(
                "Executing SQL statement",
                event="sql_execute_start",
                sql=_truncated(sql),
                has_params=params is not None,
            )
            if params:
                return self.conn.execute(sql, params)
            return self.conn.execute(sql)

    def executemany(
        self, sql: str, params_list: list[list[Any] | tuple[Any, ...]]
    ) -> sqlite3.Cursor:
        """Execute SQL batch."""
        logger.info(
            "Executing SQL batch",
            event="sql_batch_start",
            sql=_truncated(sql),
            batch_size=len(params_list),
        )
        return self.conn.executemany(sql, params_list)

    def executescript(self, script: str) -> sqlite3.Cursor:
        """Execute SQL script (multiple statements)."""
        logger.info(
            "Executing SQL script",
            event="sql_script_start",
            script_length=len(script),
        )
        return self.conn.executescript(script)

    def fetchone(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        """Query single record."""
        logger.debug(
            "Fetching single record",
            event="sql_query_start",
            sql=_truncated(sql),
        )
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return cast(dict[str, Any], dict(row)) if row else None

    def fetchall(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Query all records."""
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        result: list[dict[str, Any]] = cast(
            list[dict[str, Any]], [dict(row) for row in rows]
        )
        logger.debug(
            "Query completed", event="sql_query_complete", row_count=len(result)
        )
        return result

    def fetchval(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> str | int | float | None:
        """Query single value."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row:
            return cast(str | int | float, row[0])
        return None

    def commit(self) -> None:
        """Commit transaction."""
        logger.debug("Committing transaction", event="transaction_commit")
        self.conn.commit()

    def rollback(self) -> None:
        """Roll back transaction."""
        logger.warning("Rolling back transaction", event="transaction_rollback")
        self.conn.rollback()

    def insert_returning_id(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> int:
        """Insert and return auto-increment ID."""
        cursor = self.execute(sql, params)
        self.commit()
        row_id: int = cursor.lastrowid or 0
        logger.info(
            "Record inserted successfully",
            event="insert_complete",
            row_id=row_id,
        )
        return row_id

    def exists(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> bool:
        """Check if record exists."""
        return self.fetchone(sql, params) is not None

    def close(self) -> None:
        """Close the database connection."""
        self._pool.close()
