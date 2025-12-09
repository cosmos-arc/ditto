"""数据服务 - 统一数据访问入口"""

from .adapters import DuckDBAdapter, SQLiteAdapter


class DataService:
    """数据服务 - 管理所有数据库连接和操作"""

    def __init__(
        self,
        duckdb_path: str,
        sqlite_path: str,
    ) -> None:
        """
        初始化数据服务

        Args:
            duckdb_path: DuckDB 数据库路径
            sqlite_path: SQLite 数据库路径

        """
        self.duckdb_path = duckdb_path
        self.sqlite_path = sqlite_path
        self._duckdb: DuckDBAdapter | None = None
        self._sqlite: SQLiteAdapter | None = None

    def get_duckdb(self) -> DuckDBAdapter:
        """获取 DuckDB 适配器（懒加载并初始化）"""
        if self._duckdb is None:
            self._duckdb = DuckDBAdapter(self.duckdb_path)
        return self._duckdb

    def get_sqlite(self) -> SQLiteAdapter:
        """获取 SQLite 适配器（懒加载并初始化）"""
        if self._sqlite is None:
            self._sqlite = SQLiteAdapter(self.sqlite_path)
        return self._sqlite

    @property
    def duckdb_adapter(self) -> DuckDBAdapter:
        """获取 DuckDB 适配器（未连接）"""
        if self._duckdb is None:
            self._duckdb = DuckDBAdapter(self.duckdb_path)
        return self._duckdb

    @property
    def sqlite_adapter(self) -> SQLiteAdapter:
        """获取 SQLite 适配器（未连接）"""
        if self._sqlite is None:
            self._sqlite = SQLiteAdapter(self.sqlite_path)
        return self._sqlite

    def initialize(self) -> None:
        """初始化所有数据库连接"""
        # 通过方法访问触发初始化
        _ = self.get_duckdb()
        _ = self.get_sqlite()

    def close(self) -> None:
        """关闭所有数据库连接"""
        if self._duckdb:
            self._duckdb.close()
        if self._sqlite:
            self._sqlite.close()

    def __enter__(self):
        """上下文管理器入口"""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
