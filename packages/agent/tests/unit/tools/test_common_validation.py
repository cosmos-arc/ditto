"""Closed-schema and strict argument validation for Agent function tools."""

from __future__ import annotations

from typing import cast

import pytest
from ditto_agent.tools._common import Arguments, object_schema


def test_tool_schema_cannot_expose_host_owned_temporal_context() -> None:
    with pytest.raises(ValueError, match="trusted context fields"):
        object_schema(
            properties={
                "instrument_id": {"type": "string"},
                "knowledge_cutoff": {"type": "string"},
            },
            required=("instrument_id",),
        )


def test_arguments_require_every_declared_field() -> None:
    with pytest.raises(ValueError, match="missing required arguments"):
        Arguments({}, required=("instrument_id",))


@pytest.mark.parametrize("value", [None, "", " padded ", 1])
def test_text_requires_a_canonical_nonempty_string(value: object) -> None:
    arguments = Arguments({"value": value}, required=("value",))
    with pytest.raises(ValueError, match="canonical string"):
        arguments.text("value")


@pytest.mark.parametrize("value", ["", " padded ", 1])
def test_optional_text_rejects_noncanonical_present_values(value: object) -> None:
    arguments = Arguments({"value": value}, required=(), optional=("value",))
    with pytest.raises(ValueError, match="null or a non-empty canonical string"):
        arguments.optional_text("value")

    assert (
        Arguments({}, required=(), optional=("value",)).optional_text("value") is None
    )


@pytest.mark.parametrize("value", [None, True, 0, -1, "1"])
def test_positive_integer_excludes_null_boolean_and_nonpositive_values(
    value: object,
) -> None:
    arguments = Arguments({"value": value}, required=("value",))
    with pytest.raises(ValueError, match="positive integer"):
        arguments.positive_integer("value")


@pytest.mark.parametrize("value", [True, 0, -1, "1"])
def test_nullable_positive_integer_only_adds_explicit_null(value: object) -> None:
    arguments = Arguments({"value": value}, required=("value",))
    with pytest.raises(ValueError, match="null or a positive integer"):
        arguments.nullable_positive_integer("value")

    assert (
        Arguments({"value": None}, required=("value",)).nullable_positive_integer(
            "value"
        )
        is None
    )
    assert (
        Arguments({"value": 2}, required=("value",)).nullable_positive_integer("value")
        == 2
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("value", "array of strings"),
        (("",), "canonical strings"),
        ((" padded ",), "canonical strings"),
        ((1,), "canonical strings"),
        (("same", "same"), "unique strings"),
    ],
)
def test_text_tuple_requires_unique_canonical_strings(
    value: object,
    message: str,
) -> None:
    arguments = Arguments({"value": value}, required=("value",))
    with pytest.raises(ValueError, match=message):
        arguments.text_tuple("value")

    assert Arguments({"value": ["one", "two"]}, required=("value",)).text_tuple(
        "value"
    ) == ("one", "two")


def test_boolean_is_exact_and_defaulted_only_when_absent() -> None:
    assert not Arguments({}, required=(), optional=("value",)).boolean("value")
    assert Arguments({}, required=(), optional=("value",)).boolean(
        "value", default=True
    )
    with pytest.raises(ValueError, match="must be a boolean"):
        Arguments({"value": 1}, required=("value",)).boolean("value")


@pytest.mark.parametrize("value", [(), "value", 1])
def test_mapping_rejects_non_objects(value: object) -> None:
    arguments = Arguments({"value": value}, required=("value",))
    with pytest.raises(ValueError, match="string-keyed object"):
        arguments.mapping("value")

    forged = cast("dict[str, object]", {1: "value"})
    with pytest.raises(ValueError, match="string-keyed object"):
        Arguments({"value": forged}, required=("value",)).mapping("value")
