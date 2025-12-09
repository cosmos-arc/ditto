"""测试 DataService 相关功能"""

import pytest
from pathlib import Path
import tempfile
import shutil


class TestDuckDBAdapter:
    """DuckDB 适配器测试"""

    def setup_method(self):
        """每个测试前执行"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.duckdb"

    def teardown_method(self):
        """每个测试后执行"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_adapter_with_path(self):
        """测试使用路径创建适配器"""
        from ditto.data.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter(database_path=str(self.db_path))

        assert adapter.database_path == str(self.db_path)
        assert adapter.connection is None

    def test_connection_creation(self):
        """测试连接创建"""
        from ditto.data.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter(database_path=str(self.db_path))
        adapter.connect()

        assert adapter.connection is not None
        assert adapter.connection.execute("SELECT 1").fetchone()[0] == 1

    def test_initialize_schema(self):
        """测试数据库 schema 初始化"""
        from ditto.data.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter(database_path=str(self.db_path))
        adapter.connect()
        adapter.initialize_schema()

        # 验证表是否创建成功
        tables = adapter.connection.execute(
            "SHOW TABLES"
        ).fetchall()

        table_names = [table[0] for table in tables]
        expected_tables = [
            "etf_info", "daily_price", "adjustment_factors",
            "trading_calendar", "factor_data"
        ]

        for table in expected_tables:
            assert table in table_names


class TestSQLiteAdapter:
    """SQLite 适配器测试"""

    def setup_method(self):
        """每个测试前执行"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.sqlite"

    def teardown_method(self):
        """每个测试后执行"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_adapter_with_path(self):
        """测试使用路径创建适配器"""
        from ditto.data.adapters.sqlite_adapter import SQLiteAdapter

        adapter = SQLiteAdapter(database_path=str(self.db_path))

        assert adapter.database_path == str(self.db_path)
        assert adapter.connection is None

    def test_connection_creation(self):
        """测试连接创建"""
        from ditto.data.adapters.sqlite_adapter import SQLiteAdapter

        adapter = SQLiteAdapter(database_path=str(self.db_path))
        adapter.connect()

        assert adapter.connection is not None
        assert adapter.connection.execute("SELECT 1").fetchone()[0] == 1

    def test_initialize_schema(self):
        """测试数据库 schema 初始化"""
        from ditto.data.adapters.sqlite_adapter import SQLiteAdapter

        adapter = SQLiteAdapter(database_path=str(self.db_path))
        adapter.connect()
        adapter.initialize_schema()

        # 验证表是否创建成功
        tables = adapter.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        table_names = [table[0] for table in tables]
        expected_tables = [
            "trades", "orders", "positions", "portfolio_snapshots",
            "strategy_configs", "execution_logs", "risk_events"
        ]

        for table in expected_tables:
            assert table in table_names


class TestDataService:
    """数据服务测试"""

    def setup_method(self):
        """每个测试前执行"""
        self.temp_dir = tempfile.mkdtemp()
        self.duckdb_path = Path(self.temp_dir) / "test.duckdb"
        self.sqlite_path = Path(self.temp_dir) / "test.sqlite"

    def teardown_method(self):
        """每个测试后执行"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_service_initialization(self):
        """测试服务初始化"""
        from ditto.data.service import DataService

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path)
        )

        assert service.duckdb_path == str(self.duckdb_path)
        assert service.sqlite_path == str(self.sqlite_path)
        # 适配器实例已创建但未连接
        assert service.duckdb_adapter is not None
        assert service.sqlite_adapter is not None
        # 连接为 None（未主动连接）
        assert service.duckdb_adapter.connection is None
        assert service.sqlite_adapter.connection is None

    def test_lazy_connection(self):
        """测试懒加载连接"""
        from ditto.data.service import DataService

        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path)
        )

        # 调用方法时才创建连接
        duckdb_adapter = service.get_duckdb()
        sqlite_adapter = service.get_sqlite()

        assert duckdb_adapter is not None
        assert sqlite_adapter is not None
        assert duckdb_adapter.connection is not None
        assert sqlite_adapter.connection is not None

        # 验证数据库文件已创建
        assert self.duckdb_path.exists()
        assert self.sqlite_path.exists()