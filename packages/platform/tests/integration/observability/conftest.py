"""
可观测性集成测试 Fixtures.

提供内存 MetricReader 和相关的 pytest fixtures；每例前后重置 ditto 侧
注册表状态并恢复 OTel API 进程级全局，保证状态不跨例、跨 owner 泄漏.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, cast

import opentelemetry.metrics._internal as otel_metrics_internal
import pytest
from opentelemetry import trace as otel_trace_module
from opentelemetry.metrics import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import TracerProvider

# serial 由根 layering 规则按 tests/integration 目录赋予；conftest 的
# pytestmark 声明从不生效，已删除该 no-op（#330 B1）。


class _OnceFlag(Protocol):
    """OTel ``Once`` 的最小可变形状（仅 ``_done`` 标志位）."""

    _done: bool


class _TraceApiGlobals(Protocol):
    """``opentelemetry.trace`` 私有 provider 全局的真实模块形状.

    仓库 ``typings/opentelemetry/trace.pyi`` 窄 stub 未声明私有全局；
    运行时加载的是 uv.lock 钉住的真实包（#348），cast 收窄后符号
    漂移仍会在首个属性访问处响亮失败（AttributeError）.
    """

    _TRACER_PROVIDER: TracerProvider | None
    _TRACER_PROVIDER_SET_ONCE: _OnceFlag


# stub 不声明 _TRACER_PROVIDER/_TRACER_PROVIDER_SET_ONCE；cast 安全因为
# 运行时模块即 site-packages 真实 opentelemetry.trace（py.typed 包）.
otel_trace = cast("_TraceApiGlobals", otel_trace_module)


def _snapshot_otel_api_globals() -> dict[str, Any]:
    """快照 OTel API 进程级 provider 全局（#348）.

    ``set_tracer_provider``/``set_meter_provider`` 是 once-only 写且无公开
    撤销入口；生产路径测试会写入真实全局。快照/恢复走 SDK 私有符号——
    版本由 uv.lock 钉住，升级后若符号漂移会在此处响亮失败。trace 全局
    在 ``opentelemetry.trace``，metrics 全局在 ``_internal`` 子模块，且
    metrics 的 proxy 持有已绑定 meter 状态，需一并恢复。
    """
    metrics_proxy = otel_metrics_internal._PROXY_METER_PROVIDER
    return {
        "tracer_provider": otel_trace._TRACER_PROVIDER,
        "tracer_set": otel_trace._TRACER_PROVIDER_SET_ONCE._done,
        "meter_provider": otel_metrics_internal._METER_PROVIDER,
        "meter_set": otel_metrics_internal._METER_PROVIDER_SET_ONCE._done,
        "proxy_meter_provider": metrics_proxy._real_meter_provider,
        "proxy_meters": list(metrics_proxy._meters),
    }


def _detach_otel_api_globals() -> None:
    """摘下当前 OTel API 全局（#348）.

    setup 侧 reset 的 ``shutdown()`` 会关闭当时已安装的全局 provider——
    先摘下再 reset，外来 provider 保持存活，teardown 恢复引用而非恢复
    已死对象；同时把 metrics proxy 的累积 meter 列表换成新表，树内
    ``set_meter_provider`` 的 on_set 绑定只作用于新表，不污染外来
    proxy meter。trace 侧 ``ProxyTracer`` 的粘性绑定不可枚举，残留
    窗口 = 外来被插桩代码在本树测试执行期间绑定测试 provider（当前
    不存在该调用路径）。
    """
    otel_trace._TRACER_PROVIDER = None
    otel_trace._TRACER_PROVIDER_SET_ONCE._done = False
    otel_metrics_internal._METER_PROVIDER = None
    otel_metrics_internal._METER_PROVIDER_SET_ONCE._done = False
    metrics_proxy = otel_metrics_internal._PROXY_METER_PROVIDER
    metrics_proxy._real_meter_provider = None
    metrics_proxy._meters = []


def _restore_otel_api_globals(snapshot: dict[str, Any]) -> None:
    """恢复 OTel API 进程级 provider 全局到快照值."""
    otel_trace._TRACER_PROVIDER = snapshot["tracer_provider"]
    otel_trace._TRACER_PROVIDER_SET_ONCE._done = snapshot["tracer_set"]
    otel_metrics_internal._METER_PROVIDER = snapshot["meter_provider"]
    otel_metrics_internal._METER_PROVIDER_SET_ONCE._done = snapshot["meter_set"]
    metrics_proxy = otel_metrics_internal._PROXY_METER_PROVIDER
    metrics_proxy._real_meter_provider = snapshot["proxy_meter_provider"]
    metrics_proxy._meters = snapshot["proxy_meters"]


@pytest.fixture(autouse=True)
def reset_observability_state() -> Iterator[None]:
    """每例前后重置可观测性状态并恢复 OTel API 全局.

    只在测试前重置会让树内最后一条用例的脏状态泄漏给同进程后续 owner
    的用例（串行道为单进程），因此 teardown 侧同样重置.
    """
    from ditto_platform.foundation import reset_for_testing

    snapshot = _snapshot_otel_api_globals()
    _detach_otel_api_globals()
    reset_for_testing()
    yield
    reset_for_testing()
    _restore_otel_api_globals(snapshot)


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
def meter_provider(metric_reader: InMemoryMetricReader) -> Iterator[MeterProvider]:
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
