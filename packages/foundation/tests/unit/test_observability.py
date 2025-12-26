"""
可观测性模块测试.

测试日志、追踪和指标功能的核心行为.
"""

import os
import re

from ditto_foundation import (
    M,
    Mode,
    ObservabilityConfig,
    get_recorded_metrics,
    get_recorded_spans,
    get_span_id,
    get_trace_id,
    init,
    logger,
    reset_for_testing,
    span,
    traced,
)


class TestMode:
    """测试运行模式."""

    def test_mode_detection(self) -> None:
        """测试模式检测."""
        # 保存原始环境变量
        original_mode = os.environ.get("DITTO_OBSERVABILITY_MODE")

        try:
            # 测试 production 模式
            os.environ["DITTO_OBSERVABILITY_MODE"] = "production"
            config = ObservabilityConfig(environment="production")
            assert config.detect_mode() == Mode.PRODUCTION

            # 测试 development 模式
            os.environ["DITTO_OBSERVABILITY_MODE"] = "development"
            config = ObservabilityConfig(environment="dev")
            assert config.detect_mode() == Mode.DEVELOPMENT

        finally:
            # 恢复原始环境变量
            if original_mode is None:
                os.environ.pop("DITTO_OBSERVABILITY_MODE", None)
            else:
                os.environ["DITTO_OBSERVABILITY_MODE"] = original_mode

    def test_mode_is_testing(self) -> None:
        """测试 is_testing 方法."""
        assert Mode.TESTING.is_testing() is True
        assert Mode.TESTING_WITH_ASSERTIONS.is_testing() is True
        assert Mode.PRODUCTION.is_testing() is False
        assert Mode.DEVELOPMENT.is_testing() is False

    def test_mode_is_silent(self) -> None:
        """测试 is_silent 方法."""
        assert Mode.TESTING.is_silent() is True
        assert Mode.TESTING_WITH_ASSERTIONS.is_silent() is False
        assert Mode.PRODUCTION.is_silent() is False


class TestInit:
    """测试初始化."""

    def test_init_default(self) -> None:
        """测试默认初始化."""
        reset_for_testing()
        init(force=True)
        # 应该成功初始化不报错

    def test_init_with_mode(self) -> None:
        """测试指定模式初始化."""
        reset_for_testing()
        init(mode=Mode.TESTING, force=True)
        # 应该成功初始化不报错

    def test_init_idempotent(self) -> None:
        """测试多次初始化幂等性."""
        reset_for_testing()
        init(mode=Mode.TESTING, force=True)
        init(mode=Mode.TESTING)  # 第二次调用应该被忽略(不报错)


class TestSpan:
    """测试 Span 功能."""

    def test_span_created(self) -> None:
        """测试 Span 创建."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("test_operation", key="value"):
            pass

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_operation"
        assert spans[0].attributes.get("key") == "value"

    def test_span_attributes(self) -> None:
        """测试 Span 属性设置."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("test_op", source="tushare") as s:
            s.set_attribute("rows", 100)

        spans = get_recorded_spans()
        assert spans[0].attributes.get("source") == "tushare"
        assert spans[0].attributes.get("rows") == "100"

    def test_nested_spans(self) -> None:
        """测试嵌套 Span."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("parent"):
            with span("child"):
                pass

        spans = get_recorded_spans()
        assert len(spans) == 2
        assert spans[0].name == "child"
        assert spans[1].name == "parent"

    def test_span_records_exception(self) -> None:
        """测试 Span 记录异常."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        try:
            with span("test_operation"):
                raise ValueError("test error")
        except ValueError:
            pass

        spans = get_recorded_spans()
        assert len(spans) == 1
        # 检查是否记录了异常

    def test_traced_decorator(self) -> None:
        """测试 @traced 装饰器."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        @traced("my_operation")
        def my_func(x: int) -> int:
            return x + 1

        result = my_func(41)
        assert result == 42

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "my_operation"


class TestTraceId:
    """测试 trace_id 功能."""

    def test_trace_id_format(self) -> None:
        """测试 trace_id 格式 (UUID)."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("test_op"):
            trace_id = get_trace_id()

        # UUID 格式: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert trace_id is not None
        assert uuid_pattern.match(trace_id) is not None

    def test_span_id_format(self) -> None:
        """测试 span_id 格式 (16位十六进制)."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("test_op"):
            span_id = get_span_id()

        # 16位十六进制
        hex_pattern = re.compile(r"^[0-9a-f]{16}$", re.IGNORECASE)
        assert span_id is not None
        assert hex_pattern.match(span_id) is not None

    def test_trace_id_consistency(self) -> None:
        """测试同一 trace 中 trace_id 一致."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("parent"):
            trace_id_1 = get_trace_id()
            with span("child"):
                trace_id_2 = get_trace_id()

        assert trace_id_1 == trace_id_2


class TestMetrics:
    """测试指标功能."""

    def test_counter_incremented(self) -> None:
        """测试 Counter 递增."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        M.data_records.add(
            100, {"source": "test", "table": "test", "status": "success"}
        )

        # 指标应该被记录
        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

    def test_gauge_set(self) -> None:
        """测试 Gauge 设置."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        M.kill_switch_level.set(2, {"strategy": "test"})

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

    def test_histogram_record(self) -> None:
        """测试 Histogram 记录."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        M.data_update_duration.record(1.5, {"source": "test", "table": "test"})

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None


class TestLogging:
    """测试日志功能."""

    def test_logger_with_event_field(self) -> None:
        """测试带 event 字段的日志."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        # 不应该报错
        logger.info("Test message", event="test_event", key="value")

    def test_logger_with_trace_id_context(self) -> None:
        """测试带 trace_id 上下文的日志."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("test_op"):
            trace_id = get_trace_id()
            logger.bind(trace_id=trace_id).info(
                "Test with trace_id",
                event="test_event",
            )


class TestReset:
    """测试重置功能."""

    def test_reset_for_testing(self) -> None:
        """测试重置功能."""
        reset_for_testing()
        init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)

        with span("test_op"):
            pass

        spans = get_recorded_spans()
        assert len(spans) == 1

        reset_for_testing()

        spans = get_recorded_spans()
        assert len(spans) == 0
