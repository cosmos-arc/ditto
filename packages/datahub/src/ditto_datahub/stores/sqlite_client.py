"""SQLite client for database operations."""

from typing import Any

from loguru import logger

from ditto_datahub.runtime.sqlite_pool import SQLitePool

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
            "sqlite_client_initialized",
            event="client_init",
        )

    @property
    def conn(self) -> Any:
        """Get current thread database connection."""
        return self._pool.get_connection()

    def execute(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> Any:
        """
        Execute SQL statement.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            Cursor object.

        """
        logger.debug(
            "sql_execute",
            event="sql_execute",
            sql=sql[:_MAX_SQL_LOG_LENGTH] if len(sql) > _MAX_SQL_LOG_LENGTH else sql,
            has_params=params is not None,
        )
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def executemany(
        self, sql: str, params_list: list[list[Any] | tuple[Any, ...]]
    ) -> Any:
        """
        Execute SQL batch.

        Args:
            sql: SQL statement with placeholders.
            params_list: List of parameter lists.

        Returns:
            Cursor object.

        """
        logger.info(
            "sql_executemany",
            event="sql_batch",
            sql=sql[:_MAX_SQL_LOG_LENGTH] if len(sql) > _MAX_SQL_LOG_LENGTH else sql,
            batch_size=len(params_list),
        )
        return self.conn.executemany(sql, params_list)

    def executescript(self, script: str) -> Any:
        """
        Execute SQL script (multiple statements).

        Args:
            script: SQL script.

        Returns:
            Cursor object.

        """
        logger.info(
            "sql_executescript",
            event="sql_script",
            script_length=len(script),
        )
        return self.conn.executescript(script)

    def fetchone(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> Any:
        """
        Query single record.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            sqlite3.Row or None.

        """
        logger.debug(
            "sql_fetchone",
            event="sql_query",
            sql=sql[:_MAX_SQL_LOG_LENGTH] if len(sql) > _MAX_SQL_LOG_LENGTH else sql,
        )
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[Any]:
        """
        Query all records.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            sqlite3.Row list.

        """
        cursor = self.execute(sql, params)
        result: list[Any] = cursor.fetchall()
        logger.debug(
            "sql_fetchall",
            event="sql_query",
            row_count=len(result),
        )
        return result

    def fetchval(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> Any:
        """
        Query single value.

        Args:
            sql: SQL statement.
            params: Parameter list.

        Returns:
            First row first column value, or None.

        """
        row = self.fetchone(sql, params)
        if row:
            return row[0]
        return None

    def commit(self) -> None:
        """Commit transaction."""
        logger.debug(
            "transaction_commit",
            event="transaction",
            action="commit",
        )
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback transaction."""
        logger.warning(
            "transaction_rollback",
            event="transaction",
            action="rollback",
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
        row_id: int = cursor.lastrowid
        logger.info(
            "insert_returning_id",
            event="insert",
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
        Count records.

        Args:
            table: Table name.
            where: WHERE clause (without WHERE keyword).
            params: Parameter list.

        Returns:
            Record count.

        """
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"

        return self.fetchval(sql, params) or 0
