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
from opentelemetry.metrics import Counter, Histogram, ObservableGauge
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


if TYPE_CHECKING:

    class GaugeWrapper(Protocol):
        """Gauge 接口协议 (类型检查用)."""

        def set(self, value: float, attributes: dict[str, str] | None = None) -> None:
            """设置指标值."""
            ...

        def inc(self, delta: float = 1.0) -> None:
            """增加指标值."""
            ...

        def dec(self, delta: float = 1.0) -> None:
            """减少指标值."""
            ...


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


def _create_gauge(
    meter: metrics.Meter,
    name: str,
    description: str,
) -> "GaugeWrapper":
    """
    创建一个 ObservableGauge，提供简单的 set() 接口.

    注意: 当前实现不支持 attributes 参数。set(attributes) 中的 attributes
    会被忽略，因为 ObservableGauge 使用固定的回调函数。

    Args:
    ----
        meter: OTel Meter 实例
        name: 指标名称
        description: 指标描述

    Returns:
    -------
        GaugeWrapper: 包装了 ObservableGauge 的对象，提供 set() / inc() / dec() 方法

    """
    # 使用字典来存储当前值
    current_values: dict[str, float] = {}

    def callback(options: Any) -> list[metrics.Observation]:
        """ObservableGauge 回调函数."""
        value = current_values.get(name, 0.0)
        return [metrics.Observation(value, {})]

    gauge = meter.create_observable_gauge(
        name,
        [callback],
        description=description,
    )

    # 创建一个包装类提供 set() 接口
    class GaugeWrapper:
        """
        ObservableGauge 包装器，提供简单的 set() 接口.

        注意: 当前实现不支持多标签 attributes。如需带标签的 Gauge，
        请使用 meter.create_gauge() 直接创建。
        """

        def __init__(self, obs_gauge: ObservableGauge) -> None:
            self._gauge = obs_gauge
            self._name = name

        def set(self, value: float, attributes: dict[str, str] | None = None) -> None:
            """
            设置指标值.

            Args:
            ----
                value: 指标值
                attributes: 标签字典 (当前实现中会被忽略，保留用于API兼容性)

            """
            current_values[self._name] = value

        def inc(self, delta: float = 1.0) -> None:
            """增加指标值."""
            current = current_values.get(self._name, 0.0)
            current_values[self._name] = current + delta

        def dec(self, delta: float = 1.0) -> None:
            """减少指标值."""
            current = current_values.get(self._name, 0.0)
            current_values[self._name] = max(0, current - delta)

    return GaugeWrapper(gauge)


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
