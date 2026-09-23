"""Exact equal or user-specified target weights for a research allocation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

_ONE = Decimal("1")
_PRECISION = Decimal("0.00000001")


def explicit_target_weights(
    instrument_ids: tuple[int, ...],
    mode: Literal["equal", "manual"],
    cash_weight: Decimal,
    max_position_weight: Decimal,
    manual_weights: dict[int, Decimal],
) -> dict[int, Decimal]:
    """Preserve explicit user intent and assign only the equal-weight tail."""
    if not instrument_ids or len(set(instrument_ids)) != len(instrument_ids):
        raise ValueError("selected ETF identities must be non-empty and unique")
    if not _valid_weight(cash_weight, allow_one=False):
        raise ValueError(
            "cash_weight must be between zero and one at eight-decimal precision"
        )
    if not _valid_weight(max_position_weight, allow_zero=False):
        raise ValueError("max_position_weight must be positive and at most one")
    budget = _ONE - cash_weight
    if mode == "equal":
        if manual_weights:
            raise ValueError("equal mode must not include manual_weights")
        each = (budget / Decimal(len(instrument_ids))).quantize(_PRECISION)
        weights = dict.fromkeys(instrument_ids, each)
        weights[instrument_ids[-1]] += budget - sum(weights.values())
    elif mode == "manual":
        weights = _manual_target_weights(instrument_ids, manual_weights, budget)
    else:
        raise ValueError("unsupported ETF allocation mode")
    if any(weight > max_position_weight for weight in weights.values()):
        raise ValueError("selected ETF weight exceeds max_position_weight")
    return weights


def _manual_target_weights(
    instrument_ids: tuple[int, ...], weights: dict[int, Decimal], budget: Decimal
) -> dict[int, Decimal]:
    if set(weights) != set(instrument_ids):
        raise ValueError("manual_weights must cover exactly the selected ETFs")
    if any(not _valid_weight(weight) for weight in weights.values()):
        raise ValueError(
            "manual_weights must be non-negative at eight-decimal precision"
        )
    if sum(weights.values()) != budget:
        raise ValueError("manual_weights plus cash_weight must equal one")
    return dict(weights)


def _valid_weight(
    value: Decimal, *, allow_zero: bool = True, allow_one: bool = True
) -> bool:
    try:
        return (
            value.is_finite()
            and (value >= 0 if allow_zero else value > 0)
            and (value <= 1 if allow_one else value < 1)
            and value == value.quantize(_PRECISION)
        )
    except (InvalidOperation, AttributeError):
        return False
