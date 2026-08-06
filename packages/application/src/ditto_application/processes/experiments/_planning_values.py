"""Canonical baseline-value freezing shared by experiment planners."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import NoReturn, cast

from ditto_application.exceptions import AppProcessError

__all__ = [
    "BaselineInputValue",
    "BaselineValue",
    "ExperimentPlanningError",
    "freeze_baseline_mapping",
    "planning_error",
]

type BaselineScalar = None | bool | int | float | str
type BaselineInputValue = (
    BaselineScalar
    | tuple[BaselineInputValue, ...]
    | list[BaselineInputValue]
    | Mapping[str, BaselineInputValue]
)
type BaselineValue = (
    BaselineScalar | tuple[BaselineValue, ...] | Mapping[str, BaselineValue]
)


class ExperimentPlanningError(AppProcessError):
    """Typed failure raised by pure experiment planning."""


def planning_error(
    message: str,
    *,
    code: str = "SPEC_INVALID",
    **details: object,
) -> NoReturn:
    """Raise one stable planning error without transport-layer concerns."""
    raise ExperimentPlanningError(message, details={"code": code, **details})


def _enter_container(value: object, *, field_name: str, active: set[int]) -> int:
    container_id = id(value)
    if container_id in active:
        planning_error(
            f"{field_name} contains a cyclic JSON value",
            reason="cyclic_baseline_descriptor",
            field=field_name,
        )
    active.add(container_id)
    return container_id


def _freeze_baseline_value(
    value: object,
    *,
    field_name: str,
    active: set[int] | None = None,
) -> BaselineValue:
    active_ids: set[int] = set() if active is None else active
    if value is None or type(value) in {bool, int, str}:
        return cast("BaselineScalar", value)
    if type(value) is float:
        if not math.isfinite(value):
            planning_error(
                f"{field_name} must be finite",
                reason="non_finite_baseline_descriptor",
                field=field_name,
            )
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        container_id = _enter_container(
            mapping,
            field_name=field_name,
            active=active_ids,
        )
        try:
            frozen: dict[str, BaselineValue] = {}
            for key, item in mapping.items():
                if type(key) is not str:
                    planning_error(
                        f"{field_name} keys must be strings",
                        reason="invalid_baseline_descriptor_key",
                        field=field_name,
                    )
                frozen[key] = _freeze_baseline_value(
                    item,
                    field_name=f"{field_name}.{key}",
                    active=active_ids,
                )
            return MappingProxyType(frozen)
        finally:
            active_ids.remove(container_id)
    if isinstance(value, (tuple, list)):
        sequence = cast("tuple[object, ...] | list[object]", value)
        container_id = _enter_container(
            sequence,
            field_name=field_name,
            active=active_ids,
        )
        try:
            return tuple(
                _freeze_baseline_value(
                    item,
                    field_name=f"{field_name}[{index}]",
                    active=active_ids,
                )
                for index, item in enumerate(sequence)
            )
        finally:
            active_ids.remove(container_id)
    planning_error(
        f"{field_name} is not a canonical JSON value",
        reason="invalid_baseline_descriptor_value",
        field=field_name,
        actual_type=type(value).__name__,
    )


def freeze_baseline_mapping(value: object) -> Mapping[str, BaselineValue]:
    """Deep-freeze one lossless baseline descriptor payload."""
    if not isinstance(value, Mapping):
        planning_error(
            "baseline payload must be a mapping",
            reason="invalid_baseline_descriptor_payload",
        )
    frozen = _freeze_baseline_value(
        cast("Mapping[object, object]", value),
        field_name="baseline.payload",
    )
    if not isinstance(frozen, Mapping):
        planning_error(
            "baseline payload must be a mapping",
            reason="invalid_baseline_descriptor_payload",
        )
    return frozen
