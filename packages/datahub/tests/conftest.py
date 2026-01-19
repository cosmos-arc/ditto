"""Pytest configuration for datahub tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import Mode, SQLitePool, init


@pytest.fixture(autouse=True)
def init_observability() -> None:
    """Initialize observability in testing mode for all tests."""
    init(mode=Mode.TESTING)
    # Cleanup is handled by reset_for_testing if needed


@pytest.fixture(scope="session")
def sqlite_schema_path() -> Path:
    """
    获取数据库 schema 文件路径。

    Session 级别 fixture，在整个测试会话中只计算一次。

    Returns:
        Path: 指向 schema.sql 文件的路径
    """
    schema_file = (
        Path(__file__).parent.parent
        / "src"
        / "ditto_datahub"
        / "scripts"
        / "schema.sql"
    )
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    return schema_file


@pytest.fixture
def sqlite_pool(sqlite_schema_path: Path) -> SQLitePool:
    """
    创建已初始化的 SQLite 连接池。

    每个测试函数使用独立的内存数据库，确保测试隔离。

    Args:
        sqlite_schema_path: Schema 文件路径（从 session fixture 注入）

    Returns:
        SQLitePool: 已初始化表结构的连接池
    """
    pool = SQLitePool(":memory:", schema_path=sqlite_schema_path)
    pool.init_schema()
    return pool


@pytest.fixture
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """
    创建 SQLite 客户端。

    Args:
        sqlite_pool: 已初始化的连接池

    Returns:
        SQLiteClient: SQL 执行客户端
    """
    return SQLiteClient(sqlite_pool)


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """可控的时间 fixture，通过 monkeypatch 替换时间函数.

    使 time.sleep 立即完成，time.time 按预期前进，提高测试速度和确定性。
    """
    current_time = [0.0]

    def fake_sleep(seconds: float) -> None:
        current_time[0] += seconds

    def fake_time_func() -> float:
        return current_time[0]

    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.time", fake_time_func)

    return
