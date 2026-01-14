"""
OpenTelemetry Trace API stub.

反映实际的类型层次结构：
- opentelemetry.trace.TracerProvider (API)
- opentelemetry.sdk.trace.TracerProvider (SDK, 继承自 API)
"""

from typing import Any

class SpanContext:
    """Span context."""

    trace_id: int
    span_id: int
    is_valid: bool


class Span:
    """Span interface."""

    def is_recording(self) -> bool: ...

    def set_attribute(self, key: str, value: Any) -> None: ...

    def record_exception(self, exception: BaseException) -> None: ...

    def get_span_context(self) -> SpanContext: ...

    def __enter__(self) -> Span: ...

    def __exit__(self, *args: Any) -> None: ...


class ReadOnlySpan(Span):
    """只读 Span，用于导出和读取已完成的 span."""

    name: str
    context: SpanContext
    parent: SpanContext | None
    start_time: int
    end_time: int
    attributes: dict[str, Any]
    events: list[Any]
    links: list[Any]
    status: Any


# ReadableSpan 是 SDK 层的具体实现，继承自 ReadOnlySpan
class ReadableSpan(ReadOnlySpan):
    """SDK 层的可读 Span 实现."""


class Tracer:
    """Tracer interface."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> Any: ...


# API 层的 TracerProvider
class TracerProvider:
    """API TracerProvider (抽象基类)."""

    def shutdown(self, timeout_ms: int = 30000) -> None: ...

    def force_flush(self, timeout_ms: int = 30000) -> bool: ...

    def get_tracer(self, name: str, **kwargs: Any) -> Tracer: ...


def get_tracer_provider() -> TracerProvider: ...

def set_tracer_provider(provider: Any) -> None: ...

def get_tracer(__name: str, **kwargs: Any) -> Tracer: ...

def get_current_span() -> Span: ...
