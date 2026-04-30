"""
测试辅助模块单元测试.

测试 reset_for_testing(), get_recorded_spans(), get_recorded_metrics() 函数.

这是单元测试，使用 Mock 隔离外部依赖.
"""

from unittest.mock import MagicMock, patch

import pytest
from ditto_platform.foundation.observability import testing


@pytest.mark.unit
class TestResetForTesting:
    """测试 reset_for_testing() 函数."""

    @patch("ditto_platform.foundation.observability.testing.tracing.reset_tracing")
    @patch("ditto_platform.foundation.observability.testing.metrics.reset_metrics")
    def test_reset_for_testing_calls_both_resets(
        self, mock_reset_metrics, mock_reset_tracing
    ) -> None:
        """测试 reset_for_testing 调用 tracing 和 metrics 的 reset 方法."""
        testing.reset_for_testing()

        mock_reset_tracing.assert_called_once()
        mock_reset_metrics.assert_called_once()

    @patch("ditto_platform.foundation.observability.testing.tracing.reset_tracing")
    @patch("ditto_platform.foundation.observability.testing.metrics.reset_metrics")
    def test_reset_for_testing_returns_none(
        self, mock_reset_metrics, mock_reset_tracing
    ) -> None:
        """测试 reset_for_testing 返回 None."""
        result = testing.reset_for_testing()
        assert result is None


@pytest.mark.unit
class TestGetRecordedSpans:
    """测试 get_recorded_spans() 函数."""

    @patch(
        "ditto_platform.foundation.observability.testing.tracing.get_in_memory_exporter"
    )
    def test_get_recorded_spans_with_exporter(self, mock_get_exporter) -> None:
        """测试有 exporter 时返回 spans."""
        # 创建 mock exporter 和 mock spans
        mock_exporter = MagicMock()
        mock_span1 = MagicMock(name="span1")
        mock_span2 = MagicMock(name="span2")
        mock_exporter.get_finished_spans.return_value = [mock_span1, mock_span2]

        mock_get_exporter.return_value = mock_exporter

        result = testing.get_recorded_spans()

        assert result == [mock_span1, mock_span2]
        mock_exporter.get_finished_spans.assert_called_once()

    @patch(
        "ditto_platform.foundation.observability.testing.tracing.get_in_memory_exporter"
    )
    def test_get_recorded_spans_with_empty_exporter(self, mock_get_exporter) -> None:
        """测试 exporter 返回空列表."""
        mock_exporter = MagicMock()
        mock_exporter.get_finished_spans.return_value = []
        mock_get_exporter.return_value = mock_exporter

        result = testing.get_recorded_spans()

        assert result == []

    @patch(
        "ditto_platform.foundation.observability.testing.tracing.get_in_memory_exporter"
    )
    def test_get_recorded_spans_without_exporter(self, mock_get_exporter) -> None:
        """测试没有 exporter 时返回空列表."""
        mock_get_exporter.return_value = None

        result = testing.get_recorded_spans()

        assert result == []


@pytest.mark.unit
class TestGetRecordedMetrics:
    """测试 get_recorded_metrics() 函数."""

    @patch(
        "ditto_platform.foundation.observability.testing.metrics.get_in_memory_reader"
    )
    def test_get_recorded_metrics_with_reader(self, mock_get_reader) -> None:
        """测试有 reader 时返回指标数据."""
        mock_reader = MagicMock()
        mock_reader.get_metrics_data.return_value = MagicMock()
        mock_get_reader.return_value = mock_reader

        result = testing.get_recorded_metrics()

        assert result == {"metrics_recorded": True}
        mock_reader.get_metrics_data.assert_called_once()

    @patch(
        "ditto_platform.foundation.observability.testing.metrics.get_in_memory_reader"
    )
    def test_get_recorded_metrics_without_reader(self, mock_get_reader) -> None:
        """测试没有 reader 时返回空字典."""
        mock_get_reader.return_value = None

        result = testing.get_recorded_metrics()

        assert result == {}

    @patch(
        "ditto_platform.foundation.observability.testing.metrics.get_in_memory_reader"
    )
    def test_get_recorded_metrics_with_none_data(self, mock_get_reader) -> None:
        """测试 reader 返回 None 时返回空字典."""
        mock_reader = MagicMock()
        mock_reader.get_metrics_data.return_value = None
        mock_get_reader.return_value = mock_reader

        result = testing.get_recorded_metrics()

        assert result == {}
