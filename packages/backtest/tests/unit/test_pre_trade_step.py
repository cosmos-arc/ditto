"""
PreTradeStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.steps import PreTradeStep, StepContext, TradingStep
from ditto_risk.pre_trade import Decision
from packages.backtest.tests.unit._helpers import (
    _make_account_view,
    _make_clock,
    _make_ctx,
    _make_execution_plan,
    _make_order,
    _make_slice,
)


class TestPreTradeStep:
    """PreTradeStep: PreTrade 校验 + 订单提交。"""

    def _make_ctx_with_plan(self) -> StepContext:
        """构建包含 execution_plan 的 StepContext。"""
        ctx = _make_ctx()
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        ctx.target_portfolio = Mock(name="target_portfolio")
        ctx.execution_plan = _make_execution_plan()
        ctx.rules = {}
        return ctx

    def test_skips_when_not_rebalance_day(self) -> None:
        """非调仓日跳过 PreTrade。"""
        step = PreTradeStep(
            pre_trade_check=Mock(),
            brokerage=Mock(),
            fee_model=Mock(),
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = _make_ctx(is_rebalance_day=False)
        result = step.execute(ctx)

        assert result.success is True

    def test_skips_when_no_execution_plan(self) -> None:
        """调仓日但无 execution_plan 时跳过。"""
        step = PreTradeStep(
            pre_trade_check=Mock(),
            brokerage=Mock(),
            fee_model=Mock(),
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = _make_ctx()
        ctx.execution_plan = None
        result = step.execute(ctx)

        assert result.success is True

    def test_checks_orders_and_places_accepted(self) -> None:
        """校验通过 -> 提交订单 + 追加到 step_orders。"""
        order = _make_order()
        plan = _make_execution_plan(orders=(order,))
        check_result = Mock(
            decision=Decision.ACCEPT,
            resized_quantity=None,
            reason=None,
            triggered_checks=(),
        )
        brokerage = Mock()
        fee_model = Mock(estimate=Mock(return_value=0.0))

        step = PreTradeStep(
            pre_trade_check=Mock(check_order=Mock(return_value=check_result)),
            brokerage=brokerage,
            fee_model=fee_model,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_plan()
        ctx.execution_plan = plan
        step.execute(ctx)

        # 订单被提交
        brokerage.place_order.assert_called_once()
        # step_orders 追加了订单
        assert len(ctx.step_orders) == 1

    def test_rejects_order_without_placement(self) -> None:
        """REJECT -> 不提交订单。"""
        order = _make_order()
        plan = _make_execution_plan(orders=(order,))
        check_result = Mock(
            decision=Decision.REJECT,
            resized_quantity=None,
            reason="test reject",
            triggered_checks=("test",),
        )
        brokerage = Mock()

        step = PreTradeStep(
            pre_trade_check=Mock(check_order=Mock(return_value=check_result)),
            brokerage=brokerage,
            fee_model=Mock(),
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_plan()
        ctx.execution_plan = plan
        step.execute(ctx)

        # 订单未被提交
        brokerage.place_order.assert_not_called()
        # step_orders 为空
        assert len(ctx.step_orders) == 0

    def test_resizes_order_and_places(self) -> None:
        """RESIZE -> 用新数量提交订单。"""
        order = _make_order(quantity=150)
        plan = _make_execution_plan(orders=(order,))
        check_result = Mock(
            decision=Decision.RESIZE,
            resized_quantity=100,
            reason="lot_size",
            triggered_checks=("lot_size",),
        )
        brokerage = Mock()
        fee_model = Mock(estimate=Mock(return_value=0.0))

        step = PreTradeStep(
            pre_trade_check=Mock(check_order=Mock(return_value=check_result)),
            brokerage=brokerage,
            fee_model=fee_model,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_plan()
        ctx.execution_plan = plan
        step.execute(ctx)

        # 提交的是 resize 后的订单
        placed_order = brokerage.place_order.call_args[0][0]
        assert placed_order.quantity == 100
        assert len(ctx.step_orders) == 1

    def test_records_pre_trade_decisions_audit(self) -> None:
        """有 audit_collector 时记录 PreTrade 决策。"""
        order = _make_order()
        plan = _make_execution_plan(orders=(order,))
        check_result = Mock(
            decision=Decision.ACCEPT,
            resized_quantity=None,
            reason=None,
            triggered_checks=(),
        )
        fee_model = Mock(estimate=Mock(return_value=0.0))

        step = PreTradeStep(
            pre_trade_check=Mock(check_order=Mock(return_value=check_result)),
            brokerage=Mock(),
            fee_model=fee_model,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_plan()
        ctx.execution_plan = plan
        step.execute(ctx)

        # pre_trade_decisions 被追加
        assert len(ctx.pre_trade_decisions) == 1

    def test_publishes_order_submitted_event(self) -> None:
        """有 event_bus 时发布 OrderSubmitted 事件。"""
        order = _make_order()
        plan = _make_execution_plan(orders=(order,))
        check_result = Mock(
            decision=Decision.ACCEPT,
            resized_quantity=None,
            reason=None,
            triggered_checks=(),
        )
        event_bus = Mock()
        fee_model = Mock(estimate=Mock(return_value=0.0))

        step = PreTradeStep(
            pre_trade_check=Mock(check_order=Mock(return_value=check_result)),
            brokerage=Mock(),
            fee_model=fee_model,
            event_bus=event_bus,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_plan()
        ctx.execution_plan = plan
        step.execute(ctx)

        event_bus.publish.assert_called_once()

    def test_satisfies_trading_step_protocol(self) -> None:
        """PreTradeStep 满足 TradingStep Protocol。"""
        accept_result = Mock(
            decision=Decision.ACCEPT,
            resized_quantity=None,
            reason=None,
            triggered_checks=(),
        )
        step: TradingStep = PreTradeStep(  # type: ignore[assignment]
            pre_trade_check=Mock(check_order=Mock(return_value=accept_result)),
            brokerage=Mock(),
            fee_model=Mock(estimate=Mock(return_value=0.0)),
            event_bus=None,
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_plan()
        result = step.execute(ctx)
        assert result.success is True
