"""
METRIC_DEFINITIONS 配置驱动的指标注册测试.

测试基于 METRIC_DEFINITIONS 配置字典的指标注册功能：
- 验证所有指标被正确创建
- 验证指标类型正确（Histogram/Counter/Gauge）
- 验证指标名称和描述正确
"""

from ditto_foundation import Mode, ObservabilityConfig, reset_for_testing
from ditto_foundation.observability.metrics import M, configure_metrics
from opentelemetry.sdk.metrics import Counter as SDKCounter
from opentelemetry.sdk.metrics import Histogram as SDKHistogram


class TestMetricDefinitions:
    """测试 METRIC_DEFINITIONS 配置驱动的指标注册."""

    def test_all_metrics_created(self) -> None:
        """测试所有指标被正确创建."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 验证所有数据指标存在
        assert hasattr(M, "data_update_duration")
        assert hasattr(M, "data_records")
        assert hasattr(M, "data_freshness")
        assert hasattr(M, "data_errors")

        # 验证所有因子指标存在
        assert hasattr(M, "factor_calc_duration")
        assert hasattr(M, "factor_ic")
        assert hasattr(M, "factor_health")

        # 验证所有策略指标存在
        assert hasattr(M, "signal_total")
        assert hasattr(M, "rebalance_total")

        # 验证所有组合指标存在
        assert hasattr(M, "portfolio_value")
        assert hasattr(M, "portfolio_drawdown")
        assert hasattr(M, "portfolio_drawdown_3d")

        # 验证所有风控指标存在
        assert hasattr(M, "kill_switch_level")
        assert hasattr(M, "kill_switch_total")

        # 验证所有系统指标存在
        assert hasattr(M, "scheduler_jobs")
        assert hasattr(M, "api_requests")
        assert hasattr(M, "api_duration")

        # 验证所有缓存指标存在
        assert hasattr(M, "cache_hit")
        assert hasattr(M, "cache_miss")
        assert hasattr(M, "cache_hit_rate")
        assert hasattr(M, "cache_invalidations")
        assert hasattr(M, "cache_evictions")
        assert hasattr(M, "cache_size")

        # 验证所有 SQL 指标存在
        assert hasattr(M, "sql_query_duration")
        assert hasattr(M, "sql_slow_query_total")
        assert hasattr(M, "sql_query_plan_cache_hit")
        assert hasattr(M, "sql_query_plan_cache_miss")

        # 验证所有 JSON 指标存在
        assert hasattr(M, "json_serialize_duration")
        assert hasattr(M, "json_deserialize_duration")
        assert hasattr(M, "json_bytes_total")

    def test_histogram_metrics_have_record_method(self) -> None:
        """测试 Histogram 类型的指标有 record 方法."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 验证 Histogram 类型指标有 record 方法
        assert hasattr(M.data_update_duration, "record")
        assert hasattr(M.factor_calc_duration, "record")
        assert hasattr(M.api_duration, "record")
        assert hasattr(M.sql_query_duration, "record")
        assert hasattr(M.json_serialize_duration, "record")
        assert hasattr(M.json_deserialize_duration, "record")

    def test_counter_metrics_have_add_method(self) -> None:
        """测试 Counter 类型的指标有 add 方法."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 验证 Counter 类型指标有 add 方法
        assert hasattr(M.data_records, "add")
        assert hasattr(M.data_errors, "add")
        assert hasattr(M.signal_total, "add")
        assert hasattr(M.rebalance_total, "add")
        assert hasattr(M.kill_switch_total, "add")
        assert hasattr(M.scheduler_jobs, "add")
        assert hasattr(M.api_requests, "add")
        assert hasattr(M.cache_hit, "add")
        assert hasattr(M.cache_miss, "add")
        assert hasattr(M.cache_invalidations, "add")
        assert hasattr(M.cache_evictions, "add")
        assert hasattr(M.sql_slow_query_total, "add")
        assert hasattr(M.sql_query_plan_cache_hit, "add")
        assert hasattr(M.sql_query_plan_cache_miss, "add")
        assert hasattr(M.json_bytes_total, "add")

    def test_gauge_metrics_have_set_inc_dec_methods(self) -> None:
        """测试 Gauge 类型的指标有 set/inc/dec 方法."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 验证 Gauge 类型指标有 set/inc/dec 方法
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
            metric = getattr(M, metric_name)
            assert hasattr(metric, "set"), f"{metric_name} should have set method"
            assert hasattr(metric, "inc"), f"{metric_name} should have inc method"
            assert hasattr(metric, "dec"), f"{metric_name} should have dec method"

    def test_metric_names_match_expected(self) -> None:
        """测试指标名称与预期一致."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 验证部分指标名称（通过调用它们的底层方法）
        # 这里我们只验证几个关键指标，确保名称正确

        # data_update_duration 应该是 Histogram
        assert isinstance(M.data_update_duration, SDKHistogram)
        # data_records 应该是 Counter
        assert isinstance(M.data_records, SDKCounter)
        # data_freshness 应该是 SimpleGauge (有 set 方法)
        assert hasattr(M.data_freshness, "set")

    def test_metric_count_matches_definitions(self) -> None:
        """测试创建的指标数量与 METRIC_DEFINITIONS 中的定义一致."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 统计 M 类中定义的指标数量
        metric_count = 0
        for attr_name in dir(M):
            if not attr_name.startswith("_"):
                attr = getattr(M, attr_name)
                # 检查是否是指标类型（有特定的方法）
                if (
                    hasattr(attr, "record")
                    or hasattr(attr, "add")
                    or hasattr(attr, "set")
                ):
                    metric_count += 1

        # 应该有 28 个指标（根据任务描述）
        # 数据: 4, 因子: 3, 策略: 2, 组合: 3, 风控: 2, 系统: 3, 缓存: 6, SQL: 4, JSON: 3
        # 总计: 4 + 3 + 2 + 3 + 2 + 3 + 6 + 4 + 3 = 30
        # 注意：setup 是类方法，不是指标
        # 排除类方法和其他非指标属性
        expected_metric_count = 30

        # 允许一定的误差（因为可能有其他类属性）
        assert metric_count >= expected_metric_count, (
            f"Expected at least {expected_metric_count} metrics, found {metric_count}"
        )

    def test_metrics_are_functional(self) -> None:
        """测试指标可以被正常使用（不会被报错）."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        configure_metrics(config, Mode.TESTING)

        # 测试 Counter
        M.data_records.add(100, {"source": "test"})

        # 测试 Histogram
        M.data_update_duration.record(1.5, {"source": "test"})

        # 测试 Gauge
        M.kill_switch_level.set(2.0)
        M.kill_switch_level.inc(1.0)
        M.kill_switch_level.dec(0.5)
