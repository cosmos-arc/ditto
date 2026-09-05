"""Boundary validation tests for selection exposure evidence."""

from __future__ import annotations

from dataclasses import replace
from math import inf
from typing import cast

import pytest
from ditto_strategy.alpha.selection_exposure import (
    SelectionExposureDeclaration,
    SelectionExposureEvidence,
    SelectionExposureLane,
    SelectionExposurePolicy,
    SelectionExposureSizeBucket,
)
from ditto_strategy.errors import StrategySpecError

_TRADE_DATE = "2026-09-04"


def _evidence() -> SelectionExposureEvidence:
    return SelectionExposureEvidence(
        trade_date=_TRADE_DATE,
        instrument_id="000001.SZ",
        selected_weight=0.5,
        industry_id="bank",
        size_value=50_000_000_000.0,
        size_bucket=SelectionExposureSizeBucket.LARGE,
    )


@pytest.mark.parametrize("trade_date", [20260904, "bad-date", "2026-W36-5"])
def test_declaration_requires_canonical_iso_trade_date(trade_date: object) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        SelectionExposureDeclaration.from_policy(
            cast("str", trade_date),
            SelectionExposurePolicy.stock(),
        )

    assert exc_info.value.details["reason"] == "invalid_evidence_trade_date"


@pytest.mark.parametrize("instrument_id", [True, 1.5, ""])
def test_exposure_requires_non_boolean_non_empty_instrument_identity(
    instrument_id: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="instrument_id"):
        replace(_evidence(), instrument_id=cast("str", instrument_id))


@pytest.mark.parametrize("value", [True, inf])
def test_exposure_numbers_must_be_finite_non_boolean(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="finite number"):
        replace(_evidence(), selected_weight=cast("float", value))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("applicability", "APPLICABLE"),
        ("lane", "STOCK_LANE"),
    ],
)
def test_policy_requires_exact_enum_types(field_name: str, value: object) -> None:
    with pytest.raises(TypeError):
        replace(SelectionExposurePolicy.stock(), **{field_name: value})


def test_applicable_policy_is_restricted_to_stock_lane_and_complete_columns() -> None:
    with pytest.raises(ValueError, match="STOCK_LANE"):
        replace(SelectionExposurePolicy.stock(), lane=SelectionExposureLane.ETF_LANE)
    with pytest.raises(ValueError, match="industry_column"):
        replace(SelectionExposurePolicy.stock(), industry_column="")


def test_not_applicable_policy_is_restricted_to_empty_etf_semantics() -> None:
    with pytest.raises(ValueError, match="ETF_LANE"):
        replace(SelectionExposurePolicy.etf(), lane=SelectionExposureLane.STOCK_LANE)
    with pytest.raises(ValueError, match="cannot declare stock columns"):
        replace(SelectionExposurePolicy.etf(), industry_column="sector_id")


def test_declaration_factory_requires_an_exact_policy() -> None:
    with pytest.raises(TypeError, match="SelectionExposurePolicy"):
        SelectionExposureDeclaration.from_policy(
            _TRADE_DATE,
            cast("SelectionExposurePolicy", "stock"),
        )


def test_exposure_rejects_negative_weight_nonpositive_size_and_untyped_bucket() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        replace(_evidence(), selected_weight=-0.01)
    with pytest.raises(ValueError, match="positive"):
        replace(_evidence(), size_value=0.0)
    with pytest.raises(TypeError, match="SelectionExposureSizeBucket"):
        replace(
            _evidence(),
            size_bucket=cast("SelectionExposureSizeBucket", "LARGE"),
        )
