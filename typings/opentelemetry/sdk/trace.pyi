"""OpenTelemetry SDK Trace stub."""

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

    def get_span_context(self) -> SpanContext: ...


class ReadOnlySpan(Span):
    """只读 Span."""

    name: str
    context: SpanContext
    parent: SpanContext | None
    start_time: int
    end_time: int
    attributes: dict[str, Any]


class ReadableSpan(ReadOnlySpan):
    """SDK 层的可读 Span 实现."""


class TracerProvider:
    """SDK TracerProvider."""

    def __init__(self, resource: Any) -> None: ...

    def get_tracer(self, name: str, **kwargs: Any) -> Any: ...

    def add_span_processor(self, processor: Any) -> None: ...

    def shutdown(self, timeout_ms: int = 30000) -> None: ...

    def force_flush(self, timeout_ms: int = 30000) -> bool: ...


class SimpleSpanProcessor:
    """Simple span processor."""

    def __init__(self, exporter: Any) -> None: ...
