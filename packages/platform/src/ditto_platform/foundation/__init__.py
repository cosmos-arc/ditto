"""
Ditto 共享模块.

提供跨项目的共享类型、配置和工具。
"""

from ditto_platform.foundation.db import SQLitePool
from ditto_platform.foundation.observability import (
    EffectiveConfig,
    Metrics,
    ObservabilityConfig,
    get_recorded_metrics,
    get_recorded_spans,
    get_span_id,
    get_trace_id,
    init,
    logger,
    reset_for_testing,
    shutdown,
    span,
    traced,
)

__all__ = [
    "EffectiveConfig",
    "Metrics",
    "ObservabilityConfig",
    "SQLitePool",
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
