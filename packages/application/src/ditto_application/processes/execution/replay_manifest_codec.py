"""Strict decoding helpers for persisted replay manifest identity."""

from typing import cast

from ditto_strategy.alpha.parameters import EffectiveParameter, ParameterValue
from ditto_strategy.errors import StrategySpecError

from ditto_application.exceptions import AppProcessError


def deserialize_effective_parameters(
    raw_effective: object,
) -> tuple[EffectiveParameter, ...]:
    """Decode exact typed values without accepting legacy raw overrides."""
    if not isinstance(raw_effective, list):
        raise AppProcessError(
            "effective_parameters must be a JSON array",
            field_name="effective_parameters",
            reason="invalid_reproduction_identity",
        )
    effective_parameters: list[EffectiveParameter] = []
    for index, item_value in enumerate(cast(list[object], raw_effective)):
        if not isinstance(item_value, dict):
            raise AppProcessError(
                "effective parameter must contain exactly path and value",
                field_name=f"effective_parameters[{index}]",
                reason="invalid_reproduction_identity",
            )
        item = cast(dict[object, object], item_value)
        if set(item) != {"path", "value"}:
            raise AppProcessError(
                "effective parameter must contain exactly path and value",
                field_name=f"effective_parameters[{index}]",
                reason="invalid_reproduction_identity",
            )
        path_value = item["path"]
        parameter_value = item["value"]
        if not isinstance(path_value, str):
            raise AppProcessError(
                "effective parameter path must be a string",
                field_name=f"effective_parameters[{index}].path",
                reason="invalid_reproduction_identity",
            )
        try:
            effective_parameters.append(
                EffectiveParameter(
                    path=path_value,
                    value=cast(ParameterValue, parameter_value),
                ),
            )
        except StrategySpecError as exc:
            raise AppProcessError(
                str(exc),
                field_name=f"effective_parameters[{index}]",
                reason="invalid_reproduction_identity",
            ) from exc
    return tuple(effective_parameters)
