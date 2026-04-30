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

    使用 SQLITE_PATH 和 DATA_ROOT 环境变量覆盖默认路径，
    使每个测试使用独立的临时数据库文件。
    """
    original_environment = os.environ.get("ENVIRONMENT")
    original_sqlite_path = os.environ.get("SQLITE_PATH")
    original_data_root = os.environ.get("DATA_ROOT")

    # 确保 pytest 环境变量已设置（用于观察性系统）
    if "PYTEST_CURRENT_TEST" not in os.environ:
        os.environ["PYTEST_CURRENT_TEST"] = "test"

    # 强制使用 testing 配置，避免读取开发目录中的历史数据
    os.environ["ENVIRONMENT"] = "testing"

    # 设置测试专用的数据根目录和 SQLite 路径
    os.environ["DATA_ROOT"] = str(tmp_path)
    test_db_path = tmp_path / "metadata" / "metadata.sqlite"
    os.environ["SQLITE_PATH"] = str(test_db_path)

    # 确保目录存在
    test_db_path.parent.mkdir(parents=True, exist_ok=True)

    yield

    # 清理环境变量
    if original_sqlite_path is None:
        os.environ.pop("SQLITE_PATH", None)
    else:
        os.environ["SQLITE_PATH"] = original_sqlite_path

    if original_data_root is None:
        os.environ.pop("DATA_ROOT", None)
    else:
        os.environ["DATA_ROOT"] = original_data_root

    if original_environment is None:
        os.environ.pop("ENVIRONMENT", None)
    else:
        os.environ["ENVIRONMENT"] = original_environment


@pytest.fixture
def metrics_registry() -> CollectorRegistry:
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
    return CollectorRegistry()


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
def configure_observability_for_testing() -> None:
    """配置观察性系统用于测试环境（禁用日志输出到 stdout）.

    解决 CliRunner I/O 错误：
    - 设置 pytest_running=True 跳过日志 handler 配置
    - 避免后台线程写入已关闭的 stdout

    参考: https://github.com/pallets/click/issues/2156
    """
    from ditto_platform.foundation.config.environment import Environment
    from ditto_platform.foundation.observability import init
    from ditto_platform.foundation.observability.config import ObservabilityConfig

    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,  # 关键：跳过 stdout handler 配置
    )
    init(config, force=True)


# 集成测试串行执行，避免并发副作用
pytestmark = pytest.mark.serial
