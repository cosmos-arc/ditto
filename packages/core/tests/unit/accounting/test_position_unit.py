"""Tests for Position frozen dataclass."""

from dataclasses import FrozenInstanceError

import pytest


class TestPosition:
    def test_create_position(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=0,  # T+1: 买入当日不可卖
            average_cost=0.4520,
            market_value=452.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=2.26,
        )
        assert pos.instrument_id == 1
        assert pos.quantity == 1000
        assert pos.available_quantity == 0
        assert pos.average_cost == 0.4520
        assert pos.total_fees == 2.26

    def test_position_is_frozen(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=0,
            average_cost=0.4520,
            market_value=452.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        with pytest.raises(FrozenInstanceError):
            pos.quantity = 500  # type: ignore[misc]

    def test_position_with_update_returns_new_instance(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id=1,
            quantity=1000,
            available_quantity=0,
            average_cost=0.4520,
            market_value=452.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        updated = pos.__replace__(
            available_quantity=1000,  # T+1 交收后
            market_value=460.0,
            unrealized_pnl=8.0,
        )
        assert updated.available_quantity == 1000
        assert updated.unrealized_pnl == 8.0
        # 原实例不变
        assert pos.available_quantity == 0

    def test_position_with_realized_pnl(self) -> None:
        from ditto_core.accounting.position import Position

        pos = Position(
            instrument_id=1,
            quantity=500,
            available_quantity=500,
            average_cost=0.4520,
            market_value=240.0,
            unrealized_pnl=14.0,
            realized_pnl=10.0,
            total_fees=3.0,
        )
        assert pos.realized_pnl == 10.0
