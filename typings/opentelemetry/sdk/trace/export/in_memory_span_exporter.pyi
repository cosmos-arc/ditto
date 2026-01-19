"""OpenTelemetry InMemorySpanExporter stub."""

from typing import Any

class ReadableSpan:
    """SDK 层的可读 Span."""

    name: str
    context: Any
    parent: Any
    start_time: int
    end_time: int
    attributes: dict[str, Any]

class InMemorySpanExporter:
    """In-memory span exporter for testing."""

    def __init__(self) -> None: ...
    def get_finished_spans(self) -> tuple[ReadableSpan, ...]: ...
    def clear(self) -> None: ...
