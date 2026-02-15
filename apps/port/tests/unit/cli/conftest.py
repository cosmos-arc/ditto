"""CLI 单元测试配置.

覆盖父级 conftest.py 中的 reset_observability fixture，
避免与 CliRunner 的 I/O 捕获机制冲突。
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def configure_observability_for_cli_tests() -> None:
    """Session 级别：确保 CLI 测试禁用 stdout 日志 handler.

    解决 CliRunner + pytest-xdist 的 I/O 竞态条件：
    - 设置 pytest_running=True 跳过日志 handler 配置
    - 避免后台线程写入已关闭的 stdout

    参考: https://github.com/pallets/click/issues/2156
    """
    from ditto_infra.foundation.config.environment import Environment
    from ditto_infra.foundation.observability import init
    from ditto_infra.foundation.observability.config import ObservabilityConfig

    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,  # 关键：跳过 stdout handler 配置
    )
    init(config, force=True)


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """CLI 测试不重置 observability，避免 I/O 冲突."""
    # 空操作：覆盖父级 fixture，不做任何事
