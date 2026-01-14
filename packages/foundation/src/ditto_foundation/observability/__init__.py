"""
Ditto 可观测性模块.

提供统一的日志、追踪和指标接口，支持多种运行模式.

使用示例:
    >>> from ditto_foundation import init, logger, span, traced, M
    >>>
    >>> # 初始化
    >>> init()
    >>>
    >>> # 日志
    >>> logger.info("Starting backtest", strategy="etf_rotation")
    >>>
    >>> # 追踪
    >>> @traced("backtest.run")
    >>> def run_backtest():
    >>>     with span("data.load"):
    >>>         data = load_data()
    >>>     return data
    >>>
    >>> # 指标
    >>> M.data_records.add(100, {"source": "tushare", "table": "etf_daily"})
"""

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace

from .config import Mode, ObservabilityConfig
from .logging import configure_logging, logger
from .metrics import M, configure_metrics
from .testing import get_recorded_metrics, get_recorded_spans, reset_for_testing
from .tracing import (
    configure_tracing,
    get_span_id,
    get_trace_id,
    span,
    traced,
)

__all__ = [
    "M",
    "Mode",
    "ObservabilityConfig",
    "get_recorded_metrics",
    "get_recorded_spans",
    "get_span_id",
    "get_trace_id",
    "init",
    "logger",
    "reset_for_testing",
    "shutdown",
    "span",
    "traced",
]

_initialized: bool = False


def init(
    service_name: str = "ditto",
    environment: str = "dev",
    log_level: str = "INFO",
    log_dir: str = "logs",
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics",
    mode: Mode | None = None,
    force: bool = False,
) -> None:
    """
    一键初始化所有可观测性组件.

    Args:
    ----
        service_name: 服务名称
        environment: 环境名称（dev, production）
        log_level: 日志级别
        log_dir: 日志目录
        vm_endpoint: VictoriaMetrics OTLP 端点
        mode: 运行模式，None 表示自动检测
        force: 强制重新初始化（用于测试）

    """
    global _initialized  # noqa: PLW0603

    if _initialized and not force:
        return

    config = ObservabilityConfig(
        service_name=service_name,
        environment=environment,
        log_level=log_level,
        log_dir=log_dir,
        vm_endpoint=vm_endpoint,
    )

    actual_mode = mode or config.detect_mode()

    # 配置日志
    configure_logging(config, actual_mode)

    # 配置追踪
    configure_tracing(config, actual_mode)

    # 配置指标
    configure_metrics(config, actual_mode)

    # 记录初始化日志
    if not actual_mode.is_silent():
        logger.info(
            "Observability initialized",
            event="observability_init",
            service=service_name,
            environment=environment,
            mode=actual_mode.value,
        )

    _initialized = True


def shutdown() -> None:
    """优雅关闭，刷新所有待处理数据."""
    # 注意：OpenTelemetry providers shutdown 后无法重新初始化
    # 测试环境中应使用 reset_for_testing() 而非 shutdown()
    try:
        for provider in [
            otel_trace.get_tracer_provider(),
            otel_metrics.get_meter_provider(),
        ]:
            if hasattr(provider, "shutdown") and not hasattr(provider, "_shutdown"):
                provider.shutdown()
    except Exception:  # noqa: S110
        # 静默忽略：优雅关闭失败不应抛出异常
        pass

    global _initialized  # noqa: PLW0603
    _initialized = False
