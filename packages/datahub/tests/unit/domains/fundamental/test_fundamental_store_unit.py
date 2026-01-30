"""Unit tests for FundamentalStore."""

from __future__ import annotations

import pytest
from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库用于测试."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> FundamentalStore:
    """创建 FundamentalStore 实例."""
    return FundamentalStore(sqlite_client=in_memory_db)


def test_fundamental_store_init(store: FundamentalStore) -> None:
    """测试 FundamentalStore 初始化."""
    assert store is not None
    assert store._client is not None
