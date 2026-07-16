"""Trade transport model safety tests."""

import pytest
from ditto_apps.models.trade import (
    DailyDecisionActionResponse,
    DailyDecisionV2ReadinessResponse,
    ImportAccountBaselineRequest,
    PositionBaselineRequest,
    RecordFillRequest,
    ReplaceFillRequest,
    VoidFillRequest,
)
from pydantic import ValidationError


def _account_payload() -> dict[str, object]:
    return {
        "account_id": "paper-a",
        "strategy_id": "seed_etf_industry_rotation",
        "snapshot_date": "2026-07-15",
        "cash_available": 60_000.0,
        "cash_settled": 60_000.0,
        "cash_frozen": 0.0,
        "total_value": 100_000.0,
        "nav": 1.0,
        "positions": [],
    }


def _position_payload() -> dict[str, object]:
    return {
        "instrument_id": 510300,
        "quantity": 1000,
        "available_quantity": 1000,
        "average_cost": 39.0,
        "market_value": 40_000.0,
        "unrealized_pnl": 1_000.0,
        "realized_pnl": -100.0,
        "total_fees": 12.0,
    }


@pytest.mark.parametrize(
    "field_name",
    [
        "cash_available",
        "cash_settled",
        "cash_frozen",
        "total_value",
        "nav",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_account_baseline_request_rejects_non_finite_amounts(
    field_name: str,
    value: float,
) -> None:
    payload = _account_payload()
    payload[field_name] = value

    with pytest.raises(ValidationError):
        ImportAccountBaselineRequest.model_validate(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "quantity",
        "available_quantity",
        "average_cost",
        "market_value",
        "unrealized_pnl",
        "realized_pnl",
        "total_fees",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_position_baseline_request_rejects_non_finite_values(
    field_name: str,
    value: float,
) -> None:
    payload = _position_payload()
    payload[field_name] = value

    with pytest.raises(ValidationError):
        PositionBaselineRequest.model_validate(payload)


@pytest.mark.parametrize(
    "reason_code",
    ["EOD_RUN_INCOMPLETE", "SIGNAL_INTENT_MISMATCH"],
)
def test_daily_decision_transport_accepts_fail_closed_reason_codes(
    reason_code: str,
) -> None:
    response = DailyDecisionV2ReadinessResponse.model_validate(
        {
            "status": "blocked",
            "reason_codes": [reason_code],
            "details": ["fail closed"],
        }
    )

    assert response.reason_codes == [reason_code]


def test_daily_decision_action_preserves_missing_persisted_intent_status() -> None:
    action = DailyDecisionActionResponse.model_validate(
        {
            "intent_id": "intent-missing",
            "instrument_id": 510300,
            "direction": "buy",
            "target_weight": 0.2,
            "current_weight": 0.0,
            "delta_weight": 0.2,
            "risk_flags": [],
            "intent_status": None,
            "filled_quantity": 0,
        }
    )

    assert action.intent_status is None


def _fill_payload() -> dict[str, object]:
    return {
        "fill_id": "fill-1",
        "intent_id": "intent-1",
        "strategy_id": "strat-a",
        "trade_date": "2026-07-16",
        "instrument_id": 510300,
        "direction": "buy",
        "quantity": 100,
        "fill_price": 4.2,
        "fee": 1.0,
        "slippage": 0.0,
        "notes": "manual fill",
    }


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("trade_date", "2026/07/16"),
        ("trade_date", "2026-02-31"),
        ("quantity", 0),
        ("fill_price", 0.0),
        ("fill_price", float("nan")),
        ("fee", -1.0),
        ("slippage", float("inf")),
    ],
)
def test_record_fill_request_rejects_invalid_ledger_values(
    field_name: str,
    invalid_value: object,
) -> None:
    payload = _fill_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        RecordFillRequest.model_validate(payload)


def test_record_fill_request_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RecordFillRequest.model_validate({**_fill_payload(), "legacy_id": "old"})


def test_void_fill_request_requires_non_blank_reason_and_strict_shape() -> None:
    with pytest.raises(ValidationError):
        VoidFillRequest.model_validate({"adjustment_id": "adj-1", "reason": ""})
    with pytest.raises(ValidationError):
        VoidFillRequest.model_validate(
            {"adjustment_id": "adj-1", "reason": "wrong fill", "extra": True}
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("trade_date", "16-07-2026"),
        ("trade_date", "2026-02-31"),
        ("quantity", 0),
        ("fill_price", float("inf")),
        ("fee", -1.0),
        ("slippage", float("nan")),
    ],
)
def test_replace_fill_request_rejects_invalid_values(
    field_name: str,
    invalid_value: object,
) -> None:
    payload: dict[str, object] = {
        "adjustment_id": "adj-1",
        "replacement_fill_id": "fill-2",
        "trade_date": "2026-07-16",
        "quantity": 100,
        "fill_price": 4.2,
        "reason": "correct price",
    }
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        ReplaceFillRequest.model_validate(payload)


def test_daily_decision_transport_accepts_overfill_review_code() -> None:
    response = DailyDecisionV2ReadinessResponse.model_validate(
        {
            "status": "review",
            "reason_codes": ["FILL_QUANTITY_EXCEEDED"],
            "details": ["overfill"],
        }
    )

    assert response.reason_codes == ["FILL_QUANTITY_EXCEEDED"]
