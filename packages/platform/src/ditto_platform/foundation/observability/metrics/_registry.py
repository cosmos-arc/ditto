"""指标注册表和状态管理。"""

from __future__ import annotations

from collections.abc import Mapping

from opentelemetry import metrics
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from ._types import METRIC_DEFINITIONS, MetricDefinition

__all__ = [
    "_HISTOGRAM_BUCKETS",
    "_REGISTERED_METRIC_DEFINITIONS",
    "_REGISTERED_METRIC_NAMES",
    "_MetricsRegistry",
    "_all_metric_definitions",
    "_check_duplicate_metric_definition",
    "_normalize_metric_definition",
    "_platform_definitions_by_instrument",
    "_platform_definitions_by_name",
]


class _MetricsRegistry:
    meter: metrics.Meter | None = None
    in_memory_reader: InMemoryMetricReader | None = None

    @classmethod
    def get_meter(cls) -> metrics.Meter | None:
        return cls.meter

    @classmethod
    def get_in_memory_reader(cls) -> InMemoryMetricReader | None:
        return cls.in_memory_reader

    @classmethod
    def set_meter(cls, meter: metrics.Meter) -> None:
        cls.meter = meter

    @classmethod
    def set_in_memory_reader(cls, reader: InMemoryMetricReader) -> None:
        cls.in_memory_reader = reader

    @classmethod
    def reset(cls) -> None:
        cls.meter = None
        cls.in_memory_reader = None


_HISTOGRAM_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0)

_REGISTERED_METRIC_DEFINITIONS: dict[str, MetricDefinition] = {}
_REGISTERED_METRIC_NAMES: dict[str, MetricDefinition] = {}


def _all_metric_definitions() -> list[MetricDefinition]:
    return [*METRIC_DEFINITIONS, *_REGISTERED_METRIC_DEFINITIONS.values()]


def _normalize_metric_definition(
    definition: MetricDefinition | Mapping[str, str],
) -> MetricDefinition:
    return {
        "name": definition["name"],
        "instrument_name": definition["instrument_name"],
        "type": definition["type"],
        "description": definition["description"],
    }


def _platform_definitions_by_instrument() -> dict[str, MetricDefinition]:
    return {
        definition["instrument_name"]: definition for definition in METRIC_DEFINITIONS
    }


def _platform_definitions_by_name() -> dict[str, MetricDefinition]:
    return {definition["name"]: definition for definition in METRIC_DEFINITIONS}


def _check_duplicate_metric_definition(metric_def: MetricDefinition) -> bool:
    instrument_name = metric_def["instrument_name"]
    name = metric_def["name"]

    by_instrument = {
        **_platform_definitions_by_instrument(),
        **_REGISTERED_METRIC_DEFINITIONS,
    }
    by_name = {
        **_platform_definitions_by_name(),
        **_REGISTERED_METRIC_NAMES,
    }

    if existing := by_instrument.get(instrument_name):
        if existing != metric_def:
            msg = (
                f"Metric instrument {instrument_name!r} already registered with "
                f"different definition {existing!r}"
            )
            raise ValueError(msg)
        return True

    if existing := by_name.get(name):
        msg = (
            f"Metric name {name!r} already registered for instrument "
            f"{existing['instrument_name']!r}"
        )
        raise ValueError(msg)

    return False
