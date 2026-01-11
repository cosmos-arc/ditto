"""可观测性测试配置和控制.

此模块提供可观测性测试的环境变量控制逻辑，支持通过环境变量动态控制测试行为：
- DITTO_TEST_OBSERVABILITY: 启用/禁用可观测性测试（enabled/disabled）
- DITTO_OBSERVABILITY_TEST_MODE: 测试模式（local/docker/ci）
- DITTO_OBSERVABILITY_TEST_TIMEOUT: 测试超时时间（秒）
- DITTO_OBSERVABILITY_SKIP_EXTERNAL_CHECKS: 是否跳过外部依赖检查（true/false）
"""

import os

import pytest


@pytest.fixture(scope="session")
def observability_test_config() -> dict:
    """可观测性测试配置fixture.

    从环境变量读取配置，提供测试运行时的可观测性控制参数。

    Returns:
        dict: 包含以下键的配置字典：
            - enabled: bool, 是否启用可观测性测试
            - test_mode: str, 测试运行模式（local/docker/ci）
            - timeout: int, 测试超时时间（秒）
            - skip_external: bool, 是否跳过外部依赖检查

    Environment Variables:
        DITTO_TEST_OBSERVABILITY: 控制是否启用可观测性测试（默认: disabled）
        DITTO_OBSERVABILITY_TEST_MODE: 测试运行环境（默认: local）
        DITTO_OBSERVABILITY_TEST_TIMEOUT: 超时时间（默认: 30秒）
        DITTO_OBSERVABILITY_SKIP_EXTERNAL_CHECKS: 跳过外部检查（默认: false）
    """
    return {
        "enabled": os.environ.get("DITTO_TEST_OBSERVABILITY", "disabled") == "enabled",
        "test_mode": os.environ.get("DITTO_OBSERVABILITY_TEST_MODE", "local"),
        "timeout": int(os.environ.get("DITTO_OBSERVABILITY_TEST_TIMEOUT", "30")),
        "skip_external": os.environ.get(
            "DITTO_OBSERVABILITY_SKIP_EXTERNAL_CHECKS", "false"
        ).lower()
        == "true",
    }


@pytest.fixture(autouse=True)
def skip_observability_tests_if_disabled(observability_test_config):
    """自动跳过禁用的可观测性测试.

    当 DITTO_TEST_OBSERVABILITY=disabled 时，自动跳过所有标记为 observability 的测试。
    此 fixture 会自动应用于所有测试，无需手动调用。

    Args:
        observability_test_config: 从 observability_test_config fixture 注入的配置

    Note:
        此 fixture 使用 autouse=True，会自动应用于所有测试。
        要跳过特定测试，可以在测试函数上添加 @pytest.mark.observability 标记。
    """
    if not observability_test_config["enabled"]:
        pytest.skip("DITTO_TEST_OBSERVABILITY=disabled, skipping observability tests")
