"""
可观测性配置单元测试.

测试 ObservabilityConfig 的配置合并和运行时标志检测逻辑.

这是单元测试，使用 Mock 隔离环境变量等外部依赖.
"""

import pytest
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.config import (
    EffectiveConfig,
    ObservabilityConfig,
)


@pytest.mark.unit
class TestObservabilityConfig:
    """测试 ObservabilityConfig 类."""

    def test_get_effective_config_development_preset(self) -> None:
        """测试开发环境预设配置."""
        config = ObservabilityConfig(environment=Environment.DEVELOPMENT)
        effective = config.get_effective_config()

        assert effective.log_level == "DEBUG"
        assert effective.tracing_enabled is True
        assert effective.tracing_sample_rate == 1.0
        assert effective.metrics_enabled is True
        assert effective.assertions_enabled is True
        assert effective.verbose_logging is True

    def test_get_effective_config_testing_preset(self) -> None:
        """测试测试环境预设配置."""
        config = ObservabilityConfig(environment=Environment.TESTING)
        effective = config.get_effective_config()

        assert effective.log_level == "WARNING"
        assert effective.tracing_enabled is False
        assert effective.tracing_sample_rate == 0.0
        assert effective.metrics_enabled is False
        assert effective.assertions_enabled is True
        assert effective.verbose_logging is False

    def test_get_effective_config_production_preset(self) -> None:
        """测试生产环境预设配置."""
        config = ObservabilityConfig(environment=Environment.PRODUCTION)
        effective = config.get_effective_config()

        assert effective.log_level == "INFO"
        assert effective.tracing_enabled is True
        assert effective.tracing_sample_rate == 0.1
        assert effective.metrics_enabled is True
        assert effective.assertions_enabled is False
        assert effective.verbose_logging is False

    def test_get_effective_config_override_log_level(self) -> None:
        """测试覆盖日志级别."""
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            log_level="ERROR",
        )
        effective = config.get_effective_config()

        assert effective.log_level == "ERROR"
        # 其他字段使用预设值
        assert effective.tracing_enabled is True
        assert effective.metrics_enabled is True

    def test_get_effective_config_override_tracing(self) -> None:
        """测试覆盖追踪配置."""
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            tracing_enabled=False,
            tracing_sample_rate=0.5,
        )
        effective = config.get_effective_config()

        assert effective.tracing_enabled is False
        assert effective.tracing_sample_rate == 0.5
        # 其他字段使用预设值
        assert effective.log_level == "DEBUG"
        assert effective.metrics_enabled is True

    def test_get_effective_config_override_multiple_fields(self) -> None:
        """测试覆盖多个字段."""
        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            log_level="DEBUG",
            tracing_sample_rate=1.0,
            assertions_enabled=True,
        )
        effective = config.get_effective_config()

        assert effective.log_level == "DEBUG"
        assert effective.tracing_enabled is True
        assert effective.tracing_sample_rate == 1.0
        assert effective.metrics_enabled is True
        assert effective.assertions_enabled is True
        assert effective.verbose_logging is False

    def test_get_effective_config_none_values_use_preset(self) -> None:
        """测试 None 值使用预设."""
        config = ObservabilityConfig(
            environment=Environment.TESTING,
            log_level=None,
            tracing_enabled=None,
            metrics_enabled=None,
        )
        effective = config.get_effective_config()

        assert effective.log_level == "WARNING"
        assert effective.tracing_enabled is False
        assert effective.metrics_enabled is False

    def test_get_effective_config_returns_effective_config_type(self) -> None:
        """测试返回类型为 EffectiveConfig."""
        config = ObservabilityConfig(environment=Environment.DEVELOPMENT)
        effective = config.get_effective_config()

        assert isinstance(effective, EffectiveConfig)
        # 验证所有字段存在
        assert hasattr(effective, "log_level")
        assert hasattr(effective, "tracing_enabled")
        assert hasattr(effective, "tracing_sample_rate")
        assert hasattr(effective, "metrics_enabled")
        assert hasattr(effective, "vm_endpoint")
        assert hasattr(effective, "assertions_enabled")
        assert hasattr(effective, "verbose_logging")
        assert hasattr(effective, "pytest_running")

    def test_get_effective_config_custom_vm_endpoint(self) -> None:
        """测试自定义 VictoriaMetrics 端点."""
        custom_endpoint = "http://custom:9090/metrics"
        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            vm_endpoint=custom_endpoint,
        )
        effective = config.get_effective_config()

        assert effective.vm_endpoint == custom_endpoint

    def test_get_effective_config_default_vm_endpoint(self) -> None:
        """测试默认 VictoriaMetrics 端点."""
        config = ObservabilityConfig(environment=Environment.DEVELOPMENT)
        effective = config.get_effective_config()

        assert effective.vm_endpoint == "http://localhost:8428/opentelemetry/v1/metrics"


@pytest.mark.unit
class TestDetectRuntimeFlags:
    """测试运行时标志检测."""

    def test_detect_runtime_flags_testing_no_pytest(self) -> None:
        """测试测试环境无 pytest."""
        config = ObservabilityConfig(environment=Environment.TESTING)
        effective = config.get_effective_config()

        assert effective.pytest_running is False

    def test_detect_runtime_flags_testing_with_pytest(self) -> None:
        """测试测试环境有 pytest."""
        config = ObservabilityConfig(
            environment=Environment.TESTING,
            pytest_running=True,
        )
        effective = config.get_effective_config()

        assert effective.pytest_running is True

    def test_detect_runtime_flags_production(self) -> None:
        """测试生产环境标志."""
        config = ObservabilityConfig(environment=Environment.PRODUCTION)
        effective = config.get_effective_config()

        assert effective.pytest_running is False

    def test_detect_runtime_flags_development(self) -> None:
        """测试开发环境标志."""
        config = ObservabilityConfig(environment=Environment.DEVELOPMENT)
        effective = config.get_effective_config()

        assert effective.pytest_running is False
