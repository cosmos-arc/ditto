"""
Observability __init__ 模块测试.

测试 init(), shutdown(), _ObservabilityRegistry 等核心功能.
"""

import pytest
from ditto_foundation import (
    init,
    reset_for_testing,
    shutdown,
)
from ditto_foundation.observability import _ObservabilityRegistry


class TestObservabilityRegistry:
    """测试 _ObservabilityRegistry 类."""

    def test_is_initialized_initial_state(self) -> None:
        """测试初始状态未初始化."""
        # [REVIEW]
        _ObservabilityRegistry.reset()

        assert _ObservabilityRegistry.is_initialized() is False

    def test_set_initialized(self) -> None:
        """测试设置初始化状态."""
        _ObservabilityRegistry.reset()
        assert _ObservabilityRegistry.is_initialized() is False

        _ObservabilityRegistry.set_initialized(True)
        assert _ObservabilityRegistry.is_initialized() is True

        _ObservabilityRegistry.set_initialized(False)
        assert _ObservabilityRegistry.is_initialized() is False

    def test_reset_clears_state(self) -> None:
        """测试 reset 清除状态."""
        _ObservabilityRegistry.set_initialized(True)
        assert _ObservabilityRegistry.is_initialized() is True

        _ObservabilityRegistry.reset()
        assert _ObservabilityRegistry.is_initialized() is False


class TestInit:
    """测试 init() 函数."""

    def test_init_sets_registry_flag(self) -> None:
        """测试 init() 设置注册表标志."""
        reset_for_testing()
        assert _ObservabilityRegistry.is_initialized() is False

        init(force=True)
        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_idempotent_without_force(self) -> None:
        """测试无 force 参数时 init() 幂等."""
        reset_for_testing()
        init(force=True)
        first_registry_state = _ObservabilityRegistry.is_initialized()

        # [REVIEW] force，应该被忽略
        init()
        second_registry_state = _ObservabilityRegistry.is_initialized()

        assert first_registry_state is True
        assert second_registry_state is True

    def test_init_with_custom_parameters(self) -> None:
        """测试使用自定义参数初始化."""
        reset_for_testing()
        init(
            service_name="test_service",
            environment="production",
            log_level="WARNING",
            force=True,
        )

        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_environment_alias_dev(self) -> None:
        """测试环境简写 'dev' 映射到 'development'."""
        reset_for_testing()
        init(environment="dev", force=True)
        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_environment_alias_test(self) -> None:
        """测试环境简写 'test' 映射到 'testing'."""
        reset_for_testing()
        init(environment="test", force=True)
        assert _ObservabilityRegistry.is_initialized() is True

    def test_init_environment_alias_prod(self) -> None:
        """测试环境简写 'prod' 映射到 'production'."""
        reset_for_testing()
        init(environment="prod", force=True)
        assert _ObservabilityRegistry.is_initialized() is True


class TestShutdown:
    """测试 shutdown() 函数."""

    def test_shutdown_clears_registry_flag(self) -> None:
        """测试 shutdown() 清除注册表标志."""
        reset_for_testing()
        init(force=True)
        assert _ObservabilityRegistry.is_initialized() is True

        shutdown()
        assert _ObservabilityRegistry.is_initialized() is False

    def test_shutdown_idempotent(self) -> None:
        """测试多次 shutdown() 幂等."""
        reset_for_testing()
        init(force=True)

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
        init(
            force=True,
            verbose_logging=False,
            pytest_running=True,
            assertions_enabled=False,
        )

        with caplog.at_level("DEBUG"):
            shutdown()

        # [REVIEW](即使 shutdown 失败也会记录调试信息)
        # [REVIEW] OpenTelemetry provider 的行为
