"""Ditto 观测模块。"""

from __future__ import annotations

from dataclasses import dataclass

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace

from .config import EffectiveConfig, ObservabilityConfig
from .logging import configure_logging, logger
from .metrics import Metrics, configure_metrics
from .tracing import (
    configure_tracing,
    get_span_id,
    get_trace_id,
    span,
    traced,
)

__all__ = [
    "EffectiveConfig",
    "Metrics",
    "ObservabilityConfig",
    "get_span_id",
    "get_trace_id",
    "init",
    "logger",
    "shutdown",
    "span",
    "traced",
]


def __getattr__(name: str) -> object:
    """延迟导入 testing 模块，避免循环依赖。"""
    if name in ("get_recorded_metrics", "get_recorded_spans", "reset_for_testing"):
        from . import testing  # noqa: PLC0415

        return getattr(testing, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


@dataclass
class _ObservabilityRegistry:
    initialized: bool = False
    config: ObservabilityConfig | None = None

    @classmethod
    def is_initialized(cls) -> bool:
        return cls.initialized

    @classmethod
    def set_initialized(cls, value: bool) -> None:
        cls.initialized = value

    @classmethod
    def set_config(cls, config: ObservabilityConfig) -> None:
        cls.config = config

    @classmethod
    def reset(cls) -> None:
        cls.initialized = False
        cls.config = None


def init(config: ObservabilityConfig, *, force: bool = False) -> None:
    """初始化观测系统（显式配置）。"""
    if _ObservabilityRegistry.is_initialized() and not force:
        if _ObservabilityRegistry.config and _ObservabilityRegistry.config != config:
            msg = "Observability already initialized with different config"
            raise RuntimeError(msg)
        return

    _ObservabilityRegistry.set_config(config)

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

    _ObservabilityRegistry.set_initialized(True)


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
        logger.debug(f"Graceful shutdown completed with warnings: {e}")

    _ObservabilityRegistry.reset()
