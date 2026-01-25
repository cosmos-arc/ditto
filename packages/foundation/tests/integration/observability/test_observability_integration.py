"""
可观测性综合集成测试.

测试配置、初始化、日志、追踪和指标的完整工作流.

使用真实组件验证可观测性系统与 OpenTelemetry SDK 的集成。
"""

import re

import pytest
from ditto_foundation import (
    EffectiveConfig,
    M,
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


class TestPresetConfig:
    """测试预设配置系统."""

    def test_development_preset_defaults(self) -> None:
        """测试开发环境预设默认值."""
        config = ObservabilityConfig(profile="development")
        effective = config.get_effective_config()

        assert effective.log_level == "DEBUG"
        assert effective.tracing_enabled is True
        assert effective.tracing_sample_rate == 1.0
        assert effective.metrics_enabled is True
        assert effective.assertions_enabled is True
        assert effective.verbose_logging is True
        assert effective.pytest_running is False

    def test_testing_preset_defaults(self) -> None:
        """测试测试环境预设默认值."""
        config = ObservabilityConfig(profile="testing")
        effective = config.get_effective_config()

        assert effective.log_level == "WARNING"
        assert effective.tracing_enabled is False
        assert effective.tracing_sample_rate == 0.0
        assert effective.metrics_enabled is False
        assert effective.assertions_enabled is False
        assert effective.verbose_logging is False
        assert effective.pytest_running is False

    def test_production_preset_defaults(self) -> None:
        """测试生产环境预设默认值."""
        config = ObservabilityConfig(profile="production")
        effective = config.get_effective_config()

        assert effective.log_level == "INFO"
        assert effective.tracing_enabled is True
        assert effective.tracing_sample_rate == 0.1
        assert effective.metrics_enabled is True
        assert effective.assertions_enabled is False
        assert effective.verbose_logging is False
        assert effective.pytest_running is False

    def test_override_log_level(self) -> None:
        """测试覆盖日志级别."""
        config = ObservabilityConfig(profile="development", log_level="ERROR")
        effective = config.get_effective_config()

        assert effective.log_level == "ERROR"
        # [REVIEW]
        assert effective.tracing_enabled is True
        assert effective.metrics_enabled is True

    def test_override_tracing(self) -> None:
        """测试覆盖追踪配置."""
        config = ObservabilityConfig(
            profile="development",
            tracing_enabled=False,
            tracing_sample_rate=0.5,
        )
        effective = config.get_effective_config()

        assert effective.tracing_enabled is False
        assert effective.tracing_sample_rate == 0.5
        # [REVIEW]
        assert effective.log_level == "DEBUG"
        assert effective.metrics_enabled is True

    def test_override_multiple_fields(self) -> None:
        """测试覆盖多个字段."""
        config = ObservabilityConfig(
            profile="production",
            log_level="DEBUG",
            tracing_sample_rate=1.0,
            assertions_enabled=True,
        )
        effective = config.get_effective_config()

        assert effective.log_level == "DEBUG"  # [REVIEW]
        assert effective.tracing_enabled is True  # [REVIEW]
        assert effective.tracing_sample_rate == 1.0  # [REVIEW]
        assert effective.metrics_enabled is True  # [REVIEW]
        assert effective.assertions_enabled is True  # [REVIEW]
        assert effective.verbose_logging is False  # [REVIEW]

    def test_pytest_running_flag(self) -> None:
        """测试 pytest_running 标志."""
        config = ObservabilityConfig(profile="development", pytest_running=True)
        effective = config.get_effective_config()

        assert effective.pytest_running is True
        # [REVIEW]
        assert effective.log_level == "DEBUG"
        assert effective.assertions_enabled is True

    def test_none_values_use_preset(self) -> None:
        """测试 None 值使用预设."""
        config = ObservabilityConfig(
            profile="testing",
            log_level=None,
            tracing_enabled=None,
            metrics_enabled=None,
        )
        effective = config.get_effective_config()

        assert effective.log_level == "WARNING"
        assert effective.tracing_enabled is False
        assert effective.metrics_enabled is False

    def test_effective_config_type(self) -> None:
        """测试 EffectiveConfig 类型."""
        config = ObservabilityConfig(profile="development")
        effective = config.get_effective_config()

        assert isinstance(effective, EffectiveConfig)
        # Verify所有字段都存在
        assert hasattr(effective, "log_level")
        assert hasattr(effective, "tracing_enabled")
        assert hasattr(effective, "tracing_sample_rate")
        assert hasattr(effective, "metrics_enabled")
        assert hasattr(effective, "vm_endpoint")
        assert hasattr(effective, "assertions_enabled")
        assert hasattr(effective, "verbose_logging")
        assert hasattr(effective, "pytest_running")


class TestRuntimeFlags:
    """测试运行时行为标志."""

    def test_detect_runtime_flags_testing(self) -> None:
        """测试测试环境的运行时标志检测."""
        from ditto_foundation.config.environment import Environment

        flags = ObservabilityConfig.detect_runtime_flags(Environment.TESTING)
        # [REVIEW] pytest 环境中运行，pytest_running 应该是 True
        assert flags["pytest_running"] is True  # [REVIEW] pytest 中运行
        assert flags["assertions_enabled"] is True
        assert flags["verbose_logging"] is False  # [REVIEW]

    def test_detect_runtime_flags_production(self) -> None:
        """测试生产环境的运行时标志检测."""
        from ditto_foundation.config.environment import Environment

        flags = ObservabilityConfig.detect_runtime_flags(Environment.PRODUCTION)
        # [REVIEW] pytest 环境中运行，pytest_running 应该是 True
        assert flags["pytest_running"] is True  # [REVIEW] pytest 中运行
        assert flags["assertions_enabled"] is False
        assert flags["verbose_logging"] is False

    def test_detect_runtime_flags_development(self) -> None:
        """测试开发环境的运行时标志检测."""
        from ditto_foundation.config.environment import Environment

        flags = ObservabilityConfig.detect_runtime_flags(Environment.DEVELOPMENT)
        # [REVIEW] pytest 环境中运行，pytest_running 应该是 True
        assert flags["pytest_running"] is True  # [REVIEW] pytest 中运行
        assert flags["assertions_enabled"] is True
        assert flags["verbose_logging"] is True


class TestInit:
    """测试初始化."""

    def test_init_default(self) -> None:
        """测试默认初始化."""
        reset_for_testing()
        init(force=True)
        # [REVIEW]

    def test_init_with_testing_flags(self) -> None:
        """测试使用测试标志初始化."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=False,
            verbose_logging=False,
            force=True,
        )
        # [REVIEW]

    def test_init_idempotent(self) -> None:
        """测试多次初始化幂等性."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
        )  # [REVIEW](不报错)


class TestSpan:
    """测试 Span 功能."""

    def test_span_created(self) -> None:
        """测试 Span 创建."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        with span("test_operation", key="value") as s:
            assert s is not None
            s.set_attribute("extra", "data")

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_operation"
        assert spans[0].attributes.get("key") == "value"

    def test_span_attributes(self) -> None:
        """测试 Span 属性设置."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        with span("test_op", source="tushare") as s:
            s.set_attribute("rows", 100)

        spans = get_recorded_spans()
        assert spans[0].attributes.get("source") == "tushare"
        assert spans[0].attributes.get("rows") == "100"

    def test_nested_spans(self) -> None:
        """测试嵌套 Span."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        with span("parent") as parent:
            with span("child") as child:
                assert parent is not None
                assert child is not None

        spans = get_recorded_spans()
        assert len(spans) == 2
        assert spans[0].name == "child"
        assert spans[1].name == "parent"

    def test_span_records_exception(self) -> None:
        """测试 Span 记录异常."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        with pytest.raises(ValueError, match="test error"):
            with span("test_operation"):
                raise ValueError("test error")

        spans = get_recorded_spans()
        assert len(spans) == 1
        # [REVIEW]

    def test_traced_decorator(self) -> None:
        """测试 @traced 装饰器."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

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
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

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
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        with span("test_op"):
            span_id = get_span_id()

        # 16位十六进制
        hex_pattern = re.compile(r"^[0-9a-f]{16}$", re.IGNORECASE)
        assert span_id is not None
        assert hex_pattern.match(span_id) is not None

    def test_trace_id_consistency(self) -> None:
        """测试同一 trace 中 trace_id 一致."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

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
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        M.data_records.add(
            100, {"source": "test", "table": "test", "status": "success"}
        )

        # [REVIEW]
        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

    def test_gauge_set(self) -> None:
        """测试 Gauge 设置."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        M.kill_switch_level.set(2.0)

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None

    def test_histogram_record(self) -> None:
        """测试 Histogram 记录."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        M.data_update_duration.record(1.5, {"source": "test", "table": "test"})

        metrics_data = get_recorded_metrics()
        assert metrics_data is not None


class TestLogging:
    """测试日志功能."""

    def test_logger_with_event_field(self) -> None:
        """测试带 event 字段的日志."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        # [REVIEW]
        logger.info("Test message", event="test_event", key="value")

    def test_logger_with_trace_id_context(self) -> None:
        """测试带 trace_id 上下文的日志."""
        reset_for_testing()
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

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
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )

        with span("test_op") as s:
            assert s is not None

        spans = get_recorded_spans()
        assert len(spans) == 1

        reset_for_testing()

        spans = get_recorded_spans()
        assert len(spans) == 0


class TestResolveLogDir:
    """测试日志目录解析功能."""

    def test_resolve_log_dir_default_uses_xdg_paths(self) -> None:
        """测试默认 'logs' 使用 XDGPaths."""
        from ditto_foundation.observability.config import ObservabilityConfig
        from ditto_foundation.observability.logging import _resolve_log_dir

        config = ObservabilityConfig(log_dir="logs")
        log_dir = _resolve_log_dir(config)

        # [REVIEW] XDGPaths 的 state_subdir
        # [REVIEW] "logs"
        assert log_dir.name == "logs" or "logs" in log_dir.parts

    def test_resolve_log_dir_custom_path(self) -> None:
        """测试自定义路径."""
        import tempfile

        from ditto_foundation.observability.config import ObservabilityConfig
        from ditto_foundation.observability.logging import _resolve_log_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ObservabilityConfig(log_dir=tmpdir)
            log_dir = _resolve_log_dir(config)

            assert str(log_dir) == tmpdir
            assert log_dir.exists()

    def test_resolve_log_dir_creates_directory(self) -> None:
        """测试自动创建目录."""
        import tempfile

        from ditto_foundation.observability.config import ObservabilityConfig
        from ditto_foundation.observability.logging import _resolve_log_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = f"{tmpdir}/custom/nested/logs"
            config = ObservabilityConfig(log_dir=custom_path)
            log_dir = _resolve_log_dir(config)

            assert log_dir.exists()
            assert log_dir.is_dir()
