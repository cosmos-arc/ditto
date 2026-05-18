"""指标类型定义和安全包装器。"""

from __future__ import annotations

from typing import Any, TypedDict

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram

__all__ = [
    "METRIC_DEFINITIONS",
    "MetricDefinition",
    "SafeCounter",
    "SafeGauge",
    "SafeHistogram",
    "_new_noop_wrapper",
]


class MetricDefinition(TypedDict):
    name: str
    instrument_name: str
    type: str
    description: str


METRIC_DEFINITIONS: list[MetricDefinition] = [
    {
        "name": "scheduler_jobs",
        "instrument_name": "ditto.scheduler.jobs_total",
        "type": "counter",
        "description": "Total scheduler jobs executed",
    },
    {
        "name": "api_requests",
        "instrument_name": "ditto.api.requests_total",
        "type": "counter",
        "description": "Total API requests",
    },
    {
        "name": "api_duration",
        "instrument_name": "ditto.api.duration",
        "type": "histogram",
        "description": "API request duration in seconds",
    },
    {
        "name": "cache_hit",
        "instrument_name": "ditto.cache.hit_total",
        "type": "counter",
        "description": "Total cache hits",
    },
    {
        "name": "cache_miss",
        "instrument_name": "ditto.cache.miss_total",
        "type": "counter",
        "description": "Total cache misses",
    },
    {
        "name": "cache_hit_rate",
        "instrument_name": "ditto.cache.hit_rate",
        "type": "gauge",
        "description": "Cache hit rate (0-1)",
    },
    {
        "name": "cache_invalidations",
        "instrument_name": "ditto.cache.invalidations_total",
        "type": "counter",
        "description": "Total cache invalidations",
    },
    {
        "name": "cache_evictions",
        "instrument_name": "ditto.cache.evictions_total",
        "type": "counter",
        "description": "Total cache evictions",
    },
    {
        "name": "cache_size",
        "instrument_name": "ditto.cache.size",
        "type": "gauge",
        "description": "Current cache size (number of entries)",
    },
    {
        "name": "sql_query_duration",
        "instrument_name": "ditto.sql.query.duration",
        "type": "histogram",
        "description": "SQL query execution duration in seconds",
    },
    {
        "name": "sql_slow_query_total",
        "instrument_name": "ditto.sql.slow_query_total",
        "type": "counter",
        "description": "Total slow queries",
    },
    {
        "name": "sql_query_plan_cache_hit",
        "instrument_name": "ditto.sql.query_plan_cache.hit_total",
        "type": "counter",
        "description": "Total query plan cache hits",
    },
    {
        "name": "sql_query_plan_cache_miss",
        "instrument_name": "ditto.sql.query_plan_cache.miss_total",
        "type": "counter",
        "description": "Total query plan cache misses",
    },
    {
        "name": "json_serialize_duration",
        "instrument_name": "ditto.json.serialize.duration",
        "type": "histogram",
        "description": "JSON serialization duration in seconds",
    },
    {
        "name": "json_deserialize_duration",
        "instrument_name": "ditto.json.deserialize.duration",
        "type": "histogram",
        "description": "JSON deserialization duration in seconds",
    },
    {
        "name": "json_bytes_total",
        "instrument_name": "ditto.json.bytes_total",
        "type": "counter",
        "description": "Total JSON bytes processed",
    },
]


class SafeCounter:
    """防御式 Counter，未初始化时静默跳过。"""

    def __init__(self, counter: Counter | None = None) -> None:
        self._counter = counter

    def add(
        self, amount: int | float, attributes: dict[str, Any] | None = None
    ) -> None:
        """记录计数，未初始化时静默跳过。"""
        if self._counter is not None:
            self._counter.add(amount, attributes or {})

    def set_counter(self, counter: Counter) -> None:
        """设置实际的 Counter（setup 时调用）。"""
        self._counter = counter


class SafeHistogram:
    """防御式 Histogram，未初始化时静默跳过。"""

    def __init__(self, histogram: Histogram | None = None) -> None:
        self._histogram = histogram

    def record(
        self, amount: int | float, attributes: dict[str, Any] | None = None
    ) -> None:
        """记录直方图值，未初始化时静默跳过。"""
        if self._histogram is not None:
            self._histogram.record(amount, attributes or {})

    def set_histogram(self, histogram: Histogram) -> None:
        """设置实际的 Histogram（setup 时调用）。"""
        self._histogram = histogram


class SafeGauge:
    """防御式 Gauge，未初始化时静默跳过。"""

    def __init__(self) -> None:
        self._value = 0.0
        self._gauge: Any = None

    def set(self, value: float) -> None:
        """设置 Gauge 值。"""
        self._value = value

    def inc(self, delta: float = 1.0) -> None:
        """增加 Gauge 值。"""
        self._value = max(0.0, self._value + delta)

    def dec(self, delta: float = 1.0) -> None:
        """减少 Gauge 值。"""
        self._value = max(0.0, self._value - delta)

    def _callback(self, options: object) -> list[metrics.Observation]:
        """ObservableGauge 回调函数。"""
        return [metrics.Observation(self._value, {})]

    def set_gauge(self, meter: metrics.Meter, name: str, description: str) -> None:
        """设置实际的 Gauge（setup 时调用）。"""
        self._gauge = meter.create_observable_gauge(
            name,
            [self._callback],
            description=description,
        )


def _new_noop_wrapper(metric_def: MetricDefinition) -> object:
    metric_type = metric_def["type"]
    if metric_type == "histogram":
        return SafeHistogram()
    if metric_type == "counter":
        return SafeCounter()
    if metric_type == "gauge":
        return SafeGauge()
    raise ValueError(f"Unknown metric type: {metric_type}")
