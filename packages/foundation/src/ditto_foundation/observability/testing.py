"""
测试辅助模块.

提供测试环境中重置和查询可观测性数据的功能.
"""

from typing import Any

# 为了类型检查，导入 ReadableSpan（但在运行时不使用）
from opentelemetry.sdk.trace import ReadableSpan  # type: ignore[unused-import]

from . import metrics, tracing


def reset_for_testing() -> None:
    """重置所有可观测性状态（测试用）."""
    tracing.reset_tracing()
    metrics.reset_metrics()


def get_recorded_spans() -> list[ReadableSpan]:
    """
    获取记录的 Spans（测试用）.

    Returns
    -------
        list[ReadableSpan]: 已完成的 Span 列表

    """
    exporter = tracing.get_in_memory_exporter()
    if exporter is not None:
        return list(exporter.get_finished_spans())
    return []


def get_recorded_metrics() -> dict[str, Any]:
    """
    获取记录的 Metrics（测试用）.

    Returns
    -------
        dict: 指标数据

    """
    # InMemoryMetricReader 的 get_metrics_data() 返回 ResourceMetrics
    # 这是一个复杂的结构，测试中我们只需要验证它不是 None
    reader = metrics.get_in_memory_reader()
    if reader is not None:
        data = reader.get_metrics_data()
        if data is not None:
            return {"metrics_recorded": True}
    return {}
