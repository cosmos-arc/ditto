"""SQLite client for database operations."""

from typing import Any

from ditto_datahub.runtime.sqlite_pool import SQLitePool


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
        return self.conn.executemany(sql, params_list)

    def executescript(self, script: str) -> Any:
        """
        Execute SQL script (multiple statements).

        Args:
            script: SQL script.

        Returns:
            Cursor object.

        """
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
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback transaction."""
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
