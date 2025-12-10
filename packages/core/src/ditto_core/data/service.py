"""数据服务 - 统一数据访问入口."""

from .adapters import DuckDBAdapter, SQLiteAdapter


class DataService:
    """数据服务 - 管理所有数据库连接和操作."""

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
        self.duckdb_path = duckdb_path
        self.sqlite_path = sqlite_path
        self._duckdb: DuckDBAdapter | None = None
        self._sqlite: SQLiteAdapter | None = None

    def get_duckdb(self) -> DuckDBAdapter:
        """Get DuckDB adapter (lazy load and initialize)."""
        if self._duckdb is None:
            if self.duckdb_path is None:
                raise ValueError("DuckDB path not provided")
            self._duckdb = DuckDBAdapter(self.duckdb_path)
        return self._duckdb

    def get_sqlite(self) -> SQLiteAdapter:
        """Get SQLite adapter (lazy load and initialize)."""
        if self._sqlite is None:
            if self.sqlite_path is None:
                raise ValueError("SQLite path not provided")
            self._sqlite = SQLiteAdapter(self.sqlite_path)
        return self._sqlite

    @property
    def duckdb_adapter(self) -> DuckDBAdapter | None:
        """Get DuckDB adapter (not connected)."""
        if self._duckdb is None and self.duckdb_path is not None:
            self._duckdb = DuckDBAdapter(self.duckdb_path)
        return self._duckdb

    @property
    def sqlite_adapter(self) -> SQLiteAdapter | None:
        """Get SQLite adapter (not connected)."""
        if self._sqlite is None and self.sqlite_path is not None:
            self._sqlite = SQLiteAdapter(self.sqlite_path)
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
