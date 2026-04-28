"""Pytest configuration for integration tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
from ditto_infra.foundation import SQLitePool
from prometheus_client import CollectorRegistry


@pytest.fixture
def metrics_registry() -> Generator[CollectorRegistry, None, None]:
    """提供内存 Registry（不依赖外部服务）。

    使用方式:
        def test_metrics(metrics_registry):
            from prometheus_client import Counter
            counter = Counter("api_requests", "API 请求计数", registry=metrics_registry)
            counter.inc()
            # 验证指标值
            for metric in metrics_registry.collect():
                for sample in metric.samples:
                    if sample.name == "api_requests_total":
                        assert sample.value == 1.0
    """
    registry = CollectorRegistry()
    yield registry
    registry.clear()  # 清理


@pytest.fixture(autouse=True)
def ensure_sqlite_cleanup() -> Generator[None, None, None]:
    """确保 SQLite 连接在测试后正确关闭（Windows 兼容）。

    Windows 文件锁机制更严格，SQLite 连接未正确关闭会导致临时文件无法删除。
    通过强制垃圾回收确保连接在测试间被释放。
    """
    yield
    import gc

    gc.collect()


# 集成测试串行执行，避免并发副作用
pytestmark = pytest.mark.serial


@pytest.fixture
def sqlite_schema_path() -> Path:
    """获取 schema.sql 路径。

    返回 data 的数据库 schema 文件路径，用于初始化测试数据库。

    Returns:
        Path: schema.sql 文件的路径
    """
    return (
        Path(__file__).parent.parent.parent  # tests/integration/conftest.py -> data
        / "src"
        / "ditto_data"
        / "scripts"
        / "schema.sql"
    )


@pytest.fixture
def sqlite_pool_with_schema(
    sqlite_schema_path: Path, tmp_path: Path
) -> Generator[SQLitePool, None, None]:
    """创建已初始化 schema 的 SQLite 连接池。

    使用临时文件数据库（而非内存数据库），更适合集成测试场景。
    每个测试函数获得独立的数据库文件，确保测试隔离。

    Args:
        sqlite_schema_path: Schema 文件路径
        tmp_path: pytest 的临时目录 fixture

    Yields:
        SQLitePool: 已初始化表结构的连接池
    """
    db_path = tmp_path / "meta" / "hub.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    pool = SQLitePool(str(db_path), schema_path=sqlite_schema_path)
    pool.init_schema()
    yield pool
    pool.close()
