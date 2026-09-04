"""Edge cases for immutable fill validation."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from ditto_execution.errors import FillProcessingError
from ditto_execution.fills.validation import validate_fill_record
from ditto_execution.models import FillRecord


def _fill() -> FillRecord:
    return FillRecord(
        fill_id="fill-1",
        intent_id="intent-1",
        strategy_id="strategy-1",
        trade_date="2026-09-04",
        instrument_id=600519,
        direction="buy",
        quantity=100,
        fill_price=10.0,
        fee=5.0,
    )


def test_boolean_is_not_accepted_as_numeric_fill_evidence() -> None:
    malformed = replace(_fill(), fill_price=cast(float, True))

    with pytest.raises(FillProcessingError, match="fill_price"):
        validate_fill_record(malformed)


def test_compact_iso_date_is_rejected_as_non_canonical() -> None:
    malformed = replace(_fill(), trade_date="20260904")

    with pytest.raises(FillProcessingError, match="valid YYYY-MM-DD"):
        validate_fill_record(malformed)


def test_empty_settlement_date_remains_an_explicit_unsettled_value() -> None:
    fill = _fill()

    validate_fill_record(fill)

    assert fill.settlement_date == ""
