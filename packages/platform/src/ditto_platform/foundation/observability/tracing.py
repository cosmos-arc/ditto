"""链路追踪模块."""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, Sampler, TraceIdRatioBased
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.types import AttributeValue

from .config import ObservabilityConfig

P = ParamSpec("P")
T = TypeVar("T")


class SpanKind(Enum):
    """Transport-neutral span kinds mapped to the OpenTelemetry runtime enum."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class _SamplerCarrier(Protocol):
    """承载 sampler 属性的最小协议。"""

    sampler: Sampler


class _RenamableSpan(Protocol):
    """OpenTelemetry SDK span surface missing from the API package type stub."""

    def update_name(self, name: str) -> None:
        """Replace the operation name of a live span."""
        ...


class _StatusMutableSpan(Protocol):
    """OpenTelemetry status surface omitted by the repository's narrow stub."""

    def set_status(self, status: StatusCode) -> None:
        """Set the semantic terminal status."""
        ...


class _OTelSpanKinds(Protocol):
    """Runtime OTel span-kind values omitted by the repository's narrow stub."""

    INTERNAL: object
    SERVER: object
    CLIENT: object
    PRODUCER: object
    CONSUMER: object


def _otel_span_kind(kind: SpanKind) -> object:
    runtime_kinds = cast(_OTelSpanKinds, vars(trace)["SpanKind"])
    return {
        SpanKind.INTERNAL: runtime_kinds.INTERNAL,
        SpanKind.SERVER: runtime_kinds.SERVER,
        SpanKind.CLIENT: runtime_kinds.CLIENT,
        SpanKind.PRODUCER: runtime_kinds.PRODUCER,
        SpanKind.CONSUMER: runtime_kinds.CONSUMER,
    }[kind]


def _attach_sampler(provider: TracerProvider, sampler: Sampler) -> TracerProvider:
    carrier = cast(_SamplerCarrier, provider)
    carrier.sampler = sampler
    return provider


@dataclass
class TracingState:
    """封装 tracing 全局状态。"""

    tracer: trace.Tracer | None = None
    in_memory_exporter: InMemorySpanExporter | None = None

    def reset(self) -> None:
        self.tracer = None
        if self.in_memory_exporter:
            self.in_memory_exporter.clear()
        self.in_memory_exporter = None


_state = TracingState()


class SpanContext:
    """Span 上下文管理器。"""

    def __init__(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        **attributes: AttributeValue,
    ) -> None:
        self.name = name
        self.kind = kind
        self.attributes = attributes
        self._span: Any = None

    def __enter__(self) -> SpanContext:
        if _state.tracer is None:
            return self

        self._span = _state.tracer.start_as_current_span(
            self.name,
            kind=_otel_span_kind(self.kind),
        )
        actual_span = self._span.__enter__()
        for key, value in self.attributes.items():
            actual_span.set_attribute(key, value)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._span is None:
            return

        if exc_type is not None and exc_val is not None:
            current = trace.get_current_span()
            if current.is_recording():
                current.record_exception(exc_val)
        self._span.__exit__(exc_type, exc_val, exc_tb)

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        current = trace.get_current_span()
        if current.is_recording():
            current.set_attribute(key, value)

    def set_status(self, status: StatusCode) -> None:
        current = trace.get_current_span()
        if current.is_recording():
            cast(_StatusMutableSpan, current).set_status(status)

    def record_exception(self, error: BaseException) -> None:
        """Record a handled exception on the live span."""
        current = trace.get_current_span()
        if current.is_recording():
            current.record_exception(error)

    def update_name(self, name: str) -> None:
        """Update a live span name once a late-bound operation name is known."""
        current = trace.get_current_span()
        if current.is_recording():
            cast(_RenamableSpan, current).update_name(name)


def configure_tracing(config: ObservabilityConfig) -> trace.Tracer:
    """配置 OTel Tracing。"""
    effective = config.get_effective_config()
    resource = Resource.create({"service.name": config.service_name})

    if not effective.tracing_enabled:
        provider = _attach_sampler(
            TracerProvider(resource=resource),
            ParentBased(TraceIdRatioBased(0.0)),
        )
        trace.set_tracer_provider(provider)
        _state.tracer = trace.get_tracer(config.service_name)
        return _state.tracer

    if effective.pytest_running and not effective.assertions_enabled:
        _state.tracer = trace.get_tracer(__name__)
        return _state.tracer

    if effective.pytest_running and effective.assertions_enabled:
        _state.in_memory_exporter = InMemorySpanExporter()
        provider = _attach_sampler(
            TracerProvider(resource=resource),
            ParentBased(TraceIdRatioBased(effective.tracing_sample_rate)),
        )
        provider.add_span_processor(SimpleSpanProcessor(_state.in_memory_exporter))
        tracer = provider.get_tracer(__name__)
        _state.tracer = tracer
        return tracer

    provider = _attach_sampler(
        TracerProvider(resource=resource),
        ParentBased(TraceIdRatioBased(effective.tracing_sample_rate)),
    )

    if effective.tracing_exporter == "otlp":
        exporter = OTLPSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _state.tracer = trace.get_tracer(config.service_name)

    return _state.tracer


def span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    **attributes: AttributeValue,
) -> SpanContext:
    """创建 Span 上下文管理器。"""
    return SpanContext(name, kind=kind, **attributes)


def traced(operation: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """为函数添加 tracing 装饰器。"""

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with span(operation, function=func.__name__):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def get_trace_id() -> str:
    """获取当前 Trace ID（无则返回空字符串）。"""
    if _state.tracer is None:
        return ""

    current = trace.get_current_span()
    ctx = current.get_span_context()
    if ctx.is_valid:
        return str(uuid.UUID(int=ctx.trace_id))
    return ""


def get_span_id() -> str:
    """获取当前 Span ID（无则返回空字符串）。"""
    if _state.tracer is None:
        return ""

    current = trace.get_current_span()
    ctx = current.get_span_context()
    if ctx.is_valid:
        return format(ctx.span_id, "016x")
    return ""


def reset_tracing() -> None:
    """重置 tracing 状态。"""
    _state.reset()


def get_in_memory_exporter() -> InMemorySpanExporter | None:
    """获取内存 span exporter（用于测试）。"""
    return _state.in_memory_exporter


__all__ = [
    "SpanKind",
    "StatusCode",
    "configure_tracing",
    "get_in_memory_exporter",
    "get_span_id",
    "get_trace_id",
    "reset_tracing",
    "span",
    "traced",
]
