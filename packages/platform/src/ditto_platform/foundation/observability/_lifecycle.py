"""观测系统生命周期管理（初始化 + 关闭）。"""

from __future__ import annotations

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace

from ._registry import (
    get_config as _get_config,
)
from ._registry import (
    is_initialized as _is_initialized,
)
from ._registry import (
    reset as _reset,
)
from ._registry import (
    set_config as _set_config,
)
from ._registry import (
    set_initialized as _set_initialized,
)
from .config import ObservabilityConfig
from .logging import configure_logging, logger
from .metrics import configure_metrics
from .tracing import configure_tracing


def init(config: ObservabilityConfig, *, force: bool = False) -> None:
    """初始化观测系统（显式配置）。"""
    if _is_initialized() and not force:
        stored = _get_config()
        if stored and stored != config:
            msg = "Observability already initialized with different config"
            raise RuntimeError(msg)
        return

    _set_config(config)

    configure_logging(config)
    configure_tracing(config)
    configure_metrics(config)

    effective = config.get_effective_config()
    if effective.verbose_logging:
        logger.info(
            "Observability initialized",
            event="observability_init",
            service=config.service_name,
            environment=config.environment.value,
        )

    _set_initialized(True)


def shutdown() -> None:
    """优雅关闭，刷新待处理数据。"""
    try:
        for provider in [
            otel_trace.get_tracer_provider(),
            otel_metrics.get_meter_provider(),
        ]:
            if hasattr(provider, "shutdown"):
                provider.shutdown()
    except Exception as e:
        logger.debug(
            "Graceful shutdown completed with warnings",
            error=str(e),
        )

    _reset()
