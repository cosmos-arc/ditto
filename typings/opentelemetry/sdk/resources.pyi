"""OpenTelemetry SDK Resources stub."""

from typing import Any


class Resource:
    """Resource for telemetry."""

    @staticmethod
    def create(attributes: dict[str, Any]) -> "Resource": ...
