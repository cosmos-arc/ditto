"""Generic SQLite client for database operations."""

import sqlite3
from typing import Any, cast

from ditto_platform.foundation import SQLitePool, logger, span

# Maximum SQL length to log (truncates longer queries)
_MAX_SQL_LOG_LENGTH = 100


class SQLiteClient:
    """
    SQLite database client.

    Provides basic operations for SQLite database access.
    Store classes use this client through composition.
    """

    def __init__(self, pool: SQLitePool) -> None:
        """
        Initialize client.

        Args:
            pool: SQLite connection pool.

        """
        self._pool = pool
        logger.debug(
            "SQLite client initialized",
            event="client_init_complete",
        )

    @property
    def conn(self) -> sqlite3.Connection:
        """Get current thread database connection."""
        return self._pool.get_connection()

    def execute(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> sqlite3.Cursor:
        """
        Execute SQL statement.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            Cursor object.

        """
        with span("data.sql_execute"):
            logger.debug(
                "Executing SQL statement",
                event="sql_execute_start",
                sql=sql[:_MAX_SQL_LOG_LENGTH]
                if len(sql) > _MAX_SQL_LOG_LENGTH
                else sql,
                has_params=params is not None,
            )
            if params:
                result = self.conn.execute(sql, params)
            else:
                result = self.conn.execute(sql)
            return result

    def executemany(
        self, sql: str, params_list: list[list[Any] | tuple[Any, ...]]
    ) -> sqlite3.Cursor:
        """
        Execute SQL batch.

        Args:
            sql: SQL statement with placeholders.
            params_list: List of parameter lists.

        Returns:
            Cursor object.

        """
        logger.info(
            "Executing SQL batch",
            event="sql_batch_start",
            sql=sql[:_MAX_SQL_LOG_LENGTH] if len(sql) > _MAX_SQL_LOG_LENGTH else sql,
            batch_size=len(params_list),
        )
        return self.conn.executemany(sql, params_list)

    def executescript(self, script: str) -> sqlite3.Cursor:
        """
        Execute SQL script (multiple statements).

        Args:
            script: SQL script.

        Returns:
            Cursor object.

        """
        logger.info(
            "Executing SQL script",
            event="sql_script_start",
            script_length=len(script),
        )
        return self.conn.executescript(script)

    def fetchone(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        """
        Query single record.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            Record as dict, or None if not found.

        """
        logger.debug(
            "Fetching single record",
            event="sql_query_start",
            sql=sql[:_MAX_SQL_LOG_LENGTH] if len(sql) > _MAX_SQL_LOG_LENGTH else sql,
        )
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return cast(dict[str, Any], dict(row)) if row else None

    def fetchall(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """
        Query all records.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            List of record dicts.

        """
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        result: list[dict[str, Any]] = cast(
            list[dict[str, Any]], [dict(row) for row in rows]
        )
        logger.debug(
            "Query completed",
            event="sql_query_complete",
            row_count=len(result),
        )
        return result

    def fetchval(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> str | int | float | None:
        """
        Query single value.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            First row first column value (str, int, float, or None).

        """
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row:
            # pyright can't infer the type from sqlite3.Row, use cast
            return cast(str | int | float, row[0])
        return None

    def commit(self) -> None:
        """Commit transaction."""
        logger.debug(
            "Committing transaction",
            event="transaction_commit",
        )
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback transaction."""
        logger.warning(
            "Rolling back transaction",
            event="transaction_rollback",
        )
        self.conn.rollback()

    def insert_returning_id(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> int:
        """
        Insert and return auto-increment ID.

        Args:
            sql: INSERT statement.
            params: Parameter list.

        Returns:
            lastrowid.

        """
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
        """
        Check if record exists.

        Args:
            sql: SELECT statement.
            params: Parameter list.

        Returns:
            True if record exists.

        """
        return self.fetchone(sql, params) is not None

    def count(
        self,
        table: str,
        where: str | None = None,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> int:
        """
        Count records in a table.

        Args:
            table: Table name.
            where: WHERE clause (without WHERE keyword).
            params: Parameter list.

        Returns:
            Record count.

        """
        sql = f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - table name should be validated by caller
        if where:
            sql += f" WHERE {where}"

        result = self.fetchval(sql, params)
        # COUNT(*) always returns int, but pyright can't infer that
        return int(result) if result is not None else 0

    def close(self) -> None:
        """
        Close the database connection.

        This closes the thread-local connection held by this client.
        """
        self._pool.close()
