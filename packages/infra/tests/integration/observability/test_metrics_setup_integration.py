"""
指标设置集成测试.

测试 M.setup() 方法创建所有预定义指标.

使用真实组件验证指标设置与 OpenTelemetry SDK 的集成.
"""

import pytest
from ditto_infra.foundation import M, ObservabilityConfig, reset_for_testing
from ditto_infra.foundation.observability.metrics import (
    SimpleGauge,
    configure_metrics,
)
from opentelemetry import metrics


@pytest.mark.integration
class TestMSetup:
    """测试 M.setup() 方法."""

    def test_m_setup_creates_all_metrics(self) -> None:
        """测试 M.setup() 创建所有预定义指标."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        M.setup(meter)

        # Verify所有指标都已创建
        # [REVIEW]
        assert hasattr(M, "data_update_duration")
        assert hasattr(M, "data_records")
        assert hasattr(M, "data_freshness")
        assert hasattr(M, "data_errors")

        # [REVIEW]
        assert hasattr(M, "factor_calc_duration")
        assert hasattr(M, "factor_ic")
        assert hasattr(M, "factor_health")

        # [REVIEW]
        assert hasattr(M, "signal_total")
        assert hasattr(M, "rebalance_total")

        # [REVIEW]
        assert hasattr(M, "portfolio_value")
        assert hasattr(M, "portfolio_drawdown")
        assert hasattr(M, "portfolio_drawdown_3d")

        # [REVIEW]
        assert hasattr(M, "kill_switch_level")
        assert hasattr(M, "kill_switch_total")

        # [REVIEW]
        assert hasattr(M, "scheduler_jobs")
        assert hasattr(M, "api_requests")
        assert hasattr(M, "api_duration")

        # [REVIEW]
        assert hasattr(M, "cache_hit")
        assert hasattr(M, "cache_miss")
        assert hasattr(M, "cache_hit_rate")
        assert hasattr(M, "cache_invalidations")
        assert hasattr(M, "cache_evictions")
        assert hasattr(M, "cache_size")

        # SQL 指标
        assert hasattr(M, "sql_query_duration")
        assert hasattr(M, "sql_slow_query_total")
        assert hasattr(M, "sql_query_plan_cache_hit")
        assert hasattr(M, "sql_query_plan_cache_miss")

        # JSON 指标
        assert hasattr(M, "json_serialize_duration")
        assert hasattr(M, "json_deserialize_duration")
        assert hasattr(M, "json_bytes_total")

        # DQ 指标
        assert hasattr(M, "dq_batch_checks")
        assert hasattr(M, "dq_batch_issues")
        assert hasattr(M, "dq_batch_alerts")

    def test_m_setup_histogram_types(self) -> None:
        """测试 M.setup() 正确创建 Histogram 类型."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        M.setup(meter)

        # Verify Histogram 类型
        assert isinstance(M.data_update_duration, metrics.Histogram)
        assert isinstance(M.factor_calc_duration, metrics.Histogram)
        assert isinstance(M.api_duration, metrics.Histogram)

    def test_m_setup_counter_types(self) -> None:
        """测试 M.setup() 正确创建 Counter 类型."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        M.setup(meter)

        # Verify Counter 类型
        assert isinstance(M.data_records, metrics.Counter)
        assert isinstance(M.signal_total, metrics.Counter)
        assert isinstance(M.kill_switch_total, metrics.Counter)

    def test_m_setup_gauge_types(self) -> None:
        """测试 M.setup() 正确创建 Gauge 类型."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)
        M.setup(meter)

        # Verify SimpleGauge 类型
        assert isinstance(M.data_freshness, SimpleGauge)
        assert isinstance(M.factor_ic, SimpleGauge)
        assert isinstance(M.kill_switch_level, SimpleGauge)

    def test_m_setup_unknown_metric_type_raises_error(self) -> None:
        """测试 M.setup() 遇到未知类型抛出异常."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)

        # [REVIEW] METRIC_DEFINITIONS 添加未知类型
        from ditto_infra.foundation.observability.metrics import METRIC_DEFINITIONS

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
                M.setup(meter)
        finally:
            # [REVIEW]
            METRIC_DEFINITIONS.clear()
            METRIC_DEFINITIONS.extend(original_definitions)

    def test_m_setup_is_idempotent(self) -> None:
        """测试 M.setup() 幂等性."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        meter = configure_metrics(config)

        # [REVIEW] setup
        M.setup(meter)
        first_data_records = M.data_records

        # [REVIEW] setup(应该覆盖)
        M.setup(meter)
        second_data_records = M.data_records

        # [REVIEW] Counter 类型
        assert isinstance(first_data_records, metrics.Counter)
        assert isinstance(second_data_records, metrics.Counter)


@pytest.mark.integration
class TestCreateGauge:
    """测试 _create_gauge 函数."""

    def test_create_gauge_returns_simple_gauge(self) -> None:
        """测试 _create_gauge 返回 SimpleGauge 实例."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        from ditto_infra.foundation.observability.metrics import _create_gauge

        meter = configure_metrics(config)

        gauge = _create_gauge(meter, "test.gauge", "Test gauge description")
        assert isinstance(gauge, SimpleGauge)

    def test_create_gauge_with_different_names(self) -> None:
        """测试创建不同名称的 gauge."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        from ditto_infra.foundation.observability.metrics import _create_gauge

        meter = configure_metrics(config)

        gauge1 = _create_gauge(meter, "gauge.one", "Description 1")
        gauge2 = _create_gauge(meter, "gauge.two", "Description 2")

        # [REVIEW]
        assert gauge1 is not gauge2


@pytest.mark.integration
class TestMetricsRegistry:
    """测试 _MetricsRegistry 类."""

    def test_registry_initial_state(self) -> None:
        """测试注册表初始状态."""
        from ditto_infra.foundation.observability.metrics import _MetricsRegistry

        _MetricsRegistry.reset()
        assert _MetricsRegistry.get_meter() is None
        assert _MetricsRegistry.get_in_memory_reader() is None

    def test_registry_set_and_get_meter(self) -> None:
        """测试设置和获取 meter."""
        from ditto_infra.foundation.observability.metrics import _MetricsRegistry

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
        from ditto_infra.foundation.observability.metrics import _MetricsRegistry

        _MetricsRegistry.reset()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_metrics(config)

        reader = _MetricsRegistry.get_in_memory_reader()
        assert reader is not None

    def test_registry_reset_clears_state(self) -> None:
        """测试 reset 清除状态."""
        from ditto_infra.foundation.observability.metrics import _MetricsRegistry

        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_metrics(config)

        _MetricsRegistry.reset()
        assert _MetricsRegistry.get_meter() is None
        assert _MetricsRegistry.get_in_memory_reader() is None
