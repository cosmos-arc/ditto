"""
可观测性集成测试 Fixtures.

提供内存 MetricReader 和相关的 pytest fixtures.
"""

from __future__ import annotations

import time

import pytest
from opentelemetry.metrics import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

# 集成测试串行执行，避免全局状态污染
pytestmark = pytest.mark.serial


@pytest.fixture(autouse=True)
def reset_observability_state() -> None:
    """在每个测试前重置观察性系统状态，避免测试隔离问题."""
    from ditto_infra.foundation import reset_for_testing

    reset_for_testing()


class MetricReaderWrapper:
    """
    InMemoryMetricReader 包装器，提供便捷的查询接口.
    """

    def __init__(self, reader: InMemoryMetricReader) -> None:
        """初始化包装器."""
        self._reader = reader

    def get_metrics_by_name(self, name: str) -> list:
        """
        按指标名称查询已导出的指标.

        Args:
            name: 指标名称

        Returns:
            list: 匹配的指标对象列表
        """
        metrics_data = self._reader.get_metrics_data()
        if not metrics_data:
            return []

        results = []
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    if metric.name == name:
                        results.append(metric)
        return results

    def get_all_metrics(self) -> list:
        """
        获取所有已导出的指标.

        Returns:
            list: 所有指标对象
        """
        metrics_data = self._reader.get_metrics_data()
        if not metrics_data:
            return []

        results = []
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    results.append(metric)
        return results


@pytest.fixture
def metric_reader() -> InMemoryMetricReader:
    """
    提供内存 MetricReader fixture.

    Returns
    -------
        InMemoryMetricReader: 内存 MetricReader 实例
    """
    reader = InMemoryMetricReader()
    return reader
    # shutdown 由 MeterProvider 负责


@pytest.fixture
def meter_provider(metric_reader: InMemoryMetricReader) -> MeterProvider:
    """
    提供配置好的 MeterProvider fixture.

    使用 InMemoryMetricReader 支持真实的指标导出流程验证.

    Args:
        metric_reader: 内存 MetricReader fixture

    Returns:
        MeterProvider: 配置好的 MeterProvider
    """
    # 创建资源标识
    resource = Resource.create({"service.name": "ditto-test"})

    # 创建 Duration Histogram Views（与生产环境一致）
    duration_histogram_views = [
        View(
            instrument_name="*duration",
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0)
            ),
        )
    ]

    provider = MeterProvider(
        metric_readers=[metric_reader],
        resource=resource,
        views=duration_histogram_views,
    )

    yield provider

    # 清理
    provider.shutdown()


@pytest.fixture
def meter(meter_provider: MeterProvider) -> Meter:
    """
    提供 Meter fixture（便捷访问）.

    Args:
        meter_provider: MeterProvider fixture

    Returns:
        Meter: Meter 实例
    """
    return meter_provider.get_meter(__name__)


@pytest.fixture
def metrics_exporter(metric_reader: InMemoryMetricReader) -> MetricReaderWrapper:
    """
    提供指标查询接口 fixture.

    Args:
        metric_reader: 内存 MetricReader fixture

    Returns:
        MetricReaderWrapper: 包装器实例
    """
    return MetricReaderWrapper(metric_reader)


def wait_for_export() -> None:
    """
    等待指标导出完成.

    InMemoryMetricReader 是同步的，指标立即可用.
    但为了模拟真实导出场景，保留一小段延迟.
    """
    time.sleep(0.05)  # 短暂延迟
