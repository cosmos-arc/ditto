"""Pytest configuration for integration tests.

这个文件为 tests/integration/ 目录下的所有测试自动添加 @pytest.mark.integration marker。
"""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from prefect.testing.utilities import prefect_test_harness
from prometheus_client import CollectorRegistry


@pytest.fixture(autouse=True)
def set_test_database_path(tmp_path: Path) -> Generator[None, None, None]:
    """为每个测试设置独立的数据库路径，支持并行测试.

    使用 DB_SQLITE_PATH 环境变量覆盖默认路径，使每个测试使用独立的临时数据库文件.
    """
    # 确保 pytest 环境变量已设置（用于观察性系统）
    if "PYTEST_CURRENT_TEST" not in os.environ:
        os.environ["PYTEST_CURRENT_TEST"] = "test"

    # 设置测试专用的 SQLite 路径
    test_db_path = tmp_path / "meta" / "hub.sqlite"
    os.environ["DB_SQLITE_PATH"] = str(test_db_path)

    # 确保目录存在
    test_db_path.parent.mkdir(parents=True, exist_ok=True)

    yield

    # 清理环境变量
    os.environ.pop("DB_SQLITE_PATH", None)


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


@pytest.fixture(scope="session")
def prefect_test_session() -> Generator[None, None, None]:
    """Session 级别的 Prefect test harness。

    禁用 Prefect 控制台日志，避免测试结束时 Rich Console I/O 错误：
    - pytest 测试结束时关闭 stderr
    - 但 Prefect server.stop() 在 atexit 时记录日志
    - 导致 Rich Console 尝试写入已关闭的文件句柄
    """
    import os

    # 禁用 Prefect 控制台日志，避免 Rich Console I/O 错误
    os.environ["PREFECT_LOGGING_COLORS"] = "False"
    os.environ["PREFECT_SERVER_LOGGING_LEVEL"] = "CRITICAL"

    with prefect_test_harness(server_startup_timeout=30):
        yield


@pytest.fixture(scope="session", autouse=True)
def configure_observability_for_testing() -> Generator[None, None, None]:
    """配置观察性系统用于测试环境（禁用日志输出到 stdout）.

    解决 CliRunner I/O 错误：
    - pytest 运行时禁用观察性系统的 stdout 日志处理器
    - 避免测试结束时 stdout 被关闭导致的 I/O 错误
    """
    import os

    # 设置环境变量，让 ObservabilityConfig.detect_runtime_flags() 检测到 pytest 环境
    # 这样 ConfigProvider.observability() 调用 init() 时会自动设置 pytest_running=True
    os.environ["PYTEST_CURRENT_TEST"] = "test"

    return

    # 不清理环境变量，让它在整个测试 session 中保持设置
    # os.environ.pop("PYTEST_CURRENT_TEST", None)


# 集成测试串行执行，避免并发副作用
pytestmark = pytest.mark.serial


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """为 integration 目录下的所有测试自动添加 integration 和 serial marker.

    Args:
        items: pytest 收集到的所有测试项
    """
    for item in items:
        # 检查测试文件是否在 integration 目录下
        is_integration_path = "/integration/" in str(
            item.fspath
        ) or "\\integration\\" in str(item.fspath)

        if is_integration_path:
            # 添加 integration marker（如果没有）
            has_integration_marker = "integration" in [
                mark.name for mark in item.iter_markers()
            ]
            if not has_integration_marker:
                item.add_marker(pytest.mark.integration)

            # 添加 serial marker（如果没有）
            has_serial_marker = "serial" in [mark.name for mark in item.iter_markers()]
            if not has_serial_marker:
                item.add_marker(pytest.mark.serial)
