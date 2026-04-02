"""Pytest configuration for unit tests.

提供内存数据库 fixtures，支持快速单元测试。

这个文件为 tests/unit/ 目录下的所有测试自动添加 @pytest.mark.unit marker。
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """为 unit 目录下的所有测试自动添加 unit marker.

    Args:
        items: pytest 收集到的所有测试项
    """
    for item in items:
        # 检查测试文件是否在 unit 目录下且没有 unit marker
        is_unit_path = "/tests/unit/" in str(item.fspath) or "\\tests\\unit\\" in str(
            item.fspath
        )
        has_unit_marker = "unit" in [mark.name for mark in item.iter_markers()]

        if is_unit_path and not has_unit_marker:
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def sqlite_memory_pool() -> Generator[SQLitePool, None, None]:
    """提供内存 SQLite 数据库池。

    每个测试函数使用独立的内存数据库，测试结束后自动清理。
    """
    # Get schema path relative to this conftest.py file
    # conftest.py: packages/data/tests/unit/conftest.py -> 3 levels up -> packages/data/
    # schema.sql: packages/data/src/ditto_data/scripts/schema.sql
    schema_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "ditto_data"
        / "scripts"
        / "schema.sql"
    )
    pool = SQLitePool(":memory:", schema_path=schema_path)
    pool.init_schema()
    yield pool
    pool.close()


@pytest.fixture
def sqlite_client(sqlite_memory_pool: SQLitePool) -> SQLiteClient:
    """提供 SQLite 客户端，基于内存数据库。"""
    return SQLiteClient(sqlite_memory_pool)


@pytest.fixture
def db_client(sqlite_client: SQLiteClient) -> SQLiteClient:
    """数据库客户端别名，方便直接使用。"""
    return sqlite_client


@pytest.fixture
def duckdb_memory() -> Generator:
    """提供内存 DuckDB 连接。

    适用于测试 SQL 查询逻辑，不需要持久化。

    Note: 需要导入 duckdb
    """
    import duckdb

    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def duckdb_memory_with_tables(duckdb_memory) -> Generator:
    """提供内存 DuckDB 连接，并初始化测试表。

    可根据需要扩展此 fixture 来添加更多测试表。
    """
    # 创建示例测试表
    duckdb_memory.execute("""
        CREATE TABLE test_data AS
        SELECT * FROM VALUES
            (1, 'a', 100.0),
            (2, 'b', 200.0),
            (3, 'c', 300.0)
    """)
    return duckdb_memory
