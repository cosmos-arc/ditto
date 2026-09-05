"""
追踪模块边界单元测试.

测试 SpanContext 在无 tracer 时的边界情况.

这是单元测试，专注于边界行为，不涉及真实 OpenTelemetry tracer.
"""

import pytest
from ditto_platform.foundation.observability.tracing import (
    SpanContext,
    get_span_id,
    get_trace_id,
    reset_tracing,
)
from opentelemetry.trace import StatusCode


@pytest.mark.unit
class TestSpanContextEdgeCases:
    """测试 SpanContext 边界情况."""

    def test_span_context_with_none_tracer(self) -> None:
        """测试 tracer 为 None 时的 SpanContext."""
        from ditto_platform.foundation.observability.tracing import _state

        reset_tracing()
        assert _state.tracer is None

        # [REVIEW]
        ctx = SpanContext("test_operation")
        assert ctx.name == "test_operation"

        with ctx:
            # [REVIEW]
            pass

    def test_span_context_set_attribute_with_none_tracer(self) -> None:
        """测试 tracer 为 None 时 set_attribute 不报错."""
        from ditto_platform.foundation.observability.tracing import _state

        reset_tracing()
        assert _state.tracer is None

        ctx = SpanContext("test_op", key="value")

        with ctx:
            # [REVIEW] tracer
            ctx.set_attribute("another_key", "another_value")

    def test_span_context_set_status_with_none_span(self) -> None:
        """测试 span 为 None 时 set_status 不报错."""
        from ditto_platform.foundation.observability.tracing import _state

        reset_tracing()
        assert _state.tracer is None

        ctx = SpanContext("test_op")

        with ctx:
            # [REVIEW]
            ctx.set_status(StatusCode.ERROR)


@pytest.mark.unit
class TestGetTraceId:
    """测试 get_trace_id 函数."""

    def test_get_trace_id_without_init(self) -> None:
        """测试未初始化时 get_trace_id 返回空字符串."""
        from ditto_platform.foundation.observability.tracing import _state

        reset_tracing()
        assert _state.tracer is None

        trace_id = get_trace_id()
        assert trace_id == ""


@pytest.mark.unit
class TestGetSpanId:
    """测试 get_span_id 函数."""

    def test_get_span_id_without_init(self) -> None:
        """测试未初始化时 get_span_id 返回空字符串."""
        from ditto_platform.foundation.observability.tracing import _state

        reset_tracing()
        assert _state.tracer is None

        span_id = get_span_id()
        assert span_id == ""
