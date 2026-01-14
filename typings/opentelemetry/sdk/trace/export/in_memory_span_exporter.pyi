"""OpenTelemetry InMemorySpanExporter stub."""

from typing import Any


class InMemorySpanExporter:
    """In-memory span exporter for testing."""

    def __init__(self) -> None: ...

    def get_finished_spans(self) -> list[Any]: ...

    def clear(self) -> None: ...
