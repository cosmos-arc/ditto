"""
指标模块.

基于 OpenTelemetry 的指标收集，定义所有预定义业务指标.

Histogram Buckets 配置 (秒):
    [0.1, 0.5, 1, 5, 10, 30, 60, 300]

适用于所有 duration 类型的 Histogram 指标.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

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

from .config import Mode, ObservabilityConfig

# 全局变量
_meter: metrics.Meter | None = None
_in_memory_reader: InMemoryMetricReader | None = None
_gauge_callbacks: dict[str, Callable[..., Any]] = {}

# Histogram buckets 配置 (秒)
_HISTOGRAM_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0)


# 用于类型检查的 Gauge 接口协议
if TYPE_CHECKING:

    class GaugeWrapper(Protocol):
        """Gauge 接口协议 (类型检查用)."""

        def set(self, value: float) -> None:
            """设置指标值."""
            ...

        def inc(self, delta: float = 1.0) -> None:
            """增加指标值."""
            ...

        def dec(self, delta: float = 1.0) -> None:
            """减少指标值."""
            ...


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
    data_freshness: "GaugeWrapper"
    data_errors: Counter

    # 因子指标
    factor_calc_duration: Histogram
    factor_ic: "GaugeWrapper"
    factor_health: "GaugeWrapper"

    # 策略指标
    signal_total: Counter
    rebalance_total: Counter

    # 组合指标
    portfolio_value: "GaugeWrapper"
    portfolio_drawdown: "GaugeWrapper"
    portfolio_drawdown_3d: "GaugeWrapper"

    # 风控指标
    kill_switch_level: "GaugeWrapper"
    kill_switch_total: Counter

    # 系统指标
    scheduler_jobs: Counter
    api_requests: Counter
    api_duration: Histogram

    # 缓存指标
    cache_hit: Counter
    cache_miss: Counter
    cache_hit_rate: "GaugeWrapper"
    cache_invalidations: Counter
    cache_evictions: Counter
    cache_size: "GaugeWrapper"

    # SQL 指标
    sql_query_duration: Histogram
    sql_slow_query_total: Counter
    sql_query_plan_cache_hit: Counter
    sql_query_plan_cache_miss: Counter

    # JSON 序列化指标
    json_serialize_duration: Histogram
    json_deserialize_duration: Histogram
    json_bytes_total: Counter

    @classmethod
    def setup(cls, meter: metrics.Meter) -> None:
        """
        初始化所有指标.

        Args:
        ----
            meter: OTel Meter 实例

        """
        # 数据指标
        cls.data_update_duration = meter.create_histogram(
            "ditto.data.update.duration",
            description="Data update operation duration in seconds",
        )
        cls.data_records = meter.create_counter(
            "ditto.data.records_total",
            description="Total data records processed",
        )
        # 使用 ObservableGauge 需要回调函数，我们创建简单的包装器
        cls.data_freshness = _create_gauge(
            meter,
            "ditto.data.freshness_days",
            "Data freshness in days since last update",
        )
        cls.data_errors = meter.create_counter(
            "ditto.data.errors_total",
            description="Total data processing errors",
        )

        # 因子指标
        cls.factor_calc_duration = meter.create_histogram(
            "ditto.factor.calc.duration",
            description="Factor calculation duration in seconds",
        )
        cls.factor_ic = _create_gauge(
            meter,
            "ditto.factor.ic",
            "Factor Information Coefficient (IC)",
        )
        cls.factor_health = _create_gauge(
            meter,
            "ditto.factor.health",
            "Factor health score (0-100)",
        )

        # 策略指标
        cls.signal_total = meter.create_counter(
            "ditto.signal.total",
            description="Total trading signals generated",
        )
        cls.rebalance_total = meter.create_counter(
            "ditto.rebalance.total",
            description="Total portfolio rebalances executed",
        )

        # 组合指标
        cls.portfolio_value = _create_gauge(
            meter,
            "ditto.portfolio.value",
            "Current portfolio value",
        )
        cls.portfolio_drawdown = _create_gauge(
            meter,
            "ditto.portfolio.drawdown",
            "Current portfolio drawdown",
        )
        cls.portfolio_drawdown_3d = _create_gauge(
            meter,
            "ditto.portfolio.drawdown_3d",
            "3-day rolling portfolio drawdown",
        )

        # 风控指标
        cls.kill_switch_level = _create_gauge(
            meter,
            "ditto.risk.kill_switch_level",
            "Current kill switch level (0-3)",
        )
        cls.kill_switch_total = meter.create_counter(
            "ditto.risk.kill_switch_total",
            description="Total kill switch triggers",
        )

        # 系统指标
        cls.scheduler_jobs = meter.create_counter(
            "ditto.scheduler.jobs_total",
            description="Total scheduler jobs executed",
        )
        cls.api_requests = meter.create_counter(
            "ditto.api.requests_total",
            description="Total API requests",
        )
        cls.api_duration = meter.create_histogram(
            "ditto.api.duration",
            description="API request duration in seconds",
        )

        # 缓存指标
        cls.cache_hit = meter.create_counter(
            "ditto.cache.hit_total",
            description="Total cache hits",
        )
        cls.cache_miss = meter.create_counter(
            "ditto.cache.miss_total",
            description="Total cache misses",
        )
        cls.cache_hit_rate = _create_gauge(
            meter,
            "ditto.cache.hit_rate",
            "Cache hit rate (0-1)",
        )
        cls.cache_invalidations = meter.create_counter(
            "ditto.cache.invalidations_total",
            description="Total cache invalidations",
        )
        cls.cache_evictions = meter.create_counter(
            "ditto.cache.evictions_total",
            description="Total cache evictions",
        )
        cls.cache_size = _create_gauge(
            meter,
            "ditto.cache.size",
            "Current cache size (number of entries)",
        )

        # SQL 指标
        cls.sql_query_duration = meter.create_histogram(
            "ditto.sql.query.duration",
            description="SQL query execution duration in seconds",
        )
        cls.sql_slow_query_total = meter.create_counter(
            "ditto.sql.slow_query_total",
            description="Total slow queries",
        )
        cls.sql_query_plan_cache_hit = meter.create_counter(
            "ditto.sql.query_plan_cache.hit_total",
            description="Total query plan cache hits",
        )
        cls.sql_query_plan_cache_miss = meter.create_counter(
            "ditto.sql.query_plan_cache.miss_total",
            description="Total query plan cache misses",
        )

        # JSON 序列化指标
        cls.json_serialize_duration = meter.create_histogram(
            "ditto.json.serialize.duration",
            description="JSON serialization duration in seconds",
        )
        cls.json_deserialize_duration = meter.create_histogram(
            "ditto.json.deserialize.duration",
            description="JSON deserialization duration in seconds",
        )
        cls.json_bytes_total = meter.create_counter(
            "ditto.json.bytes_total",
            description="Total JSON bytes processed",
        )


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


def configure_metrics(config: ObservabilityConfig, mode: Mode) -> metrics.Meter:
    """
    配置 OTel Metrics.

    Args:
    ----
        config: 可观测性配置
        mode: 运行模式

    Returns:
    -------
        metrics.Meter: 配置好的 Meter 实例

    """
    global _meter, _in_memory_reader

    # 资源定义
    resource = Resource.create({"service.name": config.service_name})

    # 配置 Histogram buckets 视图 - 适用于所有 duration 类型指标
    # 注意：当前 OpenTelemetry SDK 不支持 name_pattern 匹配
    # 需要为每个 duration 指标单独创建 View
    duration_histogram_aggregation = ExplicitBucketHistogramAggregation(
        boundaries=_HISTOGRAM_BUCKETS,
    )

    # 为每个 duration 指标创建视图
    duration_histogram_views = [
        View(
            instrument_type=Histogram,
            instrument_name="ditto.data.update.duration",
            aggregation=duration_histogram_aggregation,
        ),
        View(
            instrument_type=Histogram,
            instrument_name="ditto.factor.calc.duration",
            aggregation=duration_histogram_aggregation,
        ),
        View(
            instrument_type=Histogram,
            instrument_name="ditto.api.duration",
            aggregation=duration_histogram_aggregation,
        ),
        View(
            instrument_type=Histogram,
            instrument_name="ditto.sql.query.duration",
            aggregation=duration_histogram_aggregation,
        ),
        View(
            instrument_type=Histogram,
            instrument_name="ditto.json.serialize.duration",
            aggregation=duration_histogram_aggregation,
        ),
        View(
            instrument_type=Histogram,
            instrument_name="ditto.json.deserialize.duration",
            aggregation=duration_histogram_aggregation,
        ),
    ]

    # TESTING 或 TESTING_WITH_ASSERTIONS：使用 InMemory Reader
    if mode.is_testing():
        _in_memory_reader = InMemoryMetricReader()
        provider = MeterProvider(
            metric_readers=[_in_memory_reader],
            resource=resource,
            views=duration_histogram_views,
        )
        # 直接从 provider 获取 meter，不设置全局 provider
        _meter = provider.get_meter(__name__)
        M.setup(_meter)
        return _meter

    # PRODUCTION / DEVELOPMENT：配置 OTLP Exporter
    # 将指标推送到 VictoriaMetrics
    otlp_exporter = OTLPMetricExporter(
        endpoint=config.vm_endpoint,
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
    _meter = metrics.get_meter(config.service_name)
    M.setup(_meter)

    return _meter


def reset_metrics() -> None:
    """重置 Metrics 状态（用于测试）."""
    global _meter, _in_memory_reader

    _meter = None
    _in_memory_reader = None


def _get_in_memory_reader() -> InMemoryMetricReader | None:
    """
    获取 InMemory Metric Reader（测试用）.

    Returns
    -------
        InMemoryMetricReader | None: 当前的 InMemory Metric Reader 实例

    """
    return _in_memory_reader
