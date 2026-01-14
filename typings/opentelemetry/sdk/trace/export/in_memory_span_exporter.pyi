"""OpenTelemetry InMemorySpanExporter stub."""

from typing import Tuple

from opentelemetry.sdk.trace import ReadableSpan


class InMemorySpanExporter:
    """In-memory span exporter for testing."""

    def __init__(self) -> None: ...

    def get_finished_spans(self) -> Tuple[ReadableSpan, ...]: ...

    def clear(self) -> None: ...
