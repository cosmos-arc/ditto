"""OpenTelemetry SDK Trace stub."""

from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import ReadOnlySpan


class ReadableSpan(ReadOnlySpan):
    """SDK 层的可读 Span 实现."""


class TracerProvider:
    """SDK TracerProvider."""

    def __init__(self, resource: Resource) -> None: ...

    def get_tracer(self, name: str, **kwargs: Any) -> Any: ...

    def add_span_processor(self, processor: Any) -> None: ...


class SimpleSpanProcessor:
    """Simple span processor."""

    def __init__(self, exporter: Any) -> None: ...
