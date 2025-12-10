"""集成测试 - 数据库适配器相关功能."""

import shutil
import tempfile
from pathlib import Path

import pytest
from ditto_core.data.adapters.duckdb_adapter import DuckDBAdapter
from ditto_core.data.adapters.sqlite_adapter import SQLiteAdapter


class TestDuckDBAdapter:
    """DuckDB 适配器集成测试."""

    def setup_method(self) -> None:
        """每个测试前执行."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.duckdb"

    def teardown_method(self) -> None:
        """每个测试后执行."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.integration
    def test_create_adapter_with_path(self) -> None:
        """测试使用路径创建适配器."""
        adapter = DuckDBAdapter(db_path=str(self.db_path))

        assert str(adapter.db_path) == str(self.db_path)
        # Removed: adapter.connection is not None when created

    @pytest.mark.integration
    def test_connection_creation(self) -> None:
        """测试连接创建."""
        adapter = DuckDBAdapter(db_path=str(self.db_path))

        assert adapter.connection is not None
        assert adapter.connection.execute("SELECT 1").fetchone()[0] == 1

    @pytest.mark.integration
    def test_initialize_schema(self) -> None:
        """测试数据库 schema 初始化."""
        adapter = DuckDBAdapter(db_path=str(self.db_path))

        # 验证表是否创建成功
        tables = adapter.connection.execute("SHOW TABLES").fetchall()

        table_names = [table[0] for table in tables]
        expected_tables = [
            "etf_info",
            "daily_price",
            "adjustment_factors",
            "trading_calendar",
        ]

        for table in expected_tables:
            assert table in table_names


class TestSQLiteAdapter:
    """SQLite 适配器集成测试."""

    def setup_method(self) -> None:
        """每个测试前执行."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.sqlite"

    def teardown_method(self) -> None:
        """每个测试后执行."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.integration
    def test_create_adapter_with_path(self) -> None:
        """测试使用路径创建适配器."""
        adapter = SQLiteAdapter(db_path=str(self.db_path))

        assert str(adapter.db_path) == str(self.db_path)
        # Removed: adapter.connection is not None when created

    @pytest.mark.integration
    def test_connection_creation(self) -> None:
        """测试连接创建."""
        adapter = SQLiteAdapter(db_path=str(self.db_path))

        assert adapter.connection is not None
        assert adapter.connection.execute("SELECT 1").fetchone()[0] == 1

    @pytest.mark.integration
    def test_initialize_schema(self) -> None:
        """测试数据库 schema 初始化."""
        adapter = SQLiteAdapter(db_path=str(self.db_path))

        # 验证表是否创建成功
        tables = adapter.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        table_names = [table[0] for table in tables]
        expected_tables = [
            "trades",
            "orders",
            "positions",
            "portfolio_snapshots",
            "strategy_configs",
            "execution_logs",
        ]

        for table in expected_tables:
            assert table in table_names
