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

from ditto_foundation.config.environment import Environment

from .config import EffectiveConfig, ObservabilityConfig
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
    "EffectiveConfig",
    "M",
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


class _ObservabilityRegistry:
    """
    Registry for managing observability initialization state.

    Uses class-level attributes to store singleton state, eliminating
    the need for global statements while maintaining the same API.
    """

    initialized: bool = False

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if observability has been initialized."""
        return cls.initialized

    @classmethod
    def set_initialized(cls, value: bool) -> None:
        """Set the initialization state."""
        cls.initialized = value

    @classmethod
    def reset(cls) -> None:
        """Reset the initialization state (for testing purposes)."""
        cls.initialized = False


def init(  # noqa: PLR0913
    service_name: str = "ditto",
    environment: str = "dev",
    log_level: str = "INFO",
    log_dir: str = "logs",
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics",
    pytest_running: bool = False,
    assertions_enabled: bool = True,
    verbose_logging: bool = True,
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
        pytest_running: 是否在 pytest 中运行
        assertions_enabled: 是否启用断言
        verbose_logging: 是否启用详细日志
        force: 强制重新初始化（用于测试）

    """
    if _ObservabilityRegistry.is_initialized() and not force:
        return

    # 转换 environment 字符串为 Environment 枚举
    # 支持简写: dev -> development, prod -> production
    env_mapping = {
        "dev": "development",
        "development": "development",
        "test": "testing",
        "testing": "testing",
        "prod": "production",
        "production": "production",
    }
    normalized_env = env_mapping.get(environment.lower(), "development")
    env_enum = Environment.from_str(normalized_env)

    config = ObservabilityConfig(
        service_name=service_name,
        environment=env_enum,
        log_level=log_level,
        log_dir=log_dir,
        vm_endpoint=vm_endpoint,
        pytest_running=pytest_running,
        assertions_enabled=assertions_enabled,
        verbose_logging=verbose_logging,
    )

    # 配置日志
    configure_logging(config)

    # 配置追踪
    configure_tracing(config)

    # 配置指标
    configure_metrics(config)

    # 记录初始化日志
    if verbose_logging:
        logger.info(
            "Observability initialized",
            event="observability_init",
            service=service_name,
            environment=environment,
        )

    _ObservabilityRegistry.set_initialized(True)


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
    except Exception as e:
        # 优雅关闭失败不应抛出异常，但应记录日志用于调试
        logger.debug(f"Graceful shutdown completed with warnings: {e}")

    _ObservabilityRegistry.set_initialized(False)
