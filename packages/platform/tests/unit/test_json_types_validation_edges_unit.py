"""Strict type-rejection tests for shared JSON field validators."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest
from ditto_platform.foundation.json_types import (
    JsonValue,
    require_bool,
    require_int,
    require_payload,
    require_str,
)


@pytest.mark.parametrize(
    ("validator", "value", "message"),
    [
        (require_str, 1, "field must be a string"),
        (require_int, True, "field must be an int"),
        (require_bool, 1, "field must be a bool"),
        (require_payload, [], "field must be a JSON object"),
    ],
)
def test_json_field_validators_reject_wrong_runtime_types(
    validator: Callable[[Mapping[str, JsonValue], str], object],
    value: JsonValue,
    message: str,
) -> None:
    payload: dict[str, JsonValue] = {"field": value}

    with pytest.raises(TypeError, match=message):
        validator(payload, "field")
