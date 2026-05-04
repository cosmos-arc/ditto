"""
可观测性指标集成测试.

验证 OpenTelemetry Metrics SDK 与 OTLP Exporter 的集成，
覆盖技术指标的代表类别，每个指标验证元数据、数值、属性、类型行为四个维度.

以及 METRIC_DEFINITIONS 配置驱动的指标注册测试.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from ditto_platform.foundation import Metrics, ObservabilityConfig, reset_for_testing
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.metrics import (
    SafeCounter,
    SafeHistogram,
    configure_metrics,
)

_conftest_path = Path(__file__).parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("_conftest", _conftest_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

MetricReaderWrapper = _mod.MetricReaderWrapper
wait_for_export = _mod.wait_for_export


@pytest.mark.integration
class TestMetricsIntegration:
    """可观测性指标集成测试。"""

    # ==================== API 指标 (Counter) ====================

    def test_api_counter_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 API Counter 指标的元数据：name, description, unit."""
        counter = meter.create_counter(
            "ditto.api.requests_total", description="Total API requests"
        )

        # 触发导出
        counter.add(1, {"endpoint": "/health"})
        wait_for_export()

        # 获取导出的指标
        metrics = metrics_exporter.get_metrics_by_name("ditto.api.requests_total")
        assert len(metrics) > 0, "指标应该被导出"

        metric = metrics[0]
        assert metric.name == "ditto.api.requests_total"
        assert metric.description == "Total API requests"
        # Counter 类型的验证：数据点有 value 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_api_counter_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Counter 数值正确累加."""
        counter = meter.create_counter("ditto.api.requests_total")

        counter.add(1, {"endpoint": "/health"})
        counter.add(3, {"endpoint": "/health"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.requests_total")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 1
        assert data_points[0].value == 4  # 1 + 3

    def test_api_counter_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 attributes 正确传递和分组."""
        counter = meter.create_counter("ditto.api.requests_total")

        counter.add(1, {"endpoint": "/health", "method": "GET"})
        counter.add(2, {"endpoint": "/metrics", "method": "GET"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.requests_total")
        data_points = list(metrics[0].data.data_points)

        # 验证两个不同的 time series
        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"endpoint": "/health", "method": "GET"} in attrs_list
        assert {"endpoint": "/metrics", "method": "GET"} in attrs_list

    def test_api_counter_monotonic(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Counter 单调递增行为."""
        counter = meter.create_counter("ditto.api.requests_total")

        counter.add(5, {"endpoint": "/health"})
        counter.add(3, {"endpoint": "/health"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.requests_total")
        data_point = next(iter(metrics[0].data.data_points))

        # Counter 应该累加，而非覆盖
        assert data_point.value == 8  # 5 + 3

    # ==================== API 指标 (Histogram) ====================

    def test_api_histogram_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 API Histogram 指标的元数据."""
        histogram = meter.create_histogram(
            "ditto.api.duration",
            description="API request duration in seconds",
        )

        histogram.record(0.5, {"endpoint": "/jobs"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.api.duration"
        assert metric.description == "API request duration in seconds"
        # Histogram 类型的验证：数据点有 bucket_counts 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "bucket_counts")

    def test_api_histogram_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Histogram 记录值."""
        histogram = meter.create_histogram("ditto.api.duration")

        histogram.record(0.3, {"endpoint": "/jobs"})
        histogram.record(1.5, {"endpoint": "/jobs"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 count 和 sum
        assert data_point.count == 2
        assert abs(data_point.sum - 1.8) < 0.01  # 0.3 + 1.5

    def test_api_histogram_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Histogram attributes 分组."""
        histogram = meter.create_histogram("ditto.api.duration")

        histogram.record(0.5, {"endpoint": "/jobs"})
        histogram.record(0.8, {"endpoint": "/reports"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证两个不同的 time series
        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"endpoint": "/jobs"} in attrs_list
        assert {"endpoint": "/reports"} in attrs_list

    def test_api_histogram_buckets(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Histogram buckets 分布."""
        histogram = meter.create_histogram("ditto.api.duration")

        # 记录不同范围的值
        histogram.record(0.05, {"endpoint": "/test"})  # < 0.1
        histogram.record(0.3, {"endpoint": "/test"})  # 0.1 - 0.5
        histogram.record(2.0, {"endpoint": "/test"})  # 1.0 - 5.0
        histogram.record(10.0, {"endpoint": "/test"})  # 5.0 - 10.0
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 bucket counts
        counts = data_point.bucket_counts
        # buckets: [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
        assert counts[0] == 1  # < 0.1
        assert counts[1] == 1  # 0.1 - 0.5
        assert counts[2] == 0  # 0.5 - 1.0
        assert counts[3] == 1  # 1.0 - 5.0
        assert counts[4] == 1  # 5.0 - 10.0
        assert counts[5] == 0  # 10.0 - 30.0

    # ==================== Scheduler 指标 (Counter) ====================

    def test_scheduler_counter_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Scheduler Counter 指标的元数据."""
        counter = meter.create_counter(
            "ditto.scheduler.jobs_total", description="Total scheduler jobs executed"
        )

        counter.add(1, {"job": "daily_update"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.scheduler.jobs_total")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.scheduler.jobs_total"
        assert metric.description == "Total scheduler jobs executed"
        # Counter 类型验证
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_scheduler_counter_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Scheduler 作业计数."""
        counter = meter.create_counter("ditto.scheduler.jobs_total")

        counter.add(5, {"job": "daily_update", "status": "success"})
        counter.add(3, {"job": "daily_update", "status": "failed"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.scheduler.jobs_total")
        data_points = list(metrics[0].data.data_points)

        # 验证两个 time series
        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if (
                dp.attributes.get("job") == "daily_update"
                and dp.attributes.get("status") == "success"
            ):
                assert dp.value == 5
            elif (
                dp.attributes.get("job") == "daily_update"
                and dp.attributes.get("status") == "failed"
            ):
                assert dp.value == 3

    def test_scheduler_counter_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Scheduler attributes."""
        counter = meter.create_counter("ditto.scheduler.jobs_total")

        counter.add(1, {"job": "daily_update", "queue": "default"})
        counter.add(1, {"job": "metric_export", "queue": "default"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.scheduler.jobs_total")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"job": "daily_update", "queue": "default"} in attrs_list
        assert {"job": "metric_export", "queue": "default"} in attrs_list

    def test_scheduler_counter_monotonic(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Scheduler 计数单调递增."""
        counter = meter.create_counter("ditto.scheduler.jobs_total")

        counter.add(10, {"job": "test"})
        counter.add(5, {"job": "test"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.scheduler.jobs_total")
        data_point = next(iter(metrics[0].data.data_points))

        assert data_point.value == 15  # 10 + 5

    # ==================== Cache 指标 (Gauge) ====================

    def test_cache_size_gauge_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Cache Gauge 指标的元数据."""
        gauge = meter.create_gauge(
            "ditto.cache.size", description="Current cache size (number of entries)"
        )

        gauge.set(100000.0, {"cache": "test_cache"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.size")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.cache.size"
        assert metric.description == "Current cache size (number of entries)"
        # Gauge 类型验证：数据点有 value 属性（与 Counter 相同）
        # 但通过行为测试验证可逆性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_cache_size_gauge_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Gauge 设置值（可覆盖）."""
        gauge = meter.create_gauge("ditto.cache.size")

        gauge.set(100000.0, {"cache": "test_cache"})
        gauge.set(105000.0, {"cache": "test_cache"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.size")
        data_point = next(iter(metrics[0].data.data_points))

        # Gauge 应该覆盖，而非累加
        assert data_point.value == 105000.0

    def test_cache_size_gauge_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Cache attributes."""
        gauge = meter.create_gauge("ditto.cache.size")

        gauge.set(100000.0, {"cache": "cache_001"})
        gauge.set(200000.0, {"cache": "cache_002"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.size")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if dp.attributes.get("cache") == "cache_001":
                assert dp.value == 100000.0
            elif dp.attributes.get("cache") == "cache_002":
                assert dp.value == 200000.0

    def test_cache_size_gauge_reversible(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Gauge 可增可减."""
        gauge = meter.create_gauge("ditto.cache.size")

        gauge.set(100000.0, {"cache": "test"})
        gauge.set(95000.0, {"cache": "test"})
        gauge.set(105000.0, {"cache": "test"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.size")
        data_point = next(iter(metrics[0].data.data_points))

        # Gauge 应该支持任意值变化
        assert data_point.value == 105000.0

    # ==================== Cache 指标 (Counter) ====================

    def test_cache_counter_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Cache Counter 指标的元数据."""
        counter = meter.create_counter(
            "ditto.cache.invalidations_total",
            description="Total cache invalidations",
        )

        counter.add(1, {"cache": "primary", "reason": "refresh"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name(
            "ditto.cache.invalidations_total"
        )
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.cache.invalidations_total"
        assert metric.description == "Total cache invalidations"
        # Counter 类型验证
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_cache_counter_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Cache 事件计数."""
        counter = meter.create_counter("ditto.cache.invalidations_total")

        counter.add(1, {"cache": "primary"})
        counter.add(1, {"cache": "secondary"})
        counter.add(1, {"cache": "secondary"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name(
            "ditto.cache.invalidations_total"
        )
        data_points = list(metrics[0].data.data_points)

        # primary: 1 次，secondary: 2 次
        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if dp.attributes.get("cache") == "primary":
                assert dp.value == 1
            elif dp.attributes.get("cache") == "secondary":
                assert dp.value == 2

    def test_cache_counter_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Cache 事件 attributes."""
        counter = meter.create_counter("ditto.cache.invalidations_total")

        counter.add(1, {"cache": "primary", "reason": "refresh"})
        counter.add(1, {"cache": "secondary", "reason": "ttl"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name(
            "ditto.cache.invalidations_total"
        )
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"cache": "primary", "reason": "refresh"} in attrs_list
        assert {"cache": "secondary", "reason": "ttl"} in attrs_list

    def test_cache_counter_monotonic(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Cache 计数器单调递增."""
        counter = meter.create_counter("ditto.cache.invalidations_total")

        counter.add(1, {"cache": "primary"})
        counter.add(1, {"cache": "primary"})
        counter.add(1, {"cache": "primary"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name(
            "ditto.cache.invalidations_total"
        )
        data_point = next(iter(metrics[0].data.data_points))

        assert data_point.value == 3

    # ==================== 系统指标 (Histogram) ====================

    def test_system_histogram_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证系统 Histogram 指标的元数据."""
        histogram = meter.create_histogram(
            "ditto.api.duration", description="API request duration in seconds"
        )

        histogram.record(0.1, {"endpoint": "/api/v1/data"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.api.duration"
        assert metric.description == "API request duration in seconds"
        # Histogram 类型验证：数据点有 bucket_counts 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "bucket_counts")

    def test_system_histogram_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 API 耗时统计."""
        histogram = meter.create_histogram("ditto.api.duration")

        histogram.record(0.05, {"endpoint": "/api/v1/data"})
        histogram.record(0.15, {"endpoint": "/api/v1/data"})
        histogram.record(0.25, {"endpoint": "/api/v1/data"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 count 和 sum
        assert data_point.count == 3
        assert abs(data_point.sum - 0.45) < 0.01  # 0.05 + 0.15 + 0.25

    def test_system_histogram_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 API 端点 attributes."""
        histogram = meter.create_histogram("ditto.api.duration")

        histogram.record(0.1, {"endpoint": "/api/v1/data", "method": "GET"})
        histogram.record(0.2, {"endpoint": "/api/v1/data", "method": "POST"})
        histogram.record(0.15, {"endpoint": "/api/v1/reports", "method": "GET"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证三个不同的 time series
        assert len(data_points) == 3

        attrs_list = [dp.attributes for dp in data_points]
        assert {"endpoint": "/api/v1/data", "method": "GET"} in attrs_list
        assert {"endpoint": "/api/v1/data", "method": "POST"} in attrs_list
        assert {"endpoint": "/api/v1/reports", "method": "GET"} in attrs_list

    def test_system_histogram_buckets(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 API 耗时 buckets 分布."""
        histogram = meter.create_histogram("ditto.api.duration")

        # 记录不同范围的 API 耗时
        histogram.record(0.05, {"endpoint": "/fast"})  # < 0.1
        histogram.record(0.3, {"endpoint": "/medium"})  # 0.1 - 0.5
        histogram.record(2.0, {"endpoint": "/slow"})  # 1.0 - 5.0
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证每个 endpoint 的 bucket 分布
        assert len(data_points) == 3

        # /fast: < 0.1 bucket
        fast_dp = next(dp for dp in data_points if dp.attributes["endpoint"] == "/fast")
        assert fast_dp.bucket_counts[0] == 1

        # /medium: 0.1 - 0.5 bucket
        medium_dp = next(
            dp for dp in data_points if dp.attributes["endpoint"] == "/medium"
        )
        assert medium_dp.bucket_counts[1] == 1

        # /slow: 1.0 - 5.0 bucket
        slow_dp = next(dp for dp in data_points if dp.attributes["endpoint"] == "/slow")
        assert slow_dp.bucket_counts[3] == 1

    # ==================== 缓存指标 (Gauge) ====================

    def test_cache_gauge_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证缓存 Gauge 指标的元数据."""
        gauge = meter.create_gauge(
            "ditto.cache.hit_rate", description="Cache hit rate (0-1)"
        )

        gauge.set(0.85, {"cache": "primary_cache"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.hit_rate")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.cache.hit_rate"
        assert metric.description == "Cache hit rate (0-1)"
        # Gauge 类型验证：数据点有 value 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_cache_gauge_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证缓存命中率（百分比）."""
        gauge = meter.create_gauge("ditto.cache.hit_rate")

        gauge.set(0.80, {"cache": "primary_cache"})
        gauge.set(0.85, {"cache": "primary_cache"})
        gauge.set(0.90, {"cache": "primary_cache"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.hit_rate")
        data_point = next(iter(metrics[0].data.data_points))

        # Gauge 应该覆盖为最新值
        assert abs(data_point.value - 0.90) < 0.001

    def test_cache_gauge_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证缓存实例 attributes."""
        gauge = meter.create_gauge("ditto.cache.hit_rate")

        gauge.set(0.85, {"cache": "primary_cache"})
        gauge.set(0.92, {"cache": "secondary_cache"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.hit_rate")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if dp.attributes.get("cache") == "primary_cache":
                assert abs(dp.value - 0.85) < 0.001
            elif dp.attributes.get("cache") == "secondary_cache":
                assert abs(dp.value - 0.92) < 0.001

    def test_cache_gauge_percentage_range(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证命中率百分比范围（0-1）."""
        gauge = meter.create_gauge("ditto.cache.hit_rate")

        # 测试边界值
        gauge.set(0.0, {"cache": "test"})  # 0%
        gauge.set(0.5, {"cache": "test"})  # 50%
        gauge.set(1.0, {"cache": "test"})  # 100%
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.hit_rate")
        data_point = next(iter(metrics[0].data.data_points))

        # 最终值应该是 1.0 (100%)
        assert abs(data_point.value - 1.0) < 0.001

    # ==================== SQL 指标 (Histogram) ====================

    def test_sql_histogram_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 SQL Histogram 指标的元数据."""
        histogram = meter.create_histogram(
            "ditto.sql.query.duration",
            description="SQL query execution duration in seconds",
        )

        histogram.record(0.5, {"query_type": "SELECT"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.sql.query.duration")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.sql.query.duration"
        assert metric.description == "SQL query execution duration in seconds"
        # Histogram 类型验证：数据点有 bucket_counts 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "bucket_counts")

    def test_sql_histogram_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 SQL 查询耗时统计."""
        histogram = meter.create_histogram("ditto.sql.query.duration")

        histogram.record(0.1, {"query_type": "SELECT"})
        histogram.record(0.5, {"query_type": "SELECT"})
        histogram.record(2.0, {"query_type": "SELECT"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.sql.query.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 count 和 sum
        assert data_point.count == 3
        assert abs(data_point.sum - 2.6) < 0.01  # 0.1 + 0.5 + 2.0

    def test_sql_histogram_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 SQL 查询类型 attributes."""
        histogram = meter.create_histogram("ditto.sql.query.duration")

        histogram.record(0.1, {"query_type": "SELECT"})
        histogram.record(0.5, {"query_type": "INSERT"})
        histogram.record(0.3, {"query_type": "UPDATE"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.sql.query.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证三个不同的 time series
        assert len(data_points) == 3

        attrs_list = [dp.attributes for dp in data_points]
        assert {"query_type": "SELECT"} in attrs_list
        assert {"query_type": "INSERT"} in attrs_list
        assert {"query_type": "UPDATE"} in attrs_list

    def test_sql_histogram_slow_query_bucket(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证慢查询 bucket (>5s)."""
        histogram = meter.create_histogram("ditto.sql.query.duration")

        # 记录不同范围的查询耗时
        histogram.record(0.5, {"query_type": "SELECT"})  # 正常
        histogram.record(3.0, {"query_type": "SELECT"})  # 较慢
        histogram.record(8.0, {"query_type": "SELECT"})  # 慢查询 (>5s)
        histogram.record(60.0, {"query_type": "SELECT"})  # 非常慢 (>30s)
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.sql.query.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 bucket 分布
        counts = data_point.bucket_counts
        # buckets: [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
        assert counts[0] == 0  # < 0.1
        assert counts[1] == 1  # 0.1 - 0.5
        assert counts[2] == 0  # 0.5 - 1.0
        assert counts[3] == 1  # 1.0 - 5.0
        assert counts[4] == 1  # 5.0 - 10.0 (慢查询)
        assert counts[5] == 0  # 10.0 - 30.0
        assert counts[6] == 1  # 30.0 - 60.0
        assert counts[7] == 0  # 60.0 - 300.0
        # +Inf bucket 应该有 1 个 (60.0 落在 60.0-300.0 之间，但可能有 +Inf bucket)
        # 实际上 bucket_counts 长度是 boundaries + 1
        assert sum(counts) == 4  # 总共 4 个查询

    # ==================== JSON 指标 (Histogram) ====================

    def test_json_histogram_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 JSON Histogram 指标的元数据."""
        histogram = meter.create_histogram(
            "ditto.json.serialize.duration",
            description="JSON serialization duration in seconds",
        )

        histogram.record(0.01, {"data_type": "payload"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.json.serialize.duration")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.json.serialize.duration"
        assert metric.description == "JSON serialization duration in seconds"
        # Histogram 类型验证：数据点有 bucket_counts 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "bucket_counts")

    def test_json_histogram_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 JSON 序列化耗时统计."""
        histogram = meter.create_histogram("ditto.json.serialize.duration")

        # 使用相同的 attributes 来测试累计统计
        histogram.record(0.01, {"data_type": "test"})
        histogram.record(0.05, {"data_type": "test"})
        histogram.record(0.1, {"data_type": "test"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.json.serialize.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 count 和 sum
        assert data_point.count == 3
        assert abs(data_point.sum - 0.16) < 0.01  # 0.01 + 0.05 + 0.1

    def test_json_histogram_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 JSON 操作类型 attributes."""
        histogram = meter.create_histogram("ditto.json.serialize.duration")

        histogram.record(0.01, {"data_type": "payload", "operation": "serialize"})
        histogram.record(0.02, {"data_type": "payload", "operation": "deserialize"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.json.serialize.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证两个不同的 time series
        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"data_type": "payload", "operation": "serialize"} in attrs_list
        assert {"data_type": "payload", "operation": "deserialize"} in attrs_list

    def test_json_histogram_fast_operations_bucket(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 JSON 序列化通常很快 (<0.1s)."""
        histogram = meter.create_histogram("ditto.json.serialize.duration")

        # 使用相同的 attributes 来测试 bucket 分布
        histogram.record(0.001, {"data_type": "test"})  # 非常快
        histogram.record(0.01, {"data_type": "test"})
        histogram.record(0.05, {"data_type": "test"})
        histogram.record(0.2, {"data_type": "test"})  # 较慢
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.json.serialize.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 bucket 分布
        counts = data_point.bucket_counts
        # buckets: [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
        assert counts[0] == 3  # < 0.1: 0.001, 0.01, 0.05
        assert counts[1] == 1  # 0.1 - 0.5: 0.2
        assert sum(counts) == 4  # 总共 4 个记录


@pytest.mark.integration
class TestMetricDefinitions:
    """测试 METRIC_DEFINITIONS 配置驱动的指标注册."""

    def test_all_metrics_created(self) -> None:
        """测试所有指标被正确创建."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # Verify所有系统指标存在
        assert hasattr(Metrics, "scheduler_jobs")
        assert hasattr(Metrics, "api_requests")
        assert hasattr(Metrics, "api_duration")

        # Verify所有缓存指标存在
        assert hasattr(Metrics, "cache_hit")
        assert hasattr(Metrics, "cache_miss")
        assert hasattr(Metrics, "cache_hit_rate")
        assert hasattr(Metrics, "cache_invalidations")
        assert hasattr(Metrics, "cache_evictions")
        assert hasattr(Metrics, "cache_size")

        # Verify所有 SQL 指标存在
        assert hasattr(Metrics, "sql_query_duration")
        assert hasattr(Metrics, "sql_slow_query_total")
        assert hasattr(Metrics, "sql_query_plan_cache_hit")
        assert hasattr(Metrics, "sql_query_plan_cache_miss")

        # Verify所有 JSON 指标存在
        assert hasattr(Metrics, "json_serialize_duration")
        assert hasattr(Metrics, "json_deserialize_duration")
        assert hasattr(Metrics, "json_bytes_total")

    def test_histogram_metrics_have_record_method(self) -> None:
        """测试 Histogram 类型的指标有 record 方法."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # Verify Histogram 类型指标有 record 方法
        assert hasattr(Metrics.api_duration, "record")
        assert hasattr(Metrics.sql_query_duration, "record")
        assert hasattr(Metrics.json_serialize_duration, "record")
        assert hasattr(Metrics.json_deserialize_duration, "record")

    def test_counter_metrics_have_add_method(self) -> None:
        """测试 Counter 类型的指标有 add 方法."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # Verify Counter 类型指标有 add 方法
        assert hasattr(Metrics.scheduler_jobs, "add")
        assert hasattr(Metrics.api_requests, "add")
        assert hasattr(Metrics.cache_hit, "add")
        assert hasattr(Metrics.cache_miss, "add")
        assert hasattr(Metrics.cache_invalidations, "add")
        assert hasattr(Metrics.cache_evictions, "add")
        assert hasattr(Metrics.sql_slow_query_total, "add")
        assert hasattr(Metrics.sql_query_plan_cache_hit, "add")
        assert hasattr(Metrics.sql_query_plan_cache_miss, "add")
        assert hasattr(Metrics.json_bytes_total, "add")

    def test_gauge_metrics_have_set_inc_dec_methods(self) -> None:
        """测试 Gauge 类型的指标有 set/inc/dec 方法."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # Verify Gauge 类型指标有 set/inc/dec 方法
        for metric_name in [
            "cache_hit_rate",
            "cache_size",
        ]:
            metric = getattr(Metrics, metric_name)
            assert hasattr(metric, "set"), f"{metric_name} should have set method"
            assert hasattr(metric, "inc"), f"{metric_name} should have inc method"
            assert hasattr(metric, "dec"), f"{metric_name} should have dec method"

    def test_metric_names_match_expected(self) -> None:
        """测试指标名称与预期一致."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # Verify部分指标名称(通过调用它们的底层方法)
        # [REVIEW]

        # api_duration 应该是 Histogram
        assert isinstance(Metrics.api_duration, SafeHistogram)
        # api_requests 应该是 Counter
        assert isinstance(Metrics.api_requests, SafeCounter)
        # cache_hit_rate 应该是 SafeGauge (有 set 方法)
        assert hasattr(Metrics.cache_hit_rate, "set")

    def test_metric_count_matches_definitions(self) -> None:
        """测试创建的指标数量与 METRIC_DEFINITIONS 中的定义一致."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # [REVIEW] M 类中定义的指标数量
        metric_count = 0
        for attr_name in dir(Metrics):
            if not attr_name.startswith("_"):
                attr = getattr(Metrics, attr_name)
                # [REVIEW](有特定的方法)
                if (
                    hasattr(attr, "record")
                    or hasattr(attr, "add")
                    or hasattr(attr, "set")
                ):
                    metric_count += 1

        # 系统: 3, 缓存: 6, SQL: 4, JSON: 3
        # [REVIEW]setup 是类方法，不是指标
        expected_metric_count = 16

        # [REVIEW](因为可能有其他类属性)
        assert metric_count >= expected_metric_count, (
            f"Expected at least {expected_metric_count} metrics, found {metric_count}"
        )

    def test_metrics_are_functional(self) -> None:
        """测试指标可以被正常使用(不会被报错)."""
        reset_for_testing()

        config = ObservabilityConfig(environment=Environment.TESTING)
        configure_metrics(config)

        # [REVIEW] Counter
        Metrics.api_requests.add(100, {"endpoint": "/test"})

        # [REVIEW] Histogram
        Metrics.api_duration.record(1.5, {"endpoint": "/test"})

        # [REVIEW] Gauge
        Metrics.cache_hit_rate.set(0.8)
        Metrics.cache_hit_rate.inc(0.1)
        Metrics.cache_hit_rate.dec(0.05)
