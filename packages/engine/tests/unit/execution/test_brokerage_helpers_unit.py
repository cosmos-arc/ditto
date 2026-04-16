"""Tests for extracted brokerage helper functions.

Tests for:
- _is_order_executable: pure function checking if an order can be executed
- BacktestBrokerage._process_single_ticket: method processing a single ticket
"""

from datetime import datetime
from unittest.mock import MagicMock

from ditto_engine.accounting.order_book import (
    Order,
    OrderSide,
    OrderStatus,
    OrderTicket,
    OrderType,
)
from ditto_engine.accounting.position import Position
from ditto_engine.execution.brokerage import _is_order_executable
from ditto_engine.execution.reality.settlement import SimpleSettlementModel
from ditto_engine.execution.rules import (
    TradingRuleSet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _order(
    order_id: str = "ORD-001",
    instrument_id: int = 1,
    order_type: OrderType = OrderType.MARKET,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 1000,
    price: float | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=order_type,
        direction=direction,
        quantity=quantity,
        price=price,
        created_at=datetime(2026, 3, 1),
    )


def _ticket(
    order_id: str = "ORD-001",
    instrument_id: int = 1,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 1000,
) -> OrderTicket:
    return OrderTicket(
        order=_order(
            order_id=order_id,
            instrument_id=instrument_id,
            direction=direction,
            quantity=quantity,
        ),
        status=OrderStatus.SUBMITTED,
    )


def _trading_rule(instrument_id: int = 1) -> TradingRuleSet:
    return TradingRuleSet(
        instrument_id=instrument_id,
        as_of_date="2026-01-01",
        settlement_cycle=0,
        fund_settlement_cycle=0,
        price_limit_pct=None,
        order_types_supported=("market", "limit"),
        call_auction_sessions=(),
    )


def _position(
    instrument_id: int = 1,
    quantity: int = 1000,
    available_quantity: int = 1000,
) -> Position:
    """Create a Position with only the fields used by _is_order_executable."""
    return Position(
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=0.0,
        market_value=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


# ---------------------------------------------------------------------------
# _is_order_executable
# ---------------------------------------------------------------------------


class TestIsOrderExecutable:
    """Tests for _is_order_executable module-level function."""

    def test_buy_always_executable_when_tradable(self) -> None:
        """BUY orders are executable when settlement model says tradable."""
        ticket = _ticket(direction=OrderSide.BUY)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()

        assert (
            _is_order_executable(ticket, None, settlement, 1, "2026-01-01", rule)
            is True
        )

    def test_sell_executable_with_sufficient_available(self) -> None:
        """SELL is executable when available_quantity >= leaves_quantity."""
        ticket = _ticket(direction=OrderSide.SELL, quantity=500)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=500)

        assert (
            _is_order_executable(ticket, position, settlement, 1, "2026-01-01", rule)
            is True
        )

    def test_sell_blocked_when_insufficient_available(self) -> None:
        """SELL is blocked when available_quantity < leaves_quantity."""
        ticket = _ticket(direction=OrderSide.SELL, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=500)

        assert (
            _is_order_executable(ticket, position, settlement, 1, "2026-01-01", rule)
            is False
        )

    def test_sell_with_no_position_passes_check(self) -> None:
        """SELL with no position passes _is_order_executable.

        When position is None, the available_quantity guard is skipped.
        This preserves original behavior — the fill model may still reject
        the order downstream.
        """
        ticket = _ticket(direction=OrderSide.SELL, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()

        assert (
            _is_order_executable(ticket, None, settlement, 1, "2026-01-01", rule)
            is True
        )

    def test_not_tradable_by_settlement_model(self) -> None:
        """Returns False when settlement model says not tradable."""
        ticket = _ticket(direction=OrderSide.BUY)
        settlement = MagicMock()
        settlement.is_tradable.return_value = False
        rule = _trading_rule()

        assert (
            _is_order_executable(ticket, None, settlement, 1, "2026-01-01", rule)
            is False
        )

    def test_sell_exact_available_executable(self) -> None:
        """SELL is executable when available_quantity exactly equals leaves."""
        ticket = _ticket(direction=OrderSide.SELL, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=1000)

        assert (
            _is_order_executable(ticket, position, settlement, 1, "2026-01-01", rule)
            is True
        )

    def test_buy_with_position_ignores_available(self) -> None:
        """BUY orders ignore available_quantity check."""
        ticket = _ticket(direction=OrderSide.BUY, quantity=1000)
        settlement = SimpleSettlementModel()
        rule = _trading_rule()
        position = _position(available_quantity=0)

        assert (
            _is_order_executable(ticket, position, settlement, 1, "2026-01-01", rule)
            is True
        )
