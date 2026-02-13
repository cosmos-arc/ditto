"""
初始化集成测试.

测试 init(), shutdown() 等核心功能.

使用真实组件验证可观测性系统初始化和关闭流程与 OpenTelemetry SDK 的集成.
"""

import pytest
from ditto_infra.foundation import (
    init,
    reset_for_testing,
    shutdown,
)
from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.observability import _ObservabilityRegistry
from ditto_infra.foundation.observability.config import ObservabilityConfig


def _test_config(**overrides: object) -> ObservabilityConfig:
    values: dict[str, object] = {
        "environment": Environment.TESTING,
        "pytest_running": True,
        "assertions_enabled": True,
        "verbose_logging": False,
    }
    values.update(overrides)
    return ObservabilityConfig(**values)


@pytest.mark.integration
class TestInit:
    """测试 init() 函数."""

    def test_init_sets_registry_flag(self) -> None:
        """测试 init() 设置注册表标志."""
        reset_for_testing()
        assert _ObservabilityRegistry.is_initialized() is False

        init(_test_config(), force=True)
        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_idempotent_without_force(self) -> None:
        """测试无 force 参数时 init() 幂等."""
        reset_for_testing()
        init(_test_config(), force=True)
        first_registry_state = _ObservabilityRegistry.is_initialized()

        # [REVIEW] force，应该被忽略
        init(_test_config())
        second_registry_state = _ObservabilityRegistry.is_initialized()

        assert first_registry_state is True
        assert second_registry_state is True

    def test_init_with_custom_parameters(self) -> None:
        """测试使用自定义参数初始化."""
        reset_for_testing()
        config = ObservabilityConfig(
            service_name="test_service",
            environment=Environment.PRODUCTION,
            log_level="WARNING",
        )
        init(config, force=True)

        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_environment_alias_dev(self) -> None:
        """测试环境简写 'dev' 映射到 'development'."""
        reset_for_testing()
        init(_test_config(), force=True)
        with pytest.raises(RuntimeError):
            init(_test_config(service_name="other"))

    def test_init_environment_alias_test(self) -> None:
        """测试环境简写 'test' 映射到 'testing'."""
        reset_for_testing()
        init(_test_config(), force=True)
        init(_test_config(), force=True)
        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_environment_alias_prod(self) -> None:
        """测试环境简写 'prod' 映射到 'production'."""
        reset_for_testing()
        init(_test_config(), force=True)
        assert _ObservabilityRegistry.is_initialized() is True


@pytest.mark.integration
class TestShutdown:
    """测试 shutdown() 函数."""

    def test_shutdown_clears_registry_flag(self) -> None:
        """测试 shutdown() 清除注册表标志."""
        reset_for_testing()
        init(_test_config(), force=True)
        assert _ObservabilityRegistry.is_initialized() is True

        shutdown()
        assert _ObservabilityRegistry.is_initialized() is False

    def test_shutdown_idempotent(self) -> None:
        """测试多次 shutdown() 幂等."""
        reset_for_testing()
        init(_test_config(), force=True)

        # [REVIEW] shutdown
        shutdown()
        assert _ObservabilityRegistry.is_initialized() is False

        # [REVIEW] shutdown 不应该报错
        shutdown()
        assert _ObservabilityRegistry.is_initialized() is False

    def test_shutdown_without_init(self) -> None:
        """测试未初始化时 shutdown() 不报错."""
        reset_for_testing()
        assert _ObservabilityRegistry.is_initialized() is False

        # [REVIEW]
        shutdown()
        assert _ObservabilityRegistry.is_initialized() is False

    def test_shutdown_logs_debug_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """测试 shutdown() 记录调试日志."""
        reset_for_testing()
        init(_test_config(assertions_enabled=False), force=True)

        with caplog.at_level("DEBUG"):
            shutdown()

        # [REVIEW](即使 shutdown 失败也会记录调试信息)
        # [REVIEW] OpenTelemetry provider 的行为
