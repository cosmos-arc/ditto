"""Tests for FillOutcome (F4: 显式联合类型)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.execution.fills import Filled, FillOutcome, NoFill
from ditto_kernel.enums import OrderSide

# ---------------------------------------------------------------------------
# Shared fixture data — FillEvent is constructed identically in 5 tests.
# ---------------------------------------------------------------------------

_FILL_EVENT = FillEvent(
    fill_id="FILL-001",
    order_id="ORD-001",
    instrument_id=1,
    direction=OrderSide.BUY,
    filled_quantity=100,
    fill_price=0.452,
    fee=2.26,
    slippage=0.001,
    event_time=datetime(2026, 1, 15, 10, 30, 5),
    cumulative_quantity=100,
    leaves_quantity=0,
)


class TestFillEvent:
    def test_create_fill_event(self) -> None:
        assert _FILL_EVENT.filled_quantity == 100
        assert _FILL_EVENT.cumulative_quantity == 100
        assert _FILL_EVENT.leaves_quantity == 0

    def test_fill_event_is_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            _FILL_EVENT.filled_quantity = 200  # type: ignore[misc]


class TestFilled:
    def test_create_filled(self) -> None:
        filled = Filled(fill_event=_FILL_EVENT)
        assert filled.fill_event.filled_quantity == 100

    def test_filled_is_fill_outcome(self) -> None:
        filled = Filled(fill_event=_FILL_EVENT)
        assert isinstance(filled, FillOutcome)


class TestNoFill:
    def test_no_fill_retryable(self) -> None:
        nofill = NoFill(reason="suspended", can_retry=True)
        assert nofill.reason == "suspended"
        assert nofill.can_retry is True
        assert isinstance(nofill, FillOutcome)

    def test_no_fill_not_retryable(self) -> None:
        nofill = NoFill(reason="insufficient_auction", can_retry=False)
        assert nofill.can_retry is False

    def test_limit_up_deferred(self) -> None:
        nofill = NoFill(reason="limit_up_deferred", can_retry=True)
        assert nofill.reason == "limit_up_deferred"

    def test_limit_down_deferred(self) -> None:
        nofill = NoFill(reason="limit_down_deferred", can_retry=True)
        assert nofill.reason == "limit_down_deferred"

    def test_price_out_of_range(self) -> None:
        nofill = NoFill(reason="price_out_of_range", can_retry=False)
        assert nofill.can_retry is False
