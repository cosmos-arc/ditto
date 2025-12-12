"""数据服务 - 统一数据访问入口."""

import sqlite3
import warnings

import duckdb


class DataService:
    """
    数据服务 - 管理所有数据库连接和操作.

    .. deprecated:: 0.5.0
        DataService is deprecated and will be removed in a future version.
        Use DataReader and DataWriter classes instead for better separation of concerns.

    Migration guide:
        - For reading data: Use DataReader(adapter)
        - For writing data: Use DataWriter(adapter)
        - For database connections: Use DuckDBAdapter or SQLiteAdapter directly

    Example:
        Old::

            with DataService(duckdb_path="path.db", sqlite_path="path2.db") as service:
                duckdb = service.get_duckdb()
                data = duckdb.fetch_df("SELECT * FROM table")

        New::

            adapter = DuckDBAdapter("path.db")
            reader = DataReader(adapter)
            data = reader.get_daily_data("symbol", "2024-01-01", "2024-12-31")

    """

    def __init__(
        self,
        duckdb_path: str | None = None,
        sqlite_path: str | None = None,
    ) -> None:
        """
        初始化数据服务.

        Args:
            duckdb_path: DuckDB 数据库路径 (可选)
            sqlite_path: SQLite 数据库路径 (可选)

        """
        warnings.warn(
            "DataService is deprecated and will be removed in a future version. "
            "Use DataReader and DataWriter classes instead. "
            "See the class docstring for migration examples.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.duckdb_path = duckdb_path
        self.sqlite_path = sqlite_path
        self._duckdb: duckdb.DuckDBPyConnection | None = None
        self._sqlite: sqlite3.Connection | None = None

    def get_duckdb(self) -> duckdb.DuckDBPyConnection:
        """
        Get DuckDB connection (lazy load and initialize).

        .. deprecated:: 0.5.0
            Use duckdb.connect() directly instead.
        """
        if self._duckdb is None:
            if self.duckdb_path is None:
                raise ValueError("DuckDB path not provided")
            self._duckdb = duckdb.connect(self.duckdb_path)
        return self._duckdb

    def get_sqlite(self) -> sqlite3.Connection:
        """
        Get SQLite connection (lazy load and initialize).

        .. deprecated:: 0.5.0
            Use sqlite3.connect() directly instead.
        """
        if self._sqlite is None:
            if self.sqlite_path is None:
                raise ValueError("SQLite path not provided")
            self._sqlite = sqlite3.connect(self.sqlite_path)
        return self._sqlite

    @property
    def duckdb_connection(self) -> duckdb.DuckDBPyConnection | None:
        """Get DuckDB connection (not connected)."""
        if self._duckdb is None and self.duckdb_path is not None:
            self._duckdb = duckdb.connect(self.duckdb_path)
        return self._duckdb

    @property
    def sqlite_connection(self) -> sqlite3.Connection | None:
        """Get SQLite connection (not connected)."""
        if self._sqlite is None and self.sqlite_path is not None:
            self._sqlite = sqlite3.connect(self.sqlite_path)
        return self._sqlite

    def initialize(self) -> None:
        """Initialize all database connections."""
        # 通过方法访问触发初始化
        if self.duckdb_path is not None:
            _ = self.get_duckdb()
        if self.sqlite_path is not None:
            _ = self.get_sqlite()

    def close(self) -> None:
        """Close all database connections."""
        if self._duckdb:
            self._duckdb.close()
        if self._sqlite:
            self._sqlite.close()

    def __enter__(self) -> "DataService":
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: type | None,
    ) -> None:
        """Context manager exit."""
        self.close()
        del exc_type, exc_val, exc_tb  # Mark as intentionally unused
