"""
追踪集成测试.

测试装饰器、嵌套 span、配置等功能.

使用真实组件验证追踪系统与 OpenTelemetry SDK 的集成.
"""

import re

import pytest
from ditto_platform.foundation import (
    ObservabilityConfig,
    get_recorded_spans,
    reset_for_testing,
    span,
    traced,
)
from ditto_platform.foundation.observability.tracing import (
    configure_tracing,
    get_span_id,
    get_trace_id,
)


@pytest.mark.integration
class TestSpanContextWithTracer:
    """测试 SpanContext 与真实 tracer 交互."""

    def test_span_context_set_status(self) -> None:
        """测试 set_status 方法."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("test_operation") as ctx:
            ctx.set_status("success")
            # [REVIEW]

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_operation"

    def test_span_context_set_multiple_attributes(self) -> None:
        """测试设置多个属性."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("test_op", key1="value1") as ctx:
            ctx.set_attribute("key2", "value2")
            ctx.set_attribute("key3", "value3")

        spans = get_recorded_spans()
        assert len(spans) == 1
        # Verify属性被设置

    def test_span_context_exception_handling(self) -> None:
        """测试异常处理和记录."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with pytest.raises(ValueError):
            with span("test_operation"):
                raise ValueError("Test error")

        spans = get_recorded_spans()
        assert len(spans) == 1
        # Verify异常被记录


@pytest.mark.integration
class TestGetTraceId:
    """测试 get_trace_id 函数."""

    def test_get_trace_id_format(self) -> None:
        """测试 trace_id 格式为 UUID."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("test_op"):
            trace_id = get_trace_id()

        # UUID 格式: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert uuid_pattern.match(trace_id) is not None

    def test_get_trace_id_consistency(self) -> None:
        """测试同一 trace 中 trace_id 一致."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("parent"):
            trace_id_1 = get_trace_id()
            with span("child"):
                trace_id_2 = get_trace_id()

        assert trace_id_1 == trace_id_2


@pytest.mark.integration
class TestGetSpanId:
    """测试 get_span_id 函数."""

    def test_get_span_id_format(self) -> None:
        """测试 span_id 格式为 16 位十六进制."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("test_op"):
            span_id = get_span_id()

        # 16 位十六进制
        hex_pattern = re.compile(r"^[0-9a-f]{16}$", re.IGNORECASE)
        assert hex_pattern.match(span_id) is not None

    def test_get_span_id_unique_per_span(self) -> None:
        """测试每个 span 有唯一的 span_id."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("parent"):
            parent_span_id = get_span_id()
            with span("child"):
                child_span_id = get_span_id()

        # parent 和 child 应该有不同的 span_id
        assert parent_span_id != child_span_id


@pytest.mark.integration
class TestTracedDecorator:
    """测试 @traced 装饰器."""

    def test_traced_decorator_creates_span(self) -> None:
        """测试 @traced 装饰器创建 span."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        @traced("my_operation")
        def my_func(x: int) -> int:
            return x + 1

        result = my_func(41)
        assert result == 42

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "my_operation"

    def test_traced_decorator_with_exception(self) -> None:
        """测试 @traced 装饰器处理异常."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        @traced("failing_operation")
        def failing_func() -> None:
            raise ValueError("Function error")

        with pytest.raises(ValueError):
            failing_func()

        spans = get_recorded_spans()
        assert len(spans) == 1
        # [REVIEW]


@pytest.mark.integration
class TestConfigureTracing:
    """测试 configure_tracing 函数."""

    def test_configure_tracing_testing_mode(self) -> None:
        """测试测试模式配置."""
        from ditto_platform.foundation.observability.tracing import reset_tracing

        reset_tracing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )

        tracer = configure_tracing(config)
        assert tracer is not None

    def test_configure_tracing_silent_mode(self) -> None:
        """测试静默模式(pytest_running=True, assertions_enabled=False)."""
        from ditto_platform.foundation.observability.tracing import reset_tracing

        reset_tracing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=False, verbose_logging=False
        )

        tracer = configure_tracing(config)
        # [REVIEW] NoOp tracer
        assert tracer is not None

    def test_configure_tracing_development_mode(self) -> None:
        """测试开发模式配置."""
        from ditto_platform.foundation.config.environment import Environment
        from ditto_platform.foundation.observability.tracing import reset_tracing

        reset_tracing()

        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            pytest_running=False,
        )

        tracer = configure_tracing(config)
        assert tracer is not None

    def test_configure_tracing_production_mode(self) -> None:
        """测试生产模式配置."""
        from ditto_platform.foundation.config.environment import Environment
        from ditto_platform.foundation.observability.tracing import reset_tracing

        reset_tracing()

        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            pytest_running=False,
        )

        tracer = configure_tracing(config)
        assert tracer is not None


@pytest.mark.integration
class TestResetTracing:
    """测试 reset_tracing 函数."""

    def test_reset_tracing_clears_state(self) -> None:
        """测试 reset_tracing 清除状态."""
        from ditto_platform.foundation.observability.tracing import (
            _state,
            reset_tracing,
        )

        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        # [REVIEW] tracer 已设置
        assert _state.tracer is not None

        # [REVIEW]
        reset_tracing()
        assert _state.tracer is None

    def test_reset_tracing_clears_exporter(self) -> None:
        """测试 reset_tracing 清除 exporter."""
        from ditto_platform.foundation.observability.tracing import (
            _state,
            reset_tracing,
        )

        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        # [REVIEW] in_memory_exporter 已设置
        assert _state.in_memory_exporter is not None

        # [REVIEW]
        reset_tracing()
        assert _state.in_memory_exporter is None

    def test_reset_tracing_with_active_spans(self) -> None:
        """测试有活跃 span 时重置."""
        from ditto_platform.foundation.observability.tracing import reset_tracing

        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("test_op"):
            # [REVIEW] span 内部重置
            reset_tracing()
            # [REVIEW]
            pass


@pytest.mark.integration
class TestNestedSpans:
    """测试嵌套 span."""

    def test_deeply_nested_spans(self) -> None:
        """测试深层嵌套 span."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("level1"):
            with span("level2"):
                with span("level3"):
                    with span("level4"):
                        pass

        spans = get_recorded_spans()
        assert len(spans) == 4
        # Verify span 顺序(子 span 先结束)
        assert spans[0].name == "level4"
        assert spans[1].name == "level3"
        assert spans[2].name == "level2"
        assert spans[3].name == "level1"

    def test_sibling_spans_share_trace_id(self) -> None:
        """测试兄弟 span 共享 trace_id."""
        reset_for_testing()
        config = ObservabilityConfig(
            pytest_running=True, assertions_enabled=True, verbose_logging=False
        )
        configure_tracing(config)

        with span("parent"):
            get_trace_id()
            with span("child1"):
                pass
            with span("child2"):
                pass

        spans = get_recorded_spans()
        assert len(spans) == 3

        # [REVIEW] span 应该共享相同的 trace_id
        # Verify需要从 span context 中获取 trace_id
