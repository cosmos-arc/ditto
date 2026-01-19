"""
指标模块.

基于 OpenTelemetry 的指标收集，定义所有预定义业务指标.

Histogram Buckets 配置 (秒):
    [0.1, 0.5, 1, 5, 10, 30, 60, 300]

适用于所有 duration 类型的 Histogram 指标.
"""

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
    """
    Registry for managing metrics singleton.

    Uses class-level attributes to store singleton state, eliminating
    the need for global statements while maintaining the same API.
    """

    meter: metrics.Meter | None = None
    in_memory_reader: InMemoryMetricReader | None = None

    @classmethod
    def get_meter(cls) -> metrics.Meter | None:
        """Get the current meter instance."""
        return cls.meter

    @classmethod
    def get_in_memory_reader(cls) -> InMemoryMetricReader | None:
        """Get the current in-memory reader instance."""
        return cls.in_memory_reader

    @classmethod
    def set_meter(cls, meter: metrics.Meter) -> None:
        """Set the meter instance."""
        cls.meter = meter

    @classmethod
    def set_in_memory_reader(cls, reader: InMemoryMetricReader) -> None:
        """Set the in-memory reader instance."""
        cls.in_memory_reader = reader

    @classmethod
    def reset(cls) -> None:
        """Reset all metrics state (for testing purposes)."""
        cls.meter = None
        cls.in_memory_reader = None


# Histogram buckets 配置 (秒)
_HISTOGRAM_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0)


class MetricDefinition(TypedDict):
    """指标定义配置."""

    name: str  # 属性名
    instrument_name: str  # OTel 指标名称
    type: str  # "histogram" | "counter" | "gauge"
    description: str  # 指标描述


# 指标定义配置字典
# 数据驱动的指标注册，避免重复代码
METRIC_DEFINITIONS: list[MetricDefinition] = [
    # 数据指标
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
    # 因子指标
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
    # 策略指标
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
    # 组合指标
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
    # 风控指标
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
    # 系统指标
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
    # 缓存指标
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
    # SQL 指标
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
    # JSON 序列化指标
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
    # DQ 批量检查指标
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
    """
    简化的 Gauge 包装器.

    使用实例变量存储状态，提供简单的 set/inc/dec 接口。
    不支持 attributes 参数，简化了接口。
    """

    def __init__(self, meter: metrics.Meter, name: str, description: str) -> None:
        """
        初始化 SimpleGauge.

        Args:
        ----
            meter: OTel Meter 实例
            name: 指标名称
            description: 指标描述

        """
        self._value = 0.0

        def callback(options: Any) -> list[metrics.Observation]:
            """ObservableGauge 回调函数."""
            return [metrics.Observation(self._value, {})]

        self._gauge = meter.create_observable_gauge(
            name,
            [callback],
            description=description,
        )

    def set(self, value: float) -> None:
        """
        设置指标值.

        Args:
        ----
            value: 指标值

        """
        self._value = value

    def inc(self, delta: float = 1.0) -> None:
        """
        增加指标值.

        注意: 允许传入负数来减少值，但不会低于 0.0。
        如需减少值，建议使用 dec() 方法以获得更清晰的语义。

        Args:
        ----
            delta: 增量，默认为 1.0。可为负数。

        """
        self._value = max(0.0, self._value + delta)

    def dec(self, delta: float = 1.0) -> None:
        """
        减少指标值.

        值不会低于 0.0。

        Args:
        ----
            delta: 减量，默认为 1.0

        """
        self._value = max(0.0, self._value - delta)


class M:
    """预定义业务指标集合."""

    # 数据指标
    data_update_duration: Histogram
    data_records: Counter
    data_freshness: SimpleGauge
    data_errors: Counter

    # 因子指标
    factor_calc_duration: Histogram
    factor_ic: SimpleGauge
    factor_health: SimpleGauge

    # 策略指标
    signal_total: Counter
    rebalance_total: Counter

    # 组合指标
    portfolio_value: SimpleGauge
    portfolio_drawdown: SimpleGauge
    portfolio_drawdown_3d: SimpleGauge

    # 风控指标
    kill_switch_level: SimpleGauge
    kill_switch_total: Counter

    # 系统指标
    scheduler_jobs: Counter
    api_requests: Counter
    api_duration: Histogram

    # 缓存指标
    cache_hit: Counter
    cache_miss: Counter
    cache_hit_rate: SimpleGauge
    cache_invalidations: Counter
    cache_evictions: Counter
    cache_size: SimpleGauge

    # SQL 指标
    sql_query_duration: Histogram
    sql_slow_query_total: Counter
    sql_query_plan_cache_hit: Counter
    sql_query_plan_cache_miss: Counter

    # JSON 序列化指标
    json_serialize_duration: Histogram
    json_deserialize_duration: Histogram
    json_bytes_total: Counter

    # DQ 批量检查指标
    dq_batch_checks: Counter
    dq_batch_issues: Counter
    dq_batch_alerts: Counter

    @classmethod
    def setup(cls, meter: metrics.Meter) -> None:
        """
        初始化所有指标（基于配置驱动）.

        Args:
        ----
            meter: OTel Meter 实例

        """
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
                msg = f"Unknown metric type: {metric_type}"
                raise ValueError(msg)


def _create_gauge(
    meter: metrics.Meter,
    name: str,
    description: str,
) -> SimpleGauge:
    """
    创建一个 ObservableGauge，提供简单的 set() 接口.

    Args:
    ----
        meter: OTel Meter 实例
        name: 指标名称
        description: 指标描述

    Returns:
    -------
        SimpleGauge: 包装了 ObservableGauge 的对象，提供 set() / inc() / dec() 方法

    """
    return SimpleGauge(meter, name, description)


def configure_metrics(config: ObservabilityConfig) -> metrics.Meter:
    """
    配置 OTel Metrics.

    Args:
    ----
        config: 可观测性配置

    Returns:
    -------
        metrics.Meter: 配置好的 Meter 实例

    """
    # 获取生效配置
    effective = config.get_effective_config()

    # 资源定义
    resource = Resource.create({"service.name": config.service_name})

    # 配置 Histogram buckets 视图 - 适用于所有 duration 类型指标
    # 注意：当前 OpenTelemetry SDK 不支持 name_pattern 匹配
    # 需要为每个 duration 指标单独创建 View
    duration_histogram_aggregation = ExplicitBucketHistogramAggregation(
        boundaries=_HISTOGRAM_BUCKETS,
    )

    # 从 METRIC_DEFINITIONS 中提取所有 histogram 类型的指标
    duration_histogram_names = [
        m["instrument_name"] for m in METRIC_DEFINITIONS if m["type"] == "histogram"
    ]

    # 为每个 duration 指标创建视图
    duration_histogram_views = [
        View(
            instrument_type=Histogram,
            instrument_name=name,
            aggregation=duration_histogram_aggregation,
        )
        for name in duration_histogram_names
    ]

    # TESTING 或 TESTING_WITH_ASSERTIONS：使用 InMemory Reader
    if config.environment.is_testing or config.pytest_running:
        in_memory_reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[in_memory_reader],
            resource=resource,
            views=duration_histogram_views,
        )
        # 直接从 provider 获取 meter，不设置全局 provider
        meter = provider.get_meter(__name__)
        _MetricsRegistry.set_meter(meter)
        _MetricsRegistry.set_in_memory_reader(in_memory_reader)
        M.setup(meter)
        return meter

    # PRODUCTION / DEVELOPMENT：配置 OTLP Exporter
    # 将指标推送到 VictoriaMetrics
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
    """重置 Metrics 状态（用于测试）."""
    _MetricsRegistry.reset()


def get_in_memory_reader() -> InMemoryMetricReader | None:
    """
    获取 InMemory Metric Reader（测试用）.

    Returns
    -------
        InMemoryMetricReader | None: 当前的 InMemory Metric Reader 实例

    """
    return _MetricsRegistry.get_in_memory_reader()
