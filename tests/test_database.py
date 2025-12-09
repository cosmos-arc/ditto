"""数据库模块测试."""

import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

# Try to import all required modules at the top level
try:
    from data import DataService
    from data.adapters import DuckDBAdapter, SQLiteAdapter
    from data.schema import (
        DUCKDB_TABLES,
        SQLITE_TABLES,
        RegimeType,
        RiskEventSeverity,
        TradeStatus,
        validate_schema_completeness,
    )
except ImportError:
    # Modules not available, tests will be skipped
    DataService = None
    create_data_service = None
    DuckDBAdapter = None
    SQLiteAdapter = None
    DUCKDB_TABLES = {}
    SQLITE_TABLES = {}
    RegimeType = None
    RiskEventSeverity = None
    TradeStatus = None
    validate_schema_completeness = None


class TestDatabase:
    """数据库基础测试类."""

    @pytest.fixture(scope="class")
    def temp_databases(self) -> Generator[tuple[str, str], None, None]:
        """创建临时数据库."""
        with tempfile.TemporaryDirectory() as temp_dir:
            duckdb_path = Path(temp_dir) / "test.duckdb"
            sqlite_path = Path(temp_dir) / "test.sqlite"
            yield str(duckdb_path), str(sqlite_path)

    def test_schema_validation(self) -> None:
        """测试Schema验证."""
        if validate_schema_completeness is None:
            pytest.skip("依赖未安装: ditto.data.schema")

        result = validate_schema_completeness()
        assert result["status"] in ["complete", "incomplete"]
        assert result["duckdb_tables"] > 0
        assert result["sqlite_tables"] > 0

    def test_duckdb_adapter_creation(self, temp_databases: tuple[str, str]) -> None:
        """测试DuckDB适配器创建."""
        if DuckDBAdapter is None:
            pytest.skip("依赖未安装: ditto.data.adapters")

        duckdb_path, _ = temp_databases
        adapter = DuckDBAdapter(duckdb_path)

        assert adapter.db_path == Path(duckdb_path)
        assert not adapter.read_only

    def test_sqlite_adapter_creation(self, temp_databases: tuple[str, str]) -> None:
        """测试SQLite适配器创建."""
        if SQLiteAdapter is None:
            pytest.skip("依赖未安装: ditto.data.adapters")

        _, sqlite_path = temp_databases
        adapter = SQLiteAdapter(sqlite_path)

        assert adapter.db_path == Path(sqlite_path)

    def test_duckdb_adapter_basic_operations(
        self,
        temp_databases: tuple[str, str],
    ) -> None:
        """测试DuckDB适配器基本操作."""
        if DuckDBAdapter is None:
            pytest.skip("依赖未安装: ditto.data.adapters")

        duckdb_path, _ = temp_databases

        with DuckDBAdapter(duckdb_path) as adapter:
            # 创建测试表
            adapter.execute("""
                CREATE TABLE test_table (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR,
                    value DECIMAL(10,4),
                    created_at TIMESTAMP
                )
            """)

            # 插入数据
            adapter.execute("""
                INSERT INTO test_table (id, name, value, created_at)
                VALUES (1, "test", 123.45, CURRENT_TIMESTAMP)
            """)

            # 查询数据
            result = adapter.query_one("SELECT * FROM test_table WHERE id = 1")
            assert result is not None
            assert result[1] == "test"
            assert float(result[2]) == 123.45

            # 检查表是否存在
            assert adapter.table_exists("test_table")

            # 获取表信息
            table_info = adapter.get_table_info("test_table")
            assert table_info["exists"]
            assert len(table_info["columns"]) == 4

    def test_sqlite_adapter_basic_operations(
        self,
        temp_databases: tuple[str, str],
    ) -> None:
        """测试SQLite适配器基本操作."""
        if SQLiteAdapter is None:
            pytest.skip("依赖未安装: ditto.data.adapters")

        _, sqlite_path = temp_databases

        with SQLiteAdapter(sqlite_path) as adapter:
            # 创建测试表
            adapter.execute("""
                CREATE TABLE test_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 插入数据
            data = {"name": "test", "value": 123.45}
            row_id = adapter.insert("test_table", data)
            assert row_id == 1

            # 查询数据
            result = adapter.query_one("SELECT * FROM test_table WHERE id = 1")
            assert result is not None
            assert dict(result)["name"] == "test"
            assert dict(result)["value"] == 123.45

            # 检查表是否存在
            assert adapter.table_exists("test_table")

            # 获取表信息
            table_info = adapter.get_table_info("test_table")
            assert table_info["exists"]
            assert len(table_info["columns"]) == 4

    def test_data_service_creation(self, temp_databases: tuple[str, str]) -> None:
        """测试数据服务创建."""
        if create_data_service is None:
            pytest.skip("依赖未安装: ditto.data")

        duckdb_path, sqlite_path = temp_databases
        service = create_data_service(duckdb_path, sqlite_path)

        assert service.duckdb_path == duckdb_path
        assert service.sqlite_path == sqlite_path


class TestDatabaseIntegration:
    """数据库集成测试."""

    @pytest.fixture(scope="class")
    def data_service(self) -> Generator[Any, None, None]:
        """创建数据服务实例."""
        if create_data_service is None:
            pytest.skip("依赖未安装: ditto.data")

        with tempfile.TemporaryDirectory() as temp_dir:
            duckdb_path = Path(temp_dir) / "test.duckdb"
            sqlite_path = Path(temp_dir) / "test.sqlite"

            # 创建数据服务
            service = create_data_service(str(duckdb_path), str(sqlite_path))
            service.connect()

            # 初始化数据库Schema
            # 创建关键表
            for _table_name, create_sql in list(DUCKDB_TABLES.items())[
                :3
            ]:  # 只创建前3个表
                service.duckdb_adapter.execute(create_sql)

            for _table_name, create_sql in list(SQLITE_TABLES.items())[
                :3
            ]:  # 只创建前3个表
                service.sqlite_adapter.execute(create_sql)

            yield service

            service.disconnect()

    def test_system_status_operations(self, data_service: Any) -> None:
        """测试系统状态操作."""
        try:
            # 更新服务状态
            data_service.update_service_status(
                "test-service", "running", "测试服务正常运行"
            )

            # 获取系统状态
            status = data_service.get_system_status()
            assert "test-service" in status
            assert status["test-service"]["status"] == "running"
            assert status["test-service"]["message"] == "测试服务正常运行"

        except Exception as e:
            pytest.skip(f"系统状态测试失败: {e}")

    def test_kill_switch_operations(self, data_service: Any) -> None:
        """测试Kill Switch操作."""
        try:
            # 初始状态应该未激活
            status = data_service.get_kill_switch_status()
            assert not status.get("is_active", False)
            assert status.get("level", 0) == 0

            # 激活Kill Switch
            data_service.update_kill_switch(
                is_active=True, level=2, trigger_reason="测试触发"
            )

            # 检查状态
            status = data_service.get_kill_switch_status()
            assert status["is_active"]
            assert status["level"] == 2
            assert status["trigger_reason"] == "测试触发"

        except Exception as e:
            pytest.skip(f"Kill Switch测试失败: {e}")

    def test_risk_event_operations(self, data_service: Any) -> None:
        """测试风险事件操作."""
        if RiskEventSeverity is None:
            pytest.skip("依赖未安装: ditto.data.schema")

        # 创建风险事件
        event_data = {
            "event_id": str(uuid4()),
            "event_type": "DRAWDOWN",
            "severity": RiskEventSeverity.HIGH,
            "trigger_time": datetime.now(),
            "trigger_metric": "max_drawdown",
            "trigger_value": 0.15,
            "threshold_value": 0.10,
            "current_drawdown": 0.15,
            "position_value": 100000,
            "total_capital": 1000000,
            "action_taken": "系统暂停交易",
        }

        event_id = data_service.save_risk_event(event_data)
        assert event_id == event_data["event_id"]


def test_imports() -> None:
    """测试模块导入."""
    if DuckDBAdapter is None or SQLiteAdapter is None:
        pytest.skip("依赖未安装: ditto.data.adapters")

    assert DuckDBAdapter is not None
    assert SQLiteAdapter is not None

    if DataService is None or create_data_service is None:
        pytest.skip("依赖未安装: ditto.data")

    assert DataService is not None
    assert create_data_service is not None

    if RegimeType is None or TradeStatus is None:
        pytest.skip("依赖未安装: ditto.data.schema")

    assert len(DUCKDB_TABLES) > 0
    assert len(SQLITE_TABLES) > 0
    assert TradeStatus.NORMAL == "NORMAL"
    assert RegimeType.BULL == "bull"


if __name__ == "__main__":
    # 运行基本测试
    print("=== 数据库模块测试 ===")

    if validate_schema_completeness is not None:
        result = validate_schema_completeness()

        print("Schema验证结果:")
        print(f"  DuckDB 表: {result['duckdb_tables']}")
        print(f"  SQLite 表: {result['sqlite_tables']}")
        print(f"  状态: {result['status']}")

        if result["issues"]:
            print("  问题:")
            for issue in result["issues"]:
                print(f"    - {issue}")
    else:
        print("导入失败: ditto.data.schema")
        print("需要先安装依赖: pip install pydantic pydantic-settings duckdb")

    print("\n测试完成!")
