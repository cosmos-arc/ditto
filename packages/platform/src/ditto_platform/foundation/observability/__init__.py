"""Ditto 观测模块。"""

from __future__ import annotations

from ._lifecycle import init, shutdown
from .config import EffectiveConfig, ObservabilityConfig
from .logging import logger
from .metrics import (
    Metrics,
    SafeCounter,
    SafeGauge,
    SafeHistogram,
    register_metric_definitions,
)
from .testing import get_recorded_metrics, get_recorded_spans, reset_for_testing
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
    "SafeCounter",
    "SafeGauge",
    "SafeHistogram",
    "get_recorded_metrics",
    "get_recorded_spans",
    "get_span_id",
    "get_trace_id",
    "init",
    "logger",
    "register_metric_definitions",
    "reset_for_testing",
    "shutdown",
    "span",
    "traced",
]
