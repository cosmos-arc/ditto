"""
追踪模块.

基于 OpenTelemetry 的分布式追踪实现, 支持 span 管理和 trace_id 生成.
"""

import functools
import uuid
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from .config import Mode, ObservabilityConfig

P = ParamSpec("P")
T = TypeVar("T")

# 全局变量
_tracer: trace.Tracer | None = None
_in_memory_exporter: InMemorySpanExporter | None = None
_current_span: trace.Span | None = None


class SpanContext:
    """Span 上下文管理器."""

    def __init__(self, name: str, **attributes: Any) -> None:
        """
        初始化 Span 上下文管理器.

        Args:
        ----
            name: Span 名称
            **attributes: Span 属性

        """
        self.name = name
        self.attributes = attributes
        self._span: trace.Span | None = None

    def __enter__(self) -> "SpanContext":
        """进入上下文，启动 span."""
        global _current_span

        if _tracer is None:
            return self

        # 使用 start_as_current_span 来正确传播 trace 上下文
        # 返回的是 context manager
        self._span = _tracer.start_as_current_span(self.name)
        # 进入 span 上下文，获取实际的 Span 对象
        actual_span = self._span.__enter__()
        # 设置属性
        for key, value in self.attributes.items():
            actual_span.set_attribute(key, str(value))
        # 存储实际的 Span 对象
        _current_span = actual_span
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """退出上下文，结束 span."""
        global _current_span

        if self._span is None:
            return

        if exc_type is not None and _current_span is not None:
            # 记录异常
            _current_span.record_exception(exc_val)
        # 退出 context manager
        self._span.__exit__(exc_type, exc_val, exc_tb)
        _current_span = None

    def set_attribute(self, key: str, value: Any) -> None:
        """
        设置 Span 属性.

        Args:
        ----
            key: 属性名
            value: 属性值

        """
        global _current_span
        if _current_span is not None:
            _current_span.set_attribute(key, str(value))

    def set_status(self, status: str) -> None:
        """
        设置 Span 状态.

        Args:
        ----
            status: 状态描述

        """
        if self._span is not None:
            self._span.set_attribute("status", status)


def configure_tracing(config: ObservabilityConfig, mode: Mode) -> trace.Tracer:
    """
    配置 OTel Tracing.

    Args:
    ----
        config: 可观测性配置
        mode: 运行模式

    Returns:
    -------
        trace.Tracer: 配置好的 Tracer 实例

    """
    global _tracer, _in_memory_exporter

    # 静默模式：使用 NoOp Tracer
    if mode == Mode.TESTING:
        _tracer = trace.get_tracer(__name__)
        return _tracer

    # 资源定义
    resource = Resource.create({"service.name": config.service_name})

    # TESTING_WITH_ASSERTIONS：使用 InMemory Exporter
    if mode == Mode.TESTING_WITH_ASSERTIONS:
        _in_memory_exporter = InMemorySpanExporter()
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))
        # 直接从 provider 获取 tracer，不设置全局 provider
        _tracer = provider.get_tracer(__name__)
        return _tracer

    # PRODUCTION / DEVELOPMENT：标准 TracerProvider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(config.service_name)

    return _tracer


def span(name: str, **attributes: Any) -> SpanContext:
    """
    创建 Span 上下文管理器.

    Args:
    ----
        name: Span 名称
        **attributes: Span 属性

    Returns:
    -------
        SpanContext: Span 上下文管理器

    """
    return SpanContext(name, **attributes)


def traced(operation: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    装饰器：自动创建 Span.

    Args:
    ----
        operation: 操作名称（用作 Span 名称）

    Returns:
    -------
        装饰器函数

    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with span(operation, function=func.__name__):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def get_trace_id() -> str:
    """
    获取当前 trace_id（UUID 格式字符串）.

    Returns
    -------
        str: UUID 格式的 trace_id，如果无效则返回空字符串

    """
    global _current_span, _tracer

    # 优先使用存储的当前 span
    if _current_span is not None:
        span_context = _current_span.get_span_context()
        if span_context.is_valid:
            return str(uuid.UUID(int=span_context.trace_id))

    # 回退到全局获取（用于 production/development 模式）
    if _tracer is None:
        return ""

    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()
    if span_context.is_valid:
        return str(uuid.UUID(int=span_context.trace_id))
    return ""


def get_span_id() -> str:
    """
    获取当前 span_id（16位十六进制）.

    Returns
    -------
        str: 16位十六进制 span_id，如果无效则返回空字符串

    """
    global _current_span, _tracer

    # 优先使用存储的当前 span
    if _current_span is not None:
        span_context = _current_span.get_span_context()
        if span_context.is_valid:
            return format(span_context.span_id, "016x")

    # 回退到全局获取（用于 production/development 模式）
    if _tracer is None:
        return ""

    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()
    if span_context.is_valid:
        return format(span_context.span_id, "016x")
    return ""


def reset_tracing() -> None:
    """重置 Tracing 状态（用于测试）."""
    global _tracer, _in_memory_exporter, _current_span

    _tracer = None
    _current_span = None

    if _in_memory_exporter:
        _in_memory_exporter.clear()
    _in_memory_exporter = None
