"""Ditto 观测模块。"""

from __future__ import annotations

from ._lifecycle import init, shutdown
from .config import EffectiveConfig, ObservabilityConfig
from .logging import logger
from .metrics import Metrics
from .tracing import (
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
    """延迟导入 testing 模块和内部注册表，避免循环依赖。"""
    if name in ("get_recorded_metrics", "get_recorded_spans", "reset_for_testing"):
        from . import testing  # noqa: PLC0415

        return getattr(testing, name)
    if name == "_ObservabilityRegistry":
        from ._registry import ObservabilityRegistry  # noqa: PLC0415

        return ObservabilityRegistry
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
