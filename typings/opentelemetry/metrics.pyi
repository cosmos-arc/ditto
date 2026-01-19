"""OpenTelemetry Metrics API stub."""

from typing import Any

class Observation:
    """Metric observation."""

    def __init__(self, value: float, attributes: dict[str, Any]) -> None: ...

class Meter:
    """Meter interface."""

    def create_counter(
        self,
        name: str,
        *,
        description: str = "",
        **kwargs: Any,
    ) -> Counter: ...
    def create_histogram(
        self,
        name: str,
        *,
        description: str = "",
        **kwargs: Any,
    ) -> Histogram: ...
    def create_observable_gauge(
        self,
        name: str,
        callbacks: list[Any],
        *,
        description: str = "",
        **kwargs: Any,
    ) -> Any: ...

class Counter:
    """Counter instrument."""

    def add(self, amount: float, attributes: dict[str, Any] | None = None) -> None: ...

class Histogram:
    """Histogram instrument."""

    def record(
        self, amount: float, attributes: dict[str, Any] | None = None
    ) -> None: ...

class MeterProvider:
    """Meter provider."""

    def shutdown(self, timeout_ms: int = 30000) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...
    def get_meter(self, name: str, **kwargs: Any) -> Meter: ...

def get_meter_provider() -> MeterProvider: ...
def set_meter_provider(provider: MeterProvider) -> None: ...
def get_meter(__name: str, **kwargs: Any) -> Meter: ...
