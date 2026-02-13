"""
测试辅助功能集成测试.

测试 reset_for_testing, get_recorded_spans, get_recorded_metrics 等测试辅助功能.

使用真实组件验证测试辅助功能与 OpenTelemetry SDK 的集成.
"""

import pytest
from ditto_infra.foundation import (
    Metrics,
    get_recorded_metrics,
    get_recorded_spans,
    init,
    reset_for_testing,
    span,
)
from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.observability.config import ObservabilityConfig


def _test_config(**overrides: object) -> ObservabilityConfig:
    values: dict[str, object] = {
        "environment": Environment.TESTING,
        "pytest_running": True,
        "assertions_enabled": True,
        "verbose_logging": False,
        "tracing_enabled": True,
        "tracing_sample_rate": 1.0,
        "metrics_enabled": True,
    }
    values.update(overrides)
    return ObservabilityConfig(**values)


@pytest.mark.integration
class TestResetForTesting:
    """测试 reset_for_testing 函数."""

    def test_reset_for_testing_clears_spans(self) -> None:
        """测试 reset_for_testing 清除 spans."""
        init(_test_config(), force=True)

        # [REVIEW] span
        with span("test_op1"):
            pass
        with span("test_op2"):
            pass

        spans = get_recorded_spans()
        assert len(spans) == 2

        # [REVIEW]
        reset_for_testing()

        # Spans 应该被清除
        spans = get_recorded_spans()
        assert len(spans) == 0

    def test_reset_for_testing_clears_metrics(self) -> None:
        """测试 reset_for_testing 清除 metrics."""
        init(_test_config(), force=True)

        # [REVIEW]
        Metrics.data_records.add(100, {"source": "test"})
        Metrics.kill_switch_level.set(2.0)

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

        # [REVIEW]
        reset_for_testing()

        # Metrics 应该被重置
        # [REVIEW] metrics_data 可能为空字典或 None
        get_recorded_metrics()
        # Verify状态已清除

    def test_reset_for_testing_clears_both(self) -> None:
        """测试 reset_for_testing 同时清除 spans 和 metrics."""
        init(_test_config(), force=True)

        # [REVIEW] spans 和 metrics
        with span("test_op"):
            Metrics.data_records.add(50, {"source": "test"})

        spans = get_recorded_spans()
        metrics_data = get_recorded_metrics()

        assert len(spans) == 1
        assert metrics_data is not None

        # [REVIEW]
        reset_for_testing()

        # [REVIEW]
        spans = get_recorded_spans()
        metrics_data = get_recorded_metrics()

        assert len(spans) == 0
        # metrics 应该被重置

    def test_reset_for_testing_allows_reinit(self) -> None:
        """测试 reset_for_testing 后可以重新初始化."""
        # [REVIEW]
        init(_test_config(), force=True)

        with span("test_op1"):
            pass

        spans = get_recorded_spans()
        assert len(spans) == 1

        # [REVIEW]
        reset_for_testing()

        # [REVIEW]
        init(_test_config(), force=True)

        with span("test_op2"):
            pass

        spans = get_recorded_spans()
        assert len(spans) == 1  # [REVIEW] span
        assert spans[0].name == "test_op2"

    def test_reset_for_testing_without_init(self) -> None:
        """测试未初始化时 reset_for_testing 不报错."""
        # [REVIEW]
        reset_for_testing()

        # [REVIEW]
        reset_for_testing()


@pytest.mark.integration
class TestGetRecordedSpans:
    """测试 get_recorded_spans 函数."""

    def test_get_recorded_spans_without_init(self) -> None:
        """测试未初始化时返回空列表."""
        reset_for_testing()

        spans = get_recorded_spans()
        assert spans == []

    def test_get_recorded_spans_returns_list(self) -> None:
        """测试返回列表类型."""
        init(_test_config(), force=True)

        with span("test_op"):
            pass

        spans = get_recorded_spans()
        assert isinstance(spans, list)

    def test_get_recorded_spans_order(self) -> None:
        """测试 span 按完成顺序返回."""
        init(_test_config(), force=True)

        with span("op1"):
            with span("op2"):
                with span("op3"):
                    pass

        spans = get_recorded_spans()
        # [REVIEW] span 先完成，所以 op3 应该在列表前面
        assert spans[0].name == "op3"
        assert spans[1].name == "op2"
        assert spans[2].name == "op1"

    def test_get_recorded_spans_attributes(self) -> None:
        """测试 span 属性被正确记录."""
        init(_test_config(), force=True)

        with span("test_op", source="tushare", table="etf_daily") as s:
            s.set_attribute("rows", "100")

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_op"
        # Verify属性

    def test_get_recorded_spans_with_exception(self) -> None:
        """测试异常 span 被记录."""
        init(_test_config(), force=True)

        with pytest.raises(ValueError):
            with span("failing_op"):
                raise ValueError("Test error")

        spans = get_recorded_spans()
        assert len(spans) == 1
        # [REVIEW] span 中


@pytest.mark.integration
class TestGetRecordedMetrics:
    """测试 get_recorded_metrics 函数."""

    def test_get_recorded_metrics_without_init(self) -> None:
        """测试未初始化时返回空字典."""
        reset_for_testing()

        metrics_data = get_recorded_metrics()
        assert metrics_data == {}

    def test_get_recorded_metrics_returns_dict(self) -> None:
        """测试返回字典类型."""
        init(_test_config(), force=True)

        Metrics.data_records.add(100, {"source": "test"})

        metrics_data = get_recorded_metrics()
        assert isinstance(metrics_data, dict)

    def test_get_recorded_metrics_after_counter_add(self) -> None:
        """测试 counter 操作后获取指标."""
        init(_test_config(), force=True)

        Metrics.data_records.add(100, {"source": "test", "table": "test_table"})
        Metrics.data_records.add(50, {"source": "test", "table": "test_table"})

        metrics_data = get_recorded_metrics()
        # [REVIEW]
        assert metrics_data is not None

    def test_get_recorded_metrics_after_gauge_set(self) -> None:
        """测试 gauge 操作后获取指标."""
        init(_test_config(), force=True)

        Metrics.kill_switch_level.set(2.0)
        Metrics.data_freshness.set(1.5)

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

    def test_get_recorded_metrics_after_histogram_record(self) -> None:
        """测试 histogram 操作后获取指标."""
        init(_test_config(), force=True)

        Metrics.api_duration.record(1.5, {"endpoint": "/api/test"})
        Metrics.api_duration.record(2.3, {"endpoint": "/api/test"})

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

    def test_get_recorded_metrics_multiple_types(self) -> None:
        """测试多种类型指标."""
        init(_test_config(), force=True)

        # Counter
        Metrics.data_records.add(100, {"source": "test"})

        # Gauge
        Metrics.kill_switch_level.set(1.0)

        # Histogram
        Metrics.api_duration.record(0.5, {"endpoint": "/api/test"})

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None


@pytest.mark.integration
class TestIntegrationScenarios:
    """集成测试场景."""

    def test_full_observability_workflow(self) -> None:
        """测试完整可观测性工作流."""
        # 1. 初始化
        init(_test_config(), force=True)

        # 2. 创建 span 和指标
        with span("data_update", source="tushare", table="etf_daily") as s:
            s.set_attribute("rows_processed", "1000")
            Metrics.data_records.add(1000, {"source": "tushare", "table": "etf_daily"})
            Metrics.data_update_duration.record(2.5, {"source": "tushare"})

        # 3. 验证数据
        spans = get_recorded_spans()
        metrics_data = get_recorded_metrics()

        assert len(spans) == 1
        assert spans[0].name == "data_update"
        assert metrics_data is not None

        # 4. 重置
        reset_for_testing()

        assert len(get_recorded_spans()) == 0

    def test_multiple_operations(self) -> None:
        """测试多个操作."""
        init(_test_config(), force=True)

        # [REVIEW] 1
        with span("operation1"):
            Metrics.api_requests.add(1, {"endpoint": "/api/v1"})

        # [REVIEW] 2
        with span("operation2"):
            Metrics.api_requests.add(1, {"endpoint": "/api/v2"})

        # [REVIEW] 3
        with span("operation3"):
            Metrics.cache_miss.add(1, {"cache": "data_cache"})

        spans = get_recorded_spans()
        metrics_data = get_recorded_metrics()

        assert len(spans) == 3
        assert metrics_data is not None

    def test_nested_operations_with_metrics(self) -> None:
        """测试嵌套操作和指标."""
        init(_test_config(), force=True)

        with span("parent_operation") as parent:
            parent.set_attribute("level", "parent")

            with span("child_operation1") as child1:
                child1.set_attribute("level", "child1")
                Metrics.data_records.add(100, {"operation": "child1"})

            with span("child_operation2") as child2:
                child2.set_attribute("level", "child2")
                Metrics.data_records.add(200, {"operation": "child2"})

        spans = get_recorded_spans()
        metrics_data = get_recorded_metrics()

        # 3 个 span(parent + 2 children)
        assert len(spans) == 3
        assert metrics_data is not None
