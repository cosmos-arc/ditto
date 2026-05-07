"""指标模块."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TypedDict

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

from .config import ObservabilityConfig


class _MetricsRegistry:
    meter: metrics.Meter | None = None
    in_memory_reader: InMemoryMetricReader | None = None

    @classmethod
    def get_meter(cls) -> metrics.Meter | None:
        return cls.meter

    @classmethod
    def get_in_memory_reader(cls) -> InMemoryMetricReader | None:
        return cls.in_memory_reader

    @classmethod
    def set_meter(cls, meter: metrics.Meter) -> None:
        cls.meter = meter

    @classmethod
    def set_in_memory_reader(cls, reader: InMemoryMetricReader) -> None:
        cls.in_memory_reader = reader

    @classmethod
    def reset(cls) -> None:
        cls.meter = None
        cls.in_memory_reader = None


_HISTOGRAM_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0)


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

_REGISTERED_METRIC_DEFINITIONS: dict[str, MetricDefinition] = {}
_REGISTERED_METRIC_NAMES: dict[str, MetricDefinition] = {}


def _all_metric_definitions() -> list[MetricDefinition]:
    return [*METRIC_DEFINITIONS, *_REGISTERED_METRIC_DEFINITIONS.values()]


def _normalize_metric_definition(
    definition: MetricDefinition | Mapping[str, str],
) -> MetricDefinition:
    return {
        "name": definition["name"],
        "instrument_name": definition["instrument_name"],
        "type": definition["type"],
        "description": definition["description"],
    }


def _platform_definitions_by_instrument() -> dict[str, MetricDefinition]:
    return {
        definition["instrument_name"]: definition for definition in METRIC_DEFINITIONS
    }


def _platform_definitions_by_name() -> dict[str, MetricDefinition]:
    return {definition["name"]: definition for definition in METRIC_DEFINITIONS}


def _check_duplicate_metric_definition(metric_def: MetricDefinition) -> bool:
    instrument_name = metric_def["instrument_name"]
    name = metric_def["name"]

    by_instrument = {
        **_platform_definitions_by_instrument(),
        **_REGISTERED_METRIC_DEFINITIONS,
    }
    by_name = {
        **_platform_definitions_by_name(),
        **_REGISTERED_METRIC_NAMES,
    }

    if existing := by_instrument.get(instrument_name):
        if existing != metric_def:
            msg = (
                f"Metric instrument {instrument_name!r} already registered with "
                f"different definition {existing!r}"
            )
            raise ValueError(msg)
        return True

    if existing := by_name.get(name):
        msg = (
            f"Metric name {name!r} already registered for instrument "
            f"{existing['instrument_name']!r}"
        )
        raise ValueError(msg)

    return False


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


class _MetricsMeta(type):
    def __getattr__(cls, name: str) -> Any:  # noqa: ANN401
        definition = _REGISTERED_METRIC_NAMES.get(name)
        if definition is None:
            msg = f"type object {cls.__name__!r} has no attribute {name!r}"
            raise AttributeError(msg)
        return cls.ensure_definition(definition)


class Metrics(metaclass=_MetricsMeta):
    """
    指标入口（绑定全局 Meter 后可直接使用）。

    使用防御式包装器，未初始化时静默跳过。
    """

    scheduler_jobs: SafeCounter = SafeCounter()
    api_requests: SafeCounter = SafeCounter()
    api_duration: SafeHistogram = SafeHistogram()

    cache_hit: SafeCounter = SafeCounter()
    cache_miss: SafeCounter = SafeCounter()
    cache_hit_rate: SafeGauge = SafeGauge()
    cache_invalidations: SafeCounter = SafeCounter()
    cache_evictions: SafeCounter = SafeCounter()
    cache_size: SafeGauge = SafeGauge()

    sql_query_duration: SafeHistogram = SafeHistogram()
    sql_slow_query_total: SafeCounter = SafeCounter()
    sql_query_plan_cache_hit: SafeCounter = SafeCounter()
    sql_query_plan_cache_miss: SafeCounter = SafeCounter()

    json_serialize_duration: SafeHistogram = SafeHistogram()
    json_deserialize_duration: SafeHistogram = SafeHistogram()
    json_bytes_total: SafeCounter = SafeCounter()

    @classmethod
    def setup(cls, meter: metrics.Meter) -> None:
        """基于 Meter 初始化指标对象。"""
        for metric_def in _all_metric_definitions():
            cls.setup_definition(meter, metric_def)

    @classmethod
    def setup_definition(
        cls, meter: metrics.Meter, metric_def: MetricDefinition
    ) -> None:
        """基于 Meter 初始化单个指标对象。"""
        metric_type = metric_def["type"]
        name = metric_def["name"]
        instrument_name = metric_def["instrument_name"]
        description = metric_def["description"]

        if metric_type == "histogram":
            histogram = meter.create_histogram(instrument_name, description=description)
            wrapper = cls._ensure_histogram(name)
            wrapper.set_histogram(histogram)
        elif metric_type == "counter":
            counter = meter.create_counter(instrument_name, description=description)
            wrapper = cls._ensure_counter(name)
            wrapper.set_counter(counter)
        elif metric_type == "gauge":
            wrapper = cls._ensure_gauge(name)
            wrapper.set_gauge(meter, instrument_name, description)
        else:
            raise ValueError(f"Unknown metric type: {metric_type}")

    @classmethod
    def ensure_definition(cls, metric_def: MetricDefinition) -> object:
        """创建指标安全包装器；未绑定 Meter 时保持 no-op。"""
        metric_type = metric_def["type"]
        name = metric_def["name"]

        if metric_type == "histogram":
            return cls._ensure_histogram(name)
        if metric_type == "counter":
            return cls._ensure_counter(name)
        if metric_type == "gauge":
            return cls._ensure_gauge(name)
        raise ValueError(f"Unknown metric type: {metric_type}")

    @classmethod
    def _ensure_counter(cls, name: str) -> SafeCounter:
        existing = cls.__dict__.get(name)
        if isinstance(existing, SafeCounter):
            return existing
        wrapper = SafeCounter()
        setattr(cls, name, wrapper)
        return wrapper

    @classmethod
    def _ensure_histogram(cls, name: str) -> SafeHistogram:
        existing = cls.__dict__.get(name)
        if isinstance(existing, SafeHistogram):
            return existing
        wrapper = SafeHistogram()
        setattr(cls, name, wrapper)
        return wrapper

    @classmethod
    def _ensure_gauge(cls, name: str) -> SafeGauge:
        existing = cls.__dict__.get(name)
        if isinstance(existing, SafeGauge):
            return existing
        wrapper = SafeGauge()
        setattr(cls, name, wrapper)
        return wrapper

    @classmethod
    def reset_wrappers(cls, external_names: Iterable[str]) -> None:
        """重置平台 wrapper，并移除外部动态指标 wrapper。"""
        for metric_def in METRIC_DEFINITIONS:
            setattr(cls, metric_def["name"], _new_noop_wrapper(metric_def))

        platform_names = {definition["name"] for definition in METRIC_DEFINITIONS}
        for name in external_names:
            if name not in platform_names and name in cls.__dict__:
                delattr(cls, name)


def _new_noop_wrapper(metric_def: MetricDefinition) -> object:
    metric_type = metric_def["type"]
    if metric_type == "histogram":
        return SafeHistogram()
    if metric_type == "counter":
        return SafeCounter()
    if metric_type == "gauge":
        return SafeGauge()
    raise ValueError(f"Unknown metric type: {metric_type}")


def register_metric_definitions(
    definitions: Iterable[MetricDefinition | Mapping[str, str]],
) -> None:
    """注册外部指标定义，并在 Meter 已存在时立即绑定。"""
    meter = _MetricsRegistry.get_meter()
    for definition in definitions:
        metric_def = _normalize_metric_definition(definition)
        if _check_duplicate_metric_definition(metric_def):
            continue
        if meter is not None and metric_def["type"] == "histogram":
            msg = (
                "Histogram metric definitions must be registered before "
                "configure_metrics() so their custom bucket views are installed"
            )
            raise RuntimeError(msg)
        instrument_name = metric_def["instrument_name"]
        _REGISTERED_METRIC_DEFINITIONS[instrument_name] = metric_def
        _REGISTERED_METRIC_NAMES[metric_def["name"]] = metric_def
        Metrics.ensure_definition(metric_def)
        if meter is not None:
            Metrics.setup_definition(meter, metric_def)


def configure_metrics(config: ObservabilityConfig) -> metrics.Meter:
    """配置并返回 Metrics Meter。"""
    effective = config.get_effective_config()

    resource = Resource.create({"service.name": config.service_name})

    if not effective.metrics_enabled:
        provider = MeterProvider(resource=resource)
        metrics.set_meter_provider(provider)
        meter = provider.get_meter(config.service_name)
        _MetricsRegistry.set_meter(meter)
        Metrics.setup(meter)
        return meter

    duration_histogram_aggregation = ExplicitBucketHistogramAggregation(
        boundaries=_HISTOGRAM_BUCKETS,
    )
    duration_histogram_names = [
        m["instrument_name"]
        for m in _all_metric_definitions()
        if m["type"] == "histogram"
    ]
    duration_histogram_views = [
        View(
            instrument_type=Histogram,
            instrument_name=name,
            aggregation=duration_histogram_aggregation,
        )
        for name in duration_histogram_names
    ]

    if config.environment.is_testing or effective.pytest_running:
        in_memory_reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[in_memory_reader],
            resource=resource,
            views=duration_histogram_views,
        )
        meter = provider.get_meter(__name__)
        _MetricsRegistry.set_meter(meter)
        _MetricsRegistry.set_in_memory_reader(in_memory_reader)
        Metrics.setup(meter)
        return meter

    if effective.metrics_exporter == "none":
        provider = MeterProvider(resource=resource, views=duration_histogram_views)
        metrics.set_meter_provider(provider)
        meter = metrics.get_meter(config.service_name)
        _MetricsRegistry.set_meter(meter)
        Metrics.setup(meter)
        return meter

    otlp_exporter = OTLPMetricExporter(
        endpoint=effective.vm_endpoint,
        timeout=30,
    )
    period_exporter = PeriodicExportingMetricReader(
        otlp_exporter,
        export_interval_millis=config.metrics_export_interval_ms,
    )
    provider = MeterProvider(
        metric_readers=[period_exporter],
        resource=resource,
        views=duration_histogram_views,
    )
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter(config.service_name)
    _MetricsRegistry.set_meter(meter)
    Metrics.setup(meter)

    return meter


def reset_metrics() -> None:
    """重置 Metrics 注册表和外部指标目录。"""
    _MetricsRegistry.reset()
    Metrics.reset_wrappers(_REGISTERED_METRIC_NAMES)
    _REGISTERED_METRIC_DEFINITIONS.clear()
    _REGISTERED_METRIC_NAMES.clear()


def get_in_memory_reader() -> InMemoryMetricReader | None:
    """获取内存 Metric reader（用于测试）。"""
    return _MetricsRegistry.get_in_memory_reader()


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
