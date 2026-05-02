"""CompositePreTradeCheck 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.buying_power import BuyingPowerModel
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.order_book import Order, OrderType
from ditto_risk.pre_trade import (
    CompositePreTradeCheck,
    Decision,
    OrderCheckResult,
    PreTradeContext,
)

IID = InstrumentId(1)


def _ctx() -> PreTradeContext:
    return PreTradeContext(
        account_view=AccountView(
            positions=MappingProxyType({}),
            cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
            total_value=100_000.0,
            nav=100_000.0,
            exposure=0.0,
            pending_buy_value=0.0,
            order_book=MagicMock(),
        ),
        rules={},
        market_snapshots={},
        buying_power_model=MagicMock(spec=BuyingPowerModel),
    )


def _order(quantity: int = 100) -> Order:
    return Order(
        order_id="o1",
        instrument_id=IID,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=quantity,
    )


class _AlwaysAccept:
    def check_order(self, order: Order, context: PreTradeContext) -> OrderCheckResult:
        return OrderCheckResult(decision=Decision.ACCEPT, order_id=order.order_id)


class _AlwaysReject:
    def check_order(self, order: Order, context: PreTradeContext) -> OrderCheckResult:
        return OrderCheckResult(
            decision=Decision.REJECT,
            order_id=order.order_id,
            reason="rejected",
            triggered_checks=("mock_reject",),
        )


class _AlwaysResize:
    """每次 resize +100。"""

    def check_order(self, order: Order, context: PreTradeContext) -> OrderCheckResult:
        return OrderCheckResult(
            decision=Decision.RESIZE,
            order_id=order.order_id,
            resized_quantity=order.quantity + 100,
            reason="resize",
            triggered_checks=("mock_resize",),
        )


class _ResizeOnceThenAccept:
    """第一次 RESIZE，之后 ACCEPT。"""

    def __init__(self) -> None:
        self.called = 0

    def check_order(self, order: Order, context: PreTradeContext) -> OrderCheckResult:
        self.called += 1
        if self.called == 1:
            return OrderCheckResult(
                decision=Decision.RESIZE,
                order_id=order.order_id,
                resized_quantity=200,
                reason="resize",
                triggered_checks=("mock_resize",),
            )
        return OrderCheckResult(decision=Decision.ACCEPT, order_id=order.order_id)


class TestCompositePreTradeCheck:
    def test_all_pass(self) -> None:
        """所有规则通过 → ACCEPT。"""
        composite = CompositePreTradeCheck((_AlwaysAccept(), _AlwaysAccept()))
        result = composite.check_order(_order(), _ctx())
        assert result.decision == Decision.ACCEPT
        assert result.resized_quantity is None

    def test_reject_short_circuits(self) -> None:
        """REJECT 立即返回，不继续后续规则。"""
        composite = CompositePreTradeCheck((_AlwaysReject(), _AlwaysAccept()))
        result = composite.check_order(_order(), _ctx())
        assert result.decision == Decision.REJECT
        assert result.reason == "rejected"

    def test_resize_rechecks(self) -> None:
        """RESIZE 后用新数量重新检查。"""
        checker = _ResizeOnceThenAccept()
        composite = CompositePreTradeCheck((checker,))
        result = composite.check_order(_order(quantity=100), _ctx())
        assert result.decision == Decision.ACCEPT
        assert result.resized_quantity == 200

    def test_resize_loop_detected(self) -> None:
        """连续 RESIZE 超过 3 次 → REJECT。"""
        composite = CompositePreTradeCheck((_AlwaysResize(),))
        result = composite.check_order(_order(quantity=100), _ctx())
        assert result.decision == Decision.REJECT
        assert result.reason == "resize loop detected"

    def test_multiple_resizes_then_accept(self) -> None:
        """连续 RESIZE 2 次后 ACCEPT。"""
        call_count = 0

        class ResizeTwice:
            def check_order(
                self, order: Order, context: PreTradeContext
            ) -> OrderCheckResult:
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return OrderCheckResult(
                        decision=Decision.RESIZE,
                        order_id=order.order_id,
                        resized_quantity=order.quantity + 100,
                        reason="resize",
                        triggered_checks=("mock",),
                    )
                return OrderCheckResult(
                    decision=Decision.ACCEPT, order_id=order.order_id
                )

        composite = CompositePreTradeCheck((ResizeTwice(),))
        result = composite.check_order(_order(quantity=100), _ctx())
        assert result.decision == Decision.ACCEPT
        assert result.resized_quantity == 300

    def test_accept_with_no_resize(self) -> None:
        """无 RESIZE 的 ACCEPT 时 resized_quantity 为 None。"""
        composite = CompositePreTradeCheck((_AlwaysAccept(),))
        result = composite.check_order(_order(), _ctx())
        assert result.decision == Decision.ACCEPT
        assert result.resized_quantity is None
