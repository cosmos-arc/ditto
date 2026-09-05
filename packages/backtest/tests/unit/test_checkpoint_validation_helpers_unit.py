"""Fail-closed tests for the checkpoint decoding boundary."""

from __future__ import annotations

import math
from typing import cast

import pytest
from ditto_backtest._checkpoint_codec import (
    finite_float,
    optional_finite_float,
    payload_float,
    payload_int,
    payload_mapping,
    payload_optional_float,
    payload_optional_int,
    payload_optional_str,
    payload_required,
    payload_sequence,
    payload_str,
    require_exact_keys,
)
from ditto_backtest._checkpoint_validation import (
    is_canonical_audit_state_json,
    require_canonical_json,
    require_iso_date,
    require_non_negative_counter,
)


@pytest.mark.parametrize("value", [True, "1", None])
def test_finite_float_rejects_non_numeric_payloads(value: object) -> None:
    with pytest.raises(ValueError, match="must be numeric"):
        finite_float(value, "nav")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_finite_float_rejects_non_finite_payloads(value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        finite_float(value, "nav")


def test_optional_float_helpers_preserve_null_and_normalize_numbers() -> None:
    assert optional_finite_float(None, "nav") is None
    assert optional_finite_float(2, "nav") == 2.0
    assert payload_optional_float({}, "nav") is None
    assert payload_optional_float({"nav": 2}, "nav") == 2.0


def test_checkpoint_payload_readers_reject_wrong_container_and_scalar_types() -> None:
    with pytest.raises(ValueError, match="payload must be an object"):
        payload_mapping([])
    with pytest.raises(ValueError, match="must be a sequence"):
        payload_sequence({"items": "not-a-list"}, "items")
    with pytest.raises(ValueError, match="must be a string"):
        payload_str({"name": 1}, "name")
    with pytest.raises(ValueError, match="string or null"):
        payload_optional_str({"name": 1}, "name")
    with pytest.raises(ValueError, match="must be an integer"):
        payload_int({"count": True}, "count")
    with pytest.raises(ValueError, match="must be numeric"):
        payload_float({"nav": True}, "nav")
    with pytest.raises(ValueError, match="numeric or null"):
        payload_optional_float({"nav": "1"}, "nav")


def test_checkpoint_payload_readers_apply_only_documented_defaults() -> None:
    payload: dict[str, object] = {"name": "checkpoint", "count": 3, "nav": 2}

    assert payload_sequence(payload, "items") == ()
    assert payload_str(payload, "name") == "checkpoint"
    assert payload_optional_str(payload, "missing") is None
    assert payload_int(payload, "count") == 3
    assert payload_optional_int(payload, "missing", default=7) == 7
    assert payload_optional_int(payload, "count") == 3
    assert payload_float(payload, "nav") == 2.0
    assert payload_required(payload, "name") == "checkpoint"

    with pytest.raises(ValueError, match="is required"):
        payload_required(payload, "missing")


def test_exact_key_fence_rejects_both_missing_and_unknown_members() -> None:
    require_exact_keys({"version": 1}, ("version",), subject="manifest")
    with pytest.raises(ValueError, match="missing required fields"):
        require_exact_keys({}, ("version",), subject="manifest")
    with pytest.raises(ValueError, match="unexpected fields"):
        require_exact_keys(
            {"version": 1, "future_field": True},
            ("version",),
            subject="manifest",
        )


@pytest.mark.parametrize("counter", [True, -1, 1.5])
def test_checkpoint_counters_are_exact_non_negative_integers(counter: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        require_non_negative_counter("sequence", cast(int, counter))
    require_non_negative_counter("sequence", 0)


@pytest.mark.parametrize("value", ["", "2026-02-30", "not-a-date"])
def test_checkpoint_dates_are_non_empty_real_iso_dates(value: str) -> None:
    with pytest.raises(ValueError, match="ISO date"):
        require_iso_date("trade_date", value)
    require_iso_date("trade_date", "2026-09-04")


@pytest.mark.parametrize("payload", [None, "", "{", '{"b":1,"a":2}'])
def test_generic_checkpoint_json_rejects_empty_invalid_or_noncanonical_payload(
    payload: object,
) -> None:
    with pytest.raises(ValueError):
        require_canonical_json("evidence", cast(str, payload))


def test_generic_checkpoint_json_accepts_only_canonical_payload() -> None:
    require_canonical_json("evidence", '{"a":2,"b":1}')
    assert is_canonical_audit_state_json("not-json") is False
