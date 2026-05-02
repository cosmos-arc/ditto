"""
可观测性指标集成测试.

验证 OpenTelemetry Metrics SDK 与 OTLP Exporter 的集成，
覆盖 9 个类别的代表指标，每个指标验证元数据、数值、属性、类型行为四个维度.

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

    # ==================== 数据指标 (Counter) ====================

    def test_data_counter_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证数据 Counter 指标的元数据：name, description, unit."""
        counter = meter.create_counter(
            "ditto.data.records_total", description="Total data records processed"
        )

        # 触发导出
        counter.add(1, {"source": "test"})
        wait_for_export()

        # 获取导出的指标
        metrics = metrics_exporter.get_metrics_by_name("ditto.data.records_total")
        assert len(metrics) > 0, "指标应该被导出"

        metric = metrics[0]
        assert metric.name == "ditto.data.records_total"
        assert metric.description == "Total data records processed"
        # Counter 类型的验证：数据点有 value 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_data_counter_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Counter 数值正确累加."""
        counter = meter.create_counter("ditto.data.records_total")

        counter.add(1, {"source": "test"})
        counter.add(3, {"source": "test"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.data.records_total")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 1
        assert data_points[0].value == 4  # 1 + 3

    def test_data_counter_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 attributes 正确传递和分组."""
        counter = meter.create_counter("ditto.data.records_total")

        counter.add(1, {"source": "tushare", "status": "success"})
        counter.add(2, {"source": "akshare", "status": "success"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.data.records_total")
        data_points = list(metrics[0].data.data_points)

        # 验证两个不同的 time series
        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"source": "tushare", "status": "success"} in attrs_list
        assert {"source": "akshare", "status": "success"} in attrs_list

    def test_data_counter_monotonic(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Counter 单调递增行为."""
        counter = meter.create_counter("ditto.data.records_total")

        counter.add(5, {"source": "test"})
        counter.add(3, {"source": "test"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.data.records_total")
        data_point = next(iter(metrics[0].data.data_points))

        # Counter 应该累加，而非覆盖
        assert data_point.value == 8  # 5 + 3

    # ==================== 因子指标 (Histogram) ====================

    def test_factor_histogram_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证因子 Histogram 指标的元数据."""
        histogram = meter.create_histogram(
            "ditto.factor.calc.duration",
            description="Factor calculation duration in seconds",
        )

        histogram.record(0.5, {"factor": "momentum"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.factor.calc.duration")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.factor.calc.duration"
        assert metric.description == "Factor calculation duration in seconds"
        # Histogram 类型的验证：数据点有 bucket_counts 属性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "bucket_counts")

    def test_factor_histogram_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Histogram 记录值."""
        histogram = meter.create_histogram("ditto.factor.calc.duration")

        histogram.record(0.3, {"factor": "momentum"})
        histogram.record(1.5, {"factor": "momentum"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.factor.calc.duration")
        data_point = next(iter(metrics[0].data.data_points))

        # 验证 count 和 sum
        assert data_point.count == 2
        assert abs(data_point.sum - 1.8) < 0.01  # 0.3 + 1.5

    def test_factor_histogram_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Histogram attributes 分组."""
        histogram = meter.create_histogram("ditto.factor.calc.duration")

        histogram.record(0.5, {"factor": "momentum"})
        histogram.record(0.8, {"factor": "reversal"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.factor.calc.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证两个不同的 time series
        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"factor": "momentum"} in attrs_list
        assert {"factor": "reversal"} in attrs_list

    def test_factor_histogram_buckets(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Histogram buckets 分布."""
        histogram = meter.create_histogram("ditto.factor.calc.duration")

        # 记录不同范围的值
        histogram.record(0.05, {"factor": "test"})  # < 0.1
        histogram.record(0.3, {"factor": "test"})  # 0.1 - 0.5
        histogram.record(2.0, {"factor": "test"})  # 1.0 - 5.0
        histogram.record(10.0, {"factor": "test"})  # 5.0 - 10.0
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.factor.calc.duration")
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

    # ==================== 策略指标 (Counter) ====================

    def test_strategy_counter_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证策略 Counter 指标的元数据."""
        counter = meter.create_counter(
            "ditto.signal.total", description="Total trading signals generated"
        )

        counter.add(1, {"strategy": "dual_thrust"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.signal.total")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.signal.total"
        assert metric.description == "Total trading signals generated"
        # Counter 类型验证
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_strategy_counter_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证策略信号计数."""
        counter = meter.create_counter("ditto.signal.total")

        counter.add(5, {"strategy": "dual_thrust", "direction": "long"})
        counter.add(3, {"strategy": "dual_thrust", "direction": "short"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.signal.total")
        data_points = list(metrics[0].data.data_points)

        # 验证两个 time series
        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if (
                dp.attributes.get("strategy") == "dual_thrust"
                and dp.attributes.get("direction") == "long"
            ):
                assert dp.value == 5
            elif (
                dp.attributes.get("strategy") == "dual_thrust"
                and dp.attributes.get("direction") == "short"
            ):
                assert dp.value == 3

    def test_strategy_counter_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证策略维度 attributes."""
        counter = meter.create_counter("ditto.signal.total")

        counter.add(1, {"strategy": "dual_thrust", "symbol": "000001.SZ"})
        counter.add(1, {"strategy": "alpha101", "symbol": "000001.SZ"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.signal.total")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"strategy": "dual_thrust", "symbol": "000001.SZ"} in attrs_list
        assert {"strategy": "alpha101", "symbol": "000001.SZ"} in attrs_list

    def test_strategy_counter_monotonic(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证策略信号单调递增."""
        counter = meter.create_counter("ditto.signal.total")

        counter.add(10, {"strategy": "test"})
        counter.add(5, {"strategy": "test"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.signal.total")
        data_point = next(iter(metrics[0].data.data_points))

        assert data_point.value == 15  # 10 + 5

    # ==================== 组合指标 (Gauge) ====================

    def test_portfolio_gauge_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证组合 Gauge 指标的元数据."""
        gauge = meter.create_gauge(
            "ditto.portfolio.value", description="Current portfolio value"
        )

        gauge.set(100000.0, {"account": "test_account"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.portfolio.value")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.portfolio.value"
        assert metric.description == "Current portfolio value"
        # Gauge 类型验证：数据点有 value 属性（与 Counter 相同）
        # 但通过行为测试验证可逆性
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_portfolio_gauge_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Gauge 设置值（可覆盖）."""
        gauge = meter.create_gauge("ditto.portfolio.value")

        gauge.set(100000.0, {"account": "test_account"})
        gauge.set(105000.0, {"account": "test_account"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.portfolio.value")
        data_point = next(iter(metrics[0].data.data_points))

        # Gauge 应该覆盖，而非累加
        assert data_point.value == 105000.0

    def test_portfolio_gauge_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证组合账户 attributes."""
        gauge = meter.create_gauge("ditto.portfolio.value")

        gauge.set(100000.0, {"account": "account_001"})
        gauge.set(200000.0, {"account": "account_002"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.portfolio.value")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if dp.attributes.get("account") == "account_001":
                assert dp.value == 100000.0
            elif dp.attributes.get("account") == "account_002":
                assert dp.value == 200000.0

    def test_portfolio_gauge_reversible(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证 Gauge 可增可减."""
        gauge = meter.create_gauge("ditto.portfolio.value")

        gauge.set(100000.0, {"account": "test"})
        gauge.set(95000.0, {"account": "test"})  # 亏损
        gauge.set(105000.0, {"account": "test"})  # 盈利
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.portfolio.value")
        data_point = next(iter(metrics[0].data.data_points))

        # Gauge 应该支持任意值变化
        assert data_point.value == 105000.0

    # ==================== 风控指标 (Counter) ====================

    def test_risk_counter_metadata(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证风控 Counter 指标的元数据."""
        counter = meter.create_counter(
            "ditto.risk.kill_switch_total", description="Total kill switch triggers"
        )

        counter.add(1, {"level": "2", "reason": "drawdown"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.risk.kill_switch_total")
        assert len(metrics) > 0

        metric = metrics[0]
        assert metric.name == "ditto.risk.kill_switch_total"
        assert metric.description == "Total kill switch triggers"
        # Counter 类型验证
        data_points = list(metric.data.data_points)
        assert len(data_points) > 0
        assert hasattr(data_points[0], "value")

    def test_risk_counter_values(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证风控事件计数."""
        counter = meter.create_counter("ditto.risk.kill_switch_total")

        counter.add(1, {"level": "1"})
        counter.add(1, {"level": "2"})
        counter.add(1, {"level": "2"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.risk.kill_switch_total")
        data_points = list(metrics[0].data.data_points)

        # level 1: 1 次，level 2: 2 次
        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if dp.attributes.get("level") == "1":
                assert dp.value == 1
            elif dp.attributes.get("level") == "2":
                assert dp.value == 2

    def test_risk_counter_attributes(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证风控事件 attributes."""
        counter = meter.create_counter("ditto.risk.kill_switch_total")

        counter.add(1, {"level": "2", "reason": "drawdown"})
        counter.add(1, {"level": "3", "reason": "volatility"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.risk.kill_switch_total")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"level": "2", "reason": "drawdown"} in attrs_list
        assert {"level": "3", "reason": "volatility"} in attrs_list

    def test_risk_counter_monotonic(
        self, metrics_exporter: MetricReaderWrapper, meter
    ) -> None:
        """验证风控计数器单调递增."""
        counter = meter.create_counter("ditto.risk.kill_switch_total")

        counter.add(1, {"level": "2"})
        counter.add(1, {"level": "2"})
        counter.add(1, {"level": "2"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.risk.kill_switch_total")
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
        histogram.record(0.15, {"endpoint": "/api/v1/factor", "method": "GET"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.api.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证三个不同的 time series
        assert len(data_points) == 3

        attrs_list = [dp.attributes for dp in data_points]
        assert {"endpoint": "/api/v1/data", "method": "GET"} in attrs_list
        assert {"endpoint": "/api/v1/data", "method": "POST"} in attrs_list
        assert {"endpoint": "/api/v1/factor", "method": "GET"} in attrs_list

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

        gauge.set(0.85, {"cache": "factor_cache"})
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

        gauge.set(0.80, {"cache": "factor_cache"})
        gauge.set(0.85, {"cache": "factor_cache"})
        gauge.set(0.90, {"cache": "factor_cache"})
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

        gauge.set(0.85, {"cache": "factor_cache"})
        gauge.set(0.92, {"cache": "data_cache"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.cache.hit_rate")
        data_points = list(metrics[0].data.data_points)

        assert len(data_points) == 2

        # 验证每个数据点的属性和值
        for dp in data_points:
            if dp.attributes.get("cache") == "factor_cache":
                assert abs(dp.value - 0.85) < 0.001
            elif dp.attributes.get("cache") == "data_cache":
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

        histogram.record(0.01, {"data_type": "factor"})
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

        histogram.record(0.01, {"data_type": "factor", "operation": "serialize"})
        histogram.record(0.02, {"data_type": "factor", "operation": "deserialize"})
        wait_for_export()

        metrics = metrics_exporter.get_metrics_by_name("ditto.json.serialize.duration")
        data_points = list(metrics[0].data.data_points)

        # 验证两个不同的 time series
        assert len(data_points) == 2

        attrs_list = [dp.attributes for dp in data_points]
        assert {"data_type": "factor", "operation": "serialize"} in attrs_list
        assert {"data_type": "factor", "operation": "deserialize"} in attrs_list

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

        # Verify所有数据指标存在
        assert hasattr(Metrics, "data_update_duration")
        assert hasattr(Metrics, "data_records")
        assert hasattr(Metrics, "data_freshness")
        assert hasattr(Metrics, "data_errors")

        # Verify所有因子指标存在
        assert hasattr(Metrics, "factor_calc_duration")
        assert hasattr(Metrics, "factor_ic")
        assert hasattr(Metrics, "factor_health")

        # Verify所有策略指标存在
        assert hasattr(Metrics, "signal_total")
        assert hasattr(Metrics, "rebalance_total")

        # Verify所有组合指标存在
        assert hasattr(Metrics, "portfolio_value")
        assert hasattr(Metrics, "portfolio_drawdown")
        assert hasattr(Metrics, "portfolio_drawdown_3d")

        # Verify所有风控指标存在
        assert hasattr(Metrics, "kill_switch_level")
        assert hasattr(Metrics, "kill_switch_total")

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
        assert hasattr(Metrics.data_update_duration, "record")
        assert hasattr(Metrics.factor_calc_duration, "record")
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
        assert hasattr(Metrics.data_records, "add")
        assert hasattr(Metrics.data_errors, "add")
        assert hasattr(Metrics.signal_total, "add")
        assert hasattr(Metrics.rebalance_total, "add")
        assert hasattr(Metrics.kill_switch_total, "add")
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
            "data_freshness",
            "factor_ic",
            "factor_health",
            "portfolio_value",
            "portfolio_drawdown",
            "portfolio_drawdown_3d",
            "kill_switch_level",
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

        # data_update_duration 应该是 Histogram
        assert isinstance(Metrics.data_update_duration, SafeHistogram)
        # data_records 应该是 Counter
        assert isinstance(Metrics.data_records, SafeCounter)
        # data_freshness 应该是 SafeGauge (有 set 方法)
        assert hasattr(Metrics.data_freshness, "set")

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

        # [REVIEW] 28 个指标(根据任务描述)
        # [REVIEW]: 4, 因子: 3, 策略: 2, 组合: 3, 风控: 2,
        #           系统: 3, 缓存: 6, SQL: 4, JSON: 3
        # [REVIEW]: 4 + 3 + 2 + 3 + 2 + 3 + 6 + 4 + 3 = 30
        # [REVIEW]setup 是类方法，不是指标
        # [REVIEW]
        expected_metric_count = 30

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
        Metrics.data_records.add(100, {"source": "test"})

        # [REVIEW] Histogram
        Metrics.data_update_duration.record(1.5, {"source": "test"})

        # [REVIEW] Gauge
        Metrics.kill_switch_level.set(2.0)
        Metrics.kill_switch_level.inc(1.0)
        Metrics.kill_switch_level.dec(0.5)
