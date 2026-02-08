"""指标模块."""

from __future__ import annotations

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
        "name": "data_update_duration",
        "instrument_name": "ditto.data.update.duration",
        "type": "histogram",
        "description": "Data update operation duration in seconds",
    },
    {
        "name": "data_records",
        "instrument_name": "ditto.data.records_total",
        "type": "counter",
        "description": "Total data records processed",
    },
    {
        "name": "data_freshness",
        "instrument_name": "ditto.data.freshness_days",
        "type": "gauge",
        "description": "Data freshness in days since last update",
    },
    {
        "name": "data_errors",
        "instrument_name": "ditto.data.errors_total",
        "type": "counter",
        "description": "Total data processing errors",
    },
    {
        "name": "factor_calc_duration",
        "instrument_name": "ditto.factor.calc.duration",
        "type": "histogram",
        "description": "Factor calculation duration in seconds",
    },
    {
        "name": "factor_ic",
        "instrument_name": "ditto.factor.ic",
        "type": "gauge",
        "description": "Factor Information Coefficient (IC)",
    },
    {
        "name": "factor_health",
        "instrument_name": "ditto.factor.health",
        "type": "gauge",
        "description": "Factor health score (0-100)",
    },
    {
        "name": "signal_total",
        "instrument_name": "ditto.signal.total",
        "type": "counter",
        "description": "Total trading signals generated",
    },
    {
        "name": "rebalance_total",
        "instrument_name": "ditto.rebalance.total",
        "type": "counter",
        "description": "Total portfolio rebalances executed",
    },
    {
        "name": "portfolio_value",
        "instrument_name": "ditto.portfolio.value",
        "type": "gauge",
        "description": "Current portfolio value",
    },
    {
        "name": "portfolio_drawdown",
        "instrument_name": "ditto.portfolio.drawdown",
        "type": "gauge",
        "description": "Current portfolio drawdown",
    },
    {
        "name": "portfolio_drawdown_3d",
        "instrument_name": "ditto.portfolio.drawdown_3d",
        "type": "gauge",
        "description": "3-day rolling portfolio drawdown",
    },
    {
        "name": "kill_switch_level",
        "instrument_name": "ditto.risk.kill_switch_level",
        "type": "gauge",
        "description": "Current kill switch level (0-3)",
    },
    {
        "name": "kill_switch_total",
        "instrument_name": "ditto.risk.kill_switch_total",
        "type": "counter",
        "description": "Total kill switch triggers",
    },
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
    {
        "name": "dq_batch_checks",
        "instrument_name": "ditto.dq.batch.checks_total",
        "type": "counter",
        "description": "Total DQ batch checks executed",
    },
    {
        "name": "dq_batch_issues",
        "instrument_name": "ditto.dq.batch.issues_total",
        "type": "counter",
        "description": "Total DQ batch issues found",
    },
    {
        "name": "dq_batch_alerts",
        "instrument_name": "ditto.dq.batch.alerts_total",
        "type": "counter",
        "description": "Total DQ batch alerts generated",
    },
]


class SimpleGauge:
    def __init__(self, meter: metrics.Meter, name: str, description: str) -> None:
        self._value = 0.0

        def callback(options: Any) -> list[metrics.Observation]:
            return [metrics.Observation(self._value, {})]

        self._gauge = meter.create_observable_gauge(
            name,
            [callback],
            description=description,
        )

    def set(self, value: float) -> None:
        self._value = value

    def inc(self, delta: float = 1.0) -> None:
        self._value = max(0.0, self._value + delta)

    def dec(self, delta: float = 1.0) -> None:
        self._value = max(0.0, self._value - delta)


class M:
    """指标入口（绑定全局 Meter 后可直接使用）。"""

    data_update_duration: Histogram
    data_records: Counter
    data_freshness: SimpleGauge
    data_errors: Counter

    factor_calc_duration: Histogram
    factor_ic: SimpleGauge
    factor_health: SimpleGauge

    signal_total: Counter
    rebalance_total: Counter

    portfolio_value: SimpleGauge
    portfolio_drawdown: SimpleGauge
    portfolio_drawdown_3d: SimpleGauge

    kill_switch_level: SimpleGauge
    kill_switch_total: Counter

    scheduler_jobs: Counter
    api_requests: Counter
    api_duration: Histogram

    cache_hit: Counter
    cache_miss: Counter
    cache_hit_rate: SimpleGauge
    cache_invalidations: Counter
    cache_evictions: Counter
    cache_size: SimpleGauge

    sql_query_duration: Histogram
    sql_slow_query_total: Counter
    sql_query_plan_cache_hit: Counter
    sql_query_plan_cache_miss: Counter

    json_serialize_duration: Histogram
    json_deserialize_duration: Histogram
    json_bytes_total: Counter

    dq_batch_checks: Counter
    dq_batch_issues: Counter
    dq_batch_alerts: Counter

    @classmethod
    def setup(cls, meter: metrics.Meter) -> None:
        """基于 Meter 初始化指标对象。"""
        for metric_def in METRIC_DEFINITIONS:
            metric_type = metric_def["type"]
            name = metric_def["name"]
            instrument_name = metric_def["instrument_name"]
            description = metric_def["description"]

            if metric_type == "histogram":
                setattr(
                    cls,
                    name,
                    meter.create_histogram(instrument_name, description=description),
                )
            elif metric_type == "counter":
                setattr(
                    cls,
                    name,
                    meter.create_counter(instrument_name, description=description),
                )
            elif metric_type == "gauge":
                setattr(cls, name, _create_gauge(meter, instrument_name, description))
            else:
                raise ValueError(f"Unknown metric type: {metric_type}")


def _create_gauge(
    meter: metrics.Meter,
    name: str,
    description: str,
) -> SimpleGauge:
    return SimpleGauge(meter, name, description)


def configure_metrics(config: ObservabilityConfig) -> metrics.Meter:
    """配置并返回 Metrics Meter。"""
    effective = config.get_effective_config()

    resource = Resource.create({"service.name": config.service_name})

    if not effective.metrics_enabled:
        provider = MeterProvider(resource=resource)
        metrics.set_meter_provider(provider)
        meter = provider.get_meter(config.service_name)
        _MetricsRegistry.set_meter(meter)
        M.setup(meter)
        return meter

    duration_histogram_aggregation = ExplicitBucketHistogramAggregation(
        boundaries=_HISTOGRAM_BUCKETS,
    )
    duration_histogram_names = [
        m["instrument_name"] for m in METRIC_DEFINITIONS if m["type"] == "histogram"
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
        M.setup(meter)
        return meter

    if effective.metrics_exporter == "none":
        provider = MeterProvider(resource=resource, views=duration_histogram_views)
        metrics.set_meter_provider(provider)
        meter = metrics.get_meter(config.service_name)
        _MetricsRegistry.set_meter(meter)
        M.setup(meter)
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
    M.setup(meter)

    return meter


def reset_metrics() -> None:
    """重置 Metrics 注册表。"""
    _MetricsRegistry.reset()


def get_in_memory_reader() -> InMemoryMetricReader | None:
    """获取内存 Metric reader（用于测试）。"""
    return _MetricsRegistry.get_in_memory_reader()


__all__ = [
    "M",
    "configure_metrics",
    "get_in_memory_reader",
    "reset_metrics",
]
