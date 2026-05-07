"""
指标设置集成测试.

测试 Metrics.setup() 方法创建所有预定义指标.

使用真实组件验证指标设置与 OpenTelemetry SDK 的集成.
"""

import pytest
from ditto_platform.foundation import Metrics, ObservabilityConfig, reset_for_testing
from ditto_platform.foundation.observability.metrics import (
    SafeCounter,
    SafeGauge,
    SafeHistogram,
    configure_metrics,
)


@pytest.mark.integration
class TestMSetup:
    """测试 Metrics.setup() 方法."""

    def test_m_setup_creates_all_metrics(self) -> None:
        """测试 Metrics.setup() 创建所有预定义指标."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        Metrics.setup(meter)

        # Verify所有平台指标都已创建
        # [REVIEW]
        assert hasattr(Metrics, "scheduler_jobs")
        assert hasattr(Metrics, "api_requests")
        assert hasattr(Metrics, "api_duration")

        # [REVIEW]
        assert hasattr(Metrics, "cache_hit")
        assert hasattr(Metrics, "cache_miss")
        assert hasattr(Metrics, "cache_hit_rate")
        assert hasattr(Metrics, "cache_invalidations")
        assert hasattr(Metrics, "cache_evictions")
        assert hasattr(Metrics, "cache_size")

        # SQL 指标
        assert hasattr(Metrics, "sql_query_duration")
        assert hasattr(Metrics, "sql_slow_query_total")
        assert hasattr(Metrics, "sql_query_plan_cache_hit")
        assert hasattr(Metrics, "sql_query_plan_cache_miss")

        # JSON 指标
        assert hasattr(Metrics, "json_serialize_duration")
        assert hasattr(Metrics, "json_deserialize_duration")
        assert hasattr(Metrics, "json_bytes_total")

    def test_m_setup_histogram_types(self) -> None:
        """测试 Metrics.setup() 正确创建 Histogram 类型."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        Metrics.setup(meter)

        # Verify Histogram 类型
        assert isinstance(Metrics.api_duration, SafeHistogram)
        assert isinstance(Metrics.sql_query_duration, SafeHistogram)
        assert isinstance(Metrics.json_serialize_duration, SafeHistogram)

    def test_m_setup_counter_types(self) -> None:
        """测试 Metrics.setup() 正确创建 Counter 类型."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        Metrics.setup(meter)

        # Verify Counter 类型
        assert isinstance(Metrics.api_requests, SafeCounter)
        assert isinstance(Metrics.scheduler_jobs, SafeCounter)
        assert isinstance(Metrics.cache_hit, SafeCounter)

    def test_m_setup_gauge_types(self) -> None:
        """测试 Metrics.setup() 正确创建 Gauge 类型."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        Metrics.setup(meter)

        # Verify SafeGauge 类型

        assert isinstance(Metrics.cache_hit_rate, SafeGauge)
        assert isinstance(Metrics.cache_size, SafeGauge)

    def test_m_setup_unknown_metric_type_raises_error(self) -> None:
        """测试 Metrics.setup() 遇到未知类型抛出异常."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)

        # [REVIEW] METRIC_DEFINITIONS 添加未知类型
        from ditto_platform.foundation.observability.metrics import METRIC_DEFINITIONS

        original_definitions = METRIC_DEFINITIONS.copy()
        try:
            # [REVIEW]
            METRIC_DEFINITIONS.append(
                {
                    "name": "invalid_metric",
                    "instrument_name": "ditto.invalid",
                    "type": "unknown_type",
                    "description": "Invalid metric type",
                }
            )

            with pytest.raises(ValueError, match="Unknown metric type"):
                Metrics.setup(meter)
        finally:
            # [REVIEW]
            METRIC_DEFINITIONS.clear()
            METRIC_DEFINITIONS.extend(original_definitions)

    def test_m_setup_is_idempotent(self) -> None:
        """测试 Metrics.setup() 幂等性."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)

        # [REVIEW] setup
        Metrics.setup(meter)
        first_api_requests = Metrics.api_requests

        # [REVIEW] setup(应该覆盖)
        Metrics.setup(meter)
        second_api_requests = Metrics.api_requests

        # [REVIEW] Counter 类型
        assert isinstance(first_api_requests, SafeCounter)
        assert isinstance(second_api_requests, SafeCounter)


@pytest.mark.integration
class TestMetricsRegistry:
    """测试 _MetricsRegistry 类."""

    def test_registry_initial_state(self) -> None:
        """测试注册表初始状态."""
        from ditto_platform.foundation.observability.metrics import _MetricsRegistry

        _MetricsRegistry.reset()
        assert _MetricsRegistry.get_meter() is None
        assert _MetricsRegistry.get_in_memory_reader() is None

    def test_registry_set_and_get_meter(self) -> None:
        """测试设置和获取 meter."""
        from ditto_platform.foundation.observability.metrics import _MetricsRegistry

        _MetricsRegistry.reset()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)

        stored_meter = _MetricsRegistry.get_meter()
        assert stored_meter is not None
        assert stored_meter is meter

    def test_registry_set_and_get_reader(self) -> None:
        """测试设置和获取 in_memory_reader."""
        from ditto_platform.foundation.observability.metrics import _MetricsRegistry

        _MetricsRegistry.reset()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_metrics(config)

        reader = _MetricsRegistry.get_in_memory_reader()
        assert reader is not None

    def test_registry_reset_clears_state(self) -> None:
        """测试 reset 清除状态."""
        from ditto_platform.foundation.observability.metrics import _MetricsRegistry

        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_metrics(config)

        _MetricsRegistry.reset()
        assert _MetricsRegistry.get_meter() is None
        assert _MetricsRegistry.get_in_memory_reader() is None
