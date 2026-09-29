"""Execution 集成测试 fixtures（#347：真实持久化归集成职责）.

仅提供真实 SQLite 接缝所需 fixtures；unit 树的 autouse observability
初始化不在此重复——store 实现不依赖可观测性全局（迁移时已核实）。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def sqlite_pool() -> Generator[SQLitePool]:
    """Create an in-memory SQLite pool for testing."""
    pool = SQLitePool(":memory:")
    yield pool
    pool.close()


@pytest.fixture
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """Create SQLite client for testing."""
    return SQLiteClient(sqlite_pool)
