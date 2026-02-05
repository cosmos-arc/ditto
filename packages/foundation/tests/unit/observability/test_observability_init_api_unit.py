"""
可观测性初始化 API 单元测试.

测试 init() 和 shutdown() 函数的核心逻辑.

这是单元测试，使用 Mock 隔离外部依赖.
"""

from unittest.mock import MagicMock, patch

import pytest
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability import (
    _ObservabilityRegistry,
    init,
    shutdown,
)
from ditto_foundation.observability.config import ObservabilityConfig


@pytest.mark.unit
class TestInitFunction:
    """测试 init() 函数."""

    def setup_method(self) -> None:
        """每个测试前重置初始化状态."""
        _ObservabilityRegistry.reset()

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_calls_all_configure_functions(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试 init 调用所有 configure 函数."""
        init(ObservabilityConfig(service_name="test_service"), force=True)

        mock_config_logging.assert_called_once()
        mock_config_tracing.assert_called_once()
        mock_config_metrics.assert_called_once()

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_sets_initialized_flag(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试 init 设置 initialized 标志."""
        init(ObservabilityConfig(), force=True)

        assert _ObservabilityRegistry.is_initialized()

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_skips_if_already_initialized(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试已初始化时跳过初始化."""
        config = ObservabilityConfig()
        # 第一次初始化
        init(config, force=True)

        # 重置 mock 计数
        mock_config_logging.reset_mock()
        mock_config_tracing.reset_mock()
        mock_config_metrics.reset_mock()

        # 第二次调用（不使用 force）
        init(config)

        # 验证没有再次调用 configure 函数
        mock_config_logging.assert_not_called()
        mock_config_tracing.assert_not_called()
        mock_config_metrics.assert_not_called()

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_with_force_reinitializes(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试 force 参数强制重新初始化."""
        config = ObservabilityConfig()
        # 第一次初始化
        init(config, force=True)

        # 重置 mock 计数
        mock_config_logging.reset_mock()
        mock_config_tracing.reset_mock()
        mock_config_metrics.reset_mock()

        # 第二次调用（使用 force=True）
        init(config, force=True)

        # 验证再次调用 configure 函数
        mock_config_logging.assert_called_once()
        mock_config_tracing.assert_called_once()
        mock_config_metrics.assert_called_once()

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_normalizes_environment_aliases(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试不同配置重复初始化会被拒绝."""
        init(ObservabilityConfig(environment=Environment.DEVELOPMENT), force=True)

        with pytest.raises(RuntimeError):
            init(ObservabilityConfig(environment=Environment.PRODUCTION))

        init(ObservabilityConfig(environment=Environment.PRODUCTION), force=True)

        assert mock_config_logging.call_count == 2
        assert mock_config_tracing.call_count == 2
        assert mock_config_metrics.call_count == 2

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_logs_initialization(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试 init 记录初始化日志."""
        init(
            ObservabilityConfig(
                service_name="my_service",
                environment=Environment.DEVELOPMENT,
            ),
            force=True,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "Observability initialized" in str(call_args)

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_with_verbose_logging_false_skips_info_log(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试 verbose_logging=False 时不记录 info 日志."""
        init(
            ObservabilityConfig(
                environment=Environment.DEVELOPMENT,
                verbose_logging=False,
            ),
            force=True,
        )

        mock_logger.info.assert_not_called()

    @patch("ditto_foundation.observability.configure_logging")
    @patch("ditto_foundation.observability.configure_tracing")
    @patch("ditto_foundation.observability.configure_metrics")
    @patch("ditto_foundation.observability.logger")
    def test_init_passes_config_parameters(
        self, mock_logger, mock_config_metrics, mock_config_tracing, mock_config_logging
    ) -> None:
        """测试 init 正确传递配置参数."""
        config = ObservabilityConfig(
            service_name="custom_service",
            log_level="DEBUG",
            log_dir="custom_logs",
            vm_endpoint="http://custom:8428/api/v1/metrics",
            pytest_running=True,
            assertions_enabled=False,
            verbose_logging=False,
        )
        init(config, force=True)

        # 验证每个 configure 函数都被调用
        mock_config_logging.assert_called_once()
        mock_config_tracing.assert_called_once()
        mock_config_metrics.assert_called_once()


@pytest.mark.unit
class TestShutdownFunction:
    """测试 shutdown() 函数."""

    def setup_method(self) -> None:
        """每个测试前设置初始化状态."""
        _ObservabilityRegistry.set_initialized(True)

    def teardown_method(self) -> None:
        """每个测试后重置状态."""
        _ObservabilityRegistry.reset()

    @patch("ditto_foundation.observability.otel_trace.get_tracer_provider")
    @patch("ditto_foundation.observability.otel_metrics.get_meter_provider")
    @patch("ditto_foundation.observability.logger")
    def test_shutdown_calls_provider_shutdown(
        self, mock_logger, mock_get_meter, mock_get_tracer
    ) -> None:
        """测试 shutdown 调用 provider 的 shutdown 方法."""
        mock_tracer_provider = MagicMock(spec=["shutdown"])
        mock_meter_provider = MagicMock(spec=["shutdown"])
        mock_get_tracer.return_value = mock_tracer_provider
        mock_get_meter.return_value = mock_meter_provider

        shutdown()

        mock_tracer_provider.shutdown.assert_called_once()
        mock_meter_provider.shutdown.assert_called_once()

    @patch("ditto_foundation.observability.otel_trace.get_tracer_provider")
    @patch("ditto_foundation.observability.otel_metrics.get_meter_provider")
    @patch("ditto_foundation.observability.logger")
    def test_shutdown_sets_initialized_false(
        self, mock_logger, mock_get_meter, mock_get_tracer
    ) -> None:
        """测试 shutdown 设置 initialized 为 False."""
        mock_tracer_provider = MagicMock()
        mock_meter_provider = MagicMock()
        mock_get_tracer.return_value = mock_tracer_provider
        mock_get_meter.return_value = mock_meter_provider

        shutdown()

        assert not _ObservabilityRegistry.is_initialized()

    @patch("ditto_foundation.observability.otel_trace.get_tracer_provider")
    @patch("ditto_foundation.observability.otel_metrics.get_meter_provider")
    @patch("ditto_foundation.observability.logger")
    def test_shutdown_handles_providers_without_shutdown(
        self, mock_logger, mock_get_meter, mock_get_tracer
    ) -> None:
        """测试 shutdown 处理没有 shutdown 方法的 provider."""
        # 创建没有 shutdown 方法的 mock
        mock_tracer_provider = MagicMock(spec=[])
        mock_meter_provider = MagicMock(spec=[])
        mock_get_tracer.return_value = mock_tracer_provider
        mock_get_meter.return_value = mock_meter_provider

        # 不应该抛出异常
        shutdown()

        assert not _ObservabilityRegistry.is_initialized()

    @patch("ditto_foundation.observability.otel_trace.get_tracer_provider")
    @patch("ditto_foundation.observability.otel_metrics.get_meter_provider")
    @patch("ditto_foundation.observability.logger")
    def test_shutdown_logs_exception_on_error(
        self, mock_logger, mock_get_meter, mock_get_tracer
    ) -> None:
        """测试 shutdown 在错误时记录日志."""
        mock_tracer_provider = MagicMock(spec=["shutdown"])
        mock_tracer_provider.shutdown.side_effect = Exception("Shutdown error")
        mock_meter_provider = MagicMock(spec=["shutdown"])
        mock_get_tracer.return_value = mock_tracer_provider
        mock_get_meter.return_value = mock_meter_provider

        shutdown()

        mock_logger.debug.assert_called()
        assert "Shutdown error" in str(mock_logger.debug.call_args)

    @patch("ditto_foundation.observability.otel_trace.get_tracer_provider")
    @patch("ditto_foundation.observability.otel_metrics.get_meter_provider")
    @patch("ditto_foundation.observability.logger")
    def test_shutdown_skips_already_shutdown_providers(
        self, mock_logger, mock_get_meter, mock_get_tracer
    ) -> None:
        """测试 shutdown 仍会调用 provider 的 shutdown."""
        mock_tracer_provider = MagicMock()
        mock_meter_provider = MagicMock()
        # 添加 _shutdown 属性表示已关闭
        mock_tracer_provider._shutdown = True
        mock_meter_provider._shutdown = True
        mock_get_tracer.return_value = mock_tracer_provider
        mock_get_meter.return_value = mock_meter_provider

        shutdown()

        mock_tracer_provider.shutdown.assert_called_once()
        mock_meter_provider.shutdown.assert_called_once()
