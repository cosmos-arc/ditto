"""Fixtures for derived service tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def sqlite_memory_pool() -> Generator[SQLitePool, None, None]:
    """提供内存 SQLite 数据库池。

    每个测试函数使用独立的内存数据库，测试结束后自动清理。
    """
    schema_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent.parent.parent
        / "packages"
        / "datahub"
        / "src"
        / "ditto_datahub"
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
