"""指标模块公共 API。"""

from __future__ import annotations

from ._binding import (
    Metrics,
    configure_metrics,
    get_in_memory_reader,
    register_metric_definitions,
    reset_metrics,
)
from ._types import SafeCounter, SafeGauge, SafeHistogram

__all__ = [
    "Metrics",
    "SafeCounter",
    "SafeGauge",
    "SafeHistogram",
    "configure_metrics",
    "get_in_memory_reader",
    "register_metric_definitions",
    "reset_metrics",
]


# 延迟导出内部符号，仅供测试访问内部状态。
def __getattr__(name: str) -> object:
    """延迟导出内部符号，供测试使用。"""
    if name == "_MetricsRegistry":
        from ._registry import _MetricsRegistry  # noqa: PLC0415

        return _MetricsRegistry
    if name == "METRIC_DEFINITIONS":
        from ._types import METRIC_DEFINITIONS  # noqa: PLC0415

        return METRIC_DEFINITIONS
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
