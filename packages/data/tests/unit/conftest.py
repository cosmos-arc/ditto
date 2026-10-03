"""Pytest configuration for unit tests.

提供内存数据库 fixtures，支持快速单元测试。
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def sqlite_memory_pool() -> Generator[SQLitePool]:
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
