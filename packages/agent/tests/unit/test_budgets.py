from __future__ import annotations

from decimal import Decimal

import pytest
from ditto_agent.models.port import ModelUsage
from ditto_agent.runtime.budgets import (
    BudgetExceeded,
    BudgetLedger,
    BudgetLimits,
    ModelPricing,
)


class _MonotonicClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _limits(**overrides: object) -> BudgetLimits:
    values: dict[str, object] = {
        "max_turns": 4,
        "max_model_tokens": 1_000,
        "max_model_spend_usd": Decimal("0.10"),
        "max_wall_time_seconds": 30.0,
        "max_retries": 1,
    }
    values.update(overrides)
    return BudgetLimits(**values)


def _pricing() -> ModelPricing:
    return ModelPricing(
        input_usd_per_million=Decimal("2.00"),
        output_usd_per_million=Decimal("8.00"),
    )


def test_budget_ledger_accounts_tokens_cost_turns_tools_and_retries() -> None:
    clock = _MonotonicClock()
    ledger = BudgetLedger(limits=_limits(), pricing=_pricing(), monotonic=clock)

    ledger.before_model_attempt()
    ledger.record_model_usage(
        ModelUsage(requests=2, input_tokens=400, output_tokens=100)
    )
    ledger.before_tool_call()
    ledger.register_retry()
    clock.advance(3.5)

    snapshot = ledger.snapshot()
    assert snapshot.model_attempts == 1
    assert snapshot.model_turns == 2
    assert snapshot.tool_calls == 1
    assert snapshot.retries == 1
    assert snapshot.total_tokens == 500
    assert snapshot.model_spend_usd == Decimal("0.001600")
    assert snapshot.elapsed_seconds == 3.5
    assert snapshot.exhausted_reason is None


@pytest.mark.parametrize(
    ("limits", "usage", "reason_code"),
    [
        (
            _limits(max_model_tokens=100),
            ModelUsage(requests=1, input_tokens=90, output_tokens=11),
            "max_model_tokens_exceeded",
        ),
        (
            _limits(max_model_spend_usd=Decimal("0.000001")),
            ModelUsage(requests=1, input_tokens=1, output_tokens=1),
            "max_model_spend_exceeded",
        ),
        (
            _limits(max_turns=1),
            ModelUsage(requests=2, input_tokens=1, output_tokens=1),
            "max_turns_exceeded",
        ),
    ],
)
def test_usage_budget_exhaustion_is_sticky_and_blocks_further_calls(
    limits: BudgetLimits,
    usage: ModelUsage,
    reason_code: str,
) -> None:
    ledger = BudgetLedger(
        limits=limits,
        pricing=_pricing(),
        monotonic=_MonotonicClock(),
    )
    ledger.before_model_attempt()

    with pytest.raises(BudgetExceeded) as usage_error:
        ledger.record_model_usage(usage)
    with pytest.raises(BudgetExceeded) as next_error:
        ledger.before_model_attempt()

    assert usage_error.value.reason_code == reason_code
    assert next_error.value.reason_code == reason_code
    assert ledger.snapshot().exhausted_reason == reason_code


def test_wall_time_and_retry_limits_fail_closed_without_implicit_clock() -> None:
    clock = _MonotonicClock()
    ledger = BudgetLedger(
        limits=_limits(max_wall_time_seconds=2.0, max_retries=1),
        pricing=_pricing(),
        monotonic=clock,
    )
    ledger.register_retry()

    with pytest.raises(BudgetExceeded) as retry_error:
        ledger.register_retry()

    assert retry_error.value.reason_code == "max_retries_exceeded"

    other = BudgetLedger(
        limits=_limits(max_wall_time_seconds=2.0),
        pricing=_pricing(),
        monotonic=clock,
    )
    clock.advance(2.01)
    with pytest.raises(BudgetExceeded) as time_error:
        other.before_tool_call()

    assert time_error.value.reason_code == "max_wall_time_exceeded"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_turns": 0},
        {"max_model_tokens": True},
        {"max_model_spend_usd": Decimal("NaN")},
        {"max_wall_time_seconds": float("inf")},
        {"max_retries": -1},
    ],
)
def test_budget_limits_reject_invalid_or_unbounded_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _limits(**kwargs)
