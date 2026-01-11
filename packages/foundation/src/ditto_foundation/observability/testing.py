"""
测试辅助模块.

提供测试环境中重置和查询可观测性数据的功能.
"""

from typing import Any

from . import metrics, tracing


def reset_for_testing() -> None:
    """重置所有可观测性状态（测试用）."""
    tracing.reset_tracing()
    metrics.reset_metrics()


def get_recorded_spans() -> list[Any]:
    """
    获取记录的 Spans（测试用）.

    Returns
    -------
        list: 已完成的 Span 列表

    """
    if tracing._state.in_memory_exporter is not None:
        return list(tracing._state.in_memory_exporter.get_finished_spans())
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
    if metrics._in_memory_reader is not None:
        data = metrics._in_memory_reader.get_metrics_data()
        if data is not None:
            return {"metrics_recorded": True}
    return {}
