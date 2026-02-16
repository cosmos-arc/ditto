"""
指标注册表单元测试.

测试 _MetricsRegistry 类的状态管理逻辑.

这是单元测试，使用 Mock Meter 和 InMemoryMetricReader.
"""

from unittest.mock import MagicMock

import pytest
from ditto_infra.foundation.observability.metrics import _MetricsRegistry
from opentelemetry import metrics
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


@pytest.mark.unit
class TestMetricsRegistry:
    """测试 _MetricsRegistry 类."""

    def test_initial_state(self) -> None:
        """测试初始状态."""
        # 重置状态
        _MetricsRegistry.reset()

        assert _MetricsRegistry.get_meter() is None
        assert _MetricsRegistry.get_in_memory_reader() is None

    def test_set_and_get_meter(self) -> None:
        """测试设置和获取 meter."""
        _MetricsRegistry.reset()

        # 创建 mock meter
        mock_meter = MagicMock(spec=metrics.Meter)

        _MetricsRegistry.set_meter(mock_meter)

        assert _MetricsRegistry.get_meter() is mock_meter
        assert _MetricsRegistry.get_meter() is not None

    def test_set_and_get_in_memory_reader(self) -> None:
        """测试设置和获取 in_memory_reader."""
        _MetricsRegistry.reset()

        # 创建 mock reader
        mock_reader = MagicMock(spec=InMemoryMetricReader)

        _MetricsRegistry.set_in_memory_reader(mock_reader)

        assert _MetricsRegistry.get_in_memory_reader() is mock_reader
        assert _MetricsRegistry.get_in_memory_reader() is not None

    def test_reset_clears_meter(self) -> None:
        """测试 reset 清除 meter."""
        _MetricsRegistry.reset()

        mock_meter = MagicMock(spec=metrics.Meter)
        _MetricsRegistry.set_meter(mock_meter)

        assert _MetricsRegistry.get_meter() is not None

        _MetricsRegistry.reset()

        assert _MetricsRegistry.get_meter() is None

    def test_reset_clears_in_memory_reader(self) -> None:
        """测试 reset 清除 in_memory_reader."""
        _MetricsRegistry.reset()

        mock_reader = MagicMock(spec=InMemoryMetricReader)
        _MetricsRegistry.set_in_memory_reader(mock_reader)

        assert _MetricsRegistry.get_in_memory_reader() is not None

        _MetricsRegistry.reset()

        assert _MetricsRegistry.get_in_memory_reader() is None

    def test_multiple_sets_override(self) -> None:
        """测试多次设置会覆盖."""
        _MetricsRegistry.reset()

        mock_meter1 = MagicMock(spec=metrics.Meter)
        mock_meter2 = MagicMock(spec=metrics.Meter)

        _MetricsRegistry.set_meter(mock_meter1)
        assert _MetricsRegistry.get_meter() is mock_meter1

        _MetricsRegistry.set_meter(mock_meter2)
        assert _MetricsRegistry.get_meter() is mock_meter2
        assert _MetricsRegistry.get_meter() is not mock_meter1

    def test_set_both_meter_and_reader(self) -> None:
        """测试同时设置 meter 和 reader."""
        _MetricsRegistry.reset()

        mock_meter = MagicMock(spec=metrics.Meter)
        mock_reader = MagicMock(spec=InMemoryMetricReader)

        _MetricsRegistry.set_meter(mock_meter)
        _MetricsRegistry.set_in_memory_reader(mock_reader)

        assert _MetricsRegistry.get_meter() is mock_meter
        assert _MetricsRegistry.get_in_memory_reader() is mock_reader

    def test_reset_idempotent(self) -> None:
        """测试多次 reset 幂等."""
        _MetricsRegistry.reset()

        mock_meter = MagicMock(spec=metrics.Meter)
        _MetricsRegistry.set_meter(mock_meter)

        # 第一次 reset
        _MetricsRegistry.reset()
        assert _MetricsRegistry.get_meter() is None

        # 第二次 reset 不应该报错
        _MetricsRegistry.reset()
        assert _MetricsRegistry.get_meter() is None

    def test_getter_returns_none_when_not_set(self) -> None:
        """测试未设置时返回 None."""
        _MetricsRegistry.reset()

        # 直接调用 getter 不设置
        meter = _MetricsRegistry.get_meter()
        reader = _MetricsRegistry.get_in_memory_reader()

        assert meter is None
        assert reader is None
