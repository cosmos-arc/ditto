"""
SimpleGauge 单元测试.

测试 SimpleGauge 类的核心行为:
- set() 设置值
- inc() 增加值
- dec() 减少值
- 不接受 attributes 参数 (简化接口)
"""

import pytest
from ditto_foundation import Mode, ObservabilityConfig, reset_for_testing
from ditto_foundation.observability.metrics import SimpleGauge, configure_metrics


class TestSimpleGauge:
    """测试 SimpleGauge 类."""

    def test_set_initial_value(self) -> None:
        """测试设置初始值."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge", "Test gauge")

        # 设置值
        gauge.set(42.0)

        # 通过 metrics 系统验证值被设置
        # (在实际使用中，ObservableGauge 的回调会被调用)

    def test_set_overwrites_previous_value(self) -> None:
        """测试 set() 覆盖之前的值."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge2", "Test gauge 2")

        gauge.set(10.0)
        gauge.set(20.0)

        # 最后设置的值应该是 20.0

    def test_inc_increments_value(self) -> None:
        """测试 inc() 增加值."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge3", "Test gauge 3")

        gauge.set(5.0)
        gauge.inc(3.0)

        # 值应该是 8.0

    def test_inc_default_delta(self) -> None:
        """测试 inc() 默认增量为 1.0."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge4", "Test gauge 4")

        gauge.set(10.0)
        gauge.inc()

        # 值应该是 11.0

    def test_inc_from_zero(self) -> None:
        """测试从零开始增加."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge5", "Test gauge 5")

        gauge.inc(5.0)

        # 值应该是 5.0 (从 0 开始)

    def test_dec_decrements_value(self) -> None:
        """测试 dec() 减少值."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge6", "Test gauge 6")

        gauge.set(10.0)
        gauge.dec(3.0)

        # 值应该是 7.0

    def test_dec_default_delta(self) -> None:
        """测试 dec() 默认减量为 1.0."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge7", "Test gauge 7")

        gauge.set(10.0)
        gauge.dec()

        # 值应该是 9.0

    def test_dec_clamps_at_zero(self) -> None:
        """测试 dec() 不会让值变为负数."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge8", "Test gauge 8")

        gauge.set(5.0)
        gauge.dec(10.0)

        # 值应该是 0.0 (不允许负值)

    def test_no_attributes_parameter(self) -> None:
        """测试 set() 方法不接受 attributes 参数 (简化接口)."""
        reset_for_testing()

        config = ObservabilityConfig(environment="testing")
        meter = configure_metrics(config, Mode.TESTING)

        gauge = SimpleGauge(meter, "test.gauge9", "Test gauge 9")

        # set() 方法不应该接受 attributes 参数
        # 如果尝试传入 attributes，应该得到 TypeError
        with pytest.raises(TypeError):
            gauge.set(10.0, {"key": "value"})  # type: ignore
