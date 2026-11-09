"""
PreTradeStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
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


def test_planner_rejection_reaches_saved_decision_stream() -> None:
    from dataclasses import replace

    from ditto_execution._planner_types import BlockedOrder, BlockSeverity
    from ditto_kernel.identity import InstrumentId
    from ditto_kernel.order import OrderSide

    ctx = _make_ctx()
    ctx.slice_ = _make_slice()
    ctx.account_view = _make_account_view()
    ctx.rules = {}
    ctx.execution_plan = replace(
        _make_execution_plan(),
        orders=(),
        blocked_orders=(
            BlockedOrder(
                InstrumentId(1),
                OrderSide.BUY,
                100,
                "limit_up_no_buy",
                BlockSeverity.DEFER,
            ),
        ),
    )
    step = PreTradeStep(
        pre_trade_check=Mock(),
        brokerage=Mock(),
        fee_model=None,
        event_bus=None,
        clock=_make_clock(),
    )
    assert step.execute(ctx).success
    assert len(ctx.pre_trade_decisions) == 1
    saved = ctx.pre_trade_decisions[0]
    assert (saved.decision, saved.reason, saved.final_quantity) == (
        "rejected",
        "limit_up_no_buy",
        0,
    )
    assert saved.check_sequence == ("planner", "defer")


def test_dated_minimum_is_rechecked_after_risk_resizes_an_order() -> None:
    from ditto_execution.reality.ordinary_equity import (
        CashEquityListing,
        stock_rule_history,
    )
    from ditto_kernel.identity import InstrumentId

    order = _make_order(instrument_id=InstrumentId(1), quantity=201)
    rules = stock_rule_history(
        CashEquityListing(
            InstrumentId(1), "688001", "stock", "SSE", "2019-07-22", None
        ),
        commission_rate=0.001,
        start="2019-07-22",
        end="2019-07-22",
        trading_days=["2019-07-22"],
    )[-1]
    step = PreTradeStep(
        pre_trade_check=Mock(
            check_order=Mock(
                return_value=Mock(
                    decision=Decision.RESIZE,
                    resized_quantity=199,
                    reason="risk resized",
                    triggered_checks=("risk",),
                )
            )
        ),
        brokerage=Mock(),
        fee_model=Mock(),
        event_bus=None,
        clock=_make_clock(),
    )
    ctx = _make_ctx()
    ctx.slice_ = _make_slice()
    ctx.account_view = _make_account_view()
    ctx.execution_plan = _make_execution_plan(orders=(order,))
    ctx.rules = {InstrumentId(1): rules}
    step.execute(ctx)
    assert ctx.step_orders == []
    assert ctx.pre_trade_decisions[0].reason == "order_quantity_below_dated_minimum"
    assert ctx.pre_trade_decisions[0].final_quantity == 0


@pytest.mark.parametrize("unlisted", [False, True])
def test_st_submission_cap_includes_unfilled_orders_and_releases_cancellations(
    unlisted,
):
    from dataclasses import replace

    from ditto_execution.orders.book import OrderBook
    from ditto_execution.orders.journal import InMemoryOrderEventJournal
    from ditto_execution.reality.ordinary_equity import (
        CashEquityListing,
        ordinary_equity_rules,
    )
    from ditto_kernel.identity import InstrumentId
    from ditto_portfolio.accounting import CashAccountBuyingPower
    from ditto_risk.pre_trade import PreTradeContext

    iid = InstrumentId(1)
    definition, rule, fee = ordinary_equity_rules(
        CashEquityListing(iid, "000001", "stock", "SZSE", "1991-04-03", None),
        commission_rate=0.0003,
        start="2026-10-08",
        end="2026-10-09",
    )
    book = OrderBook(InMemoryOrderEventJournal())
    pending = _make_order(order_id="pending", instrument_id=iid, quantity=400_000)
    book.submit(pending)
    view = _make_account_view()
    if unlisted:
        from datetime import date

        from ditto_portfolio.accounting.dividends import Distribution, DividendBook
        from ditto_portfolio.accounting.position import Position

        event = Distribution(
            iid,
            date(2026, 10, 7),
            date(2026, 10, 8),
            None,
            0,
            date(2026, 9, 30),
            "source:st-shares",
            share_ratio=0.5,
            listing_date=date(2026, 10, 12),
            share_tax_basis="issuer",
        )
        state, _ = (
            DividendBook.start((event,))
            .close("2026-10-07", {iid: 1_000_000})
            .settle("2026-10-08")
        )
        view = replace(
            view,
            dividends=state,
            positions={
                iid: Position(iid, 1_500_000, 1_000_000, 10 / 1.5, 10_000_000, 0, 0, 0)
            },
        )
    context = PreTradeContext(
        account_view=view,
        rules={iid: (definition, replace(rule, max_daily_buy_quantity=500_000), fee)},
        market_snapshots={},
        buying_power_model=CashAccountBuyingPower(),
        pending_tickets=book.get_pending(),
    )
    order = _make_order(order_id="new", instrument_id=iid, quantity=100_100)
    rejection = PreTradeStep._dated_order_check(order, context)
    assert rejection is not None
    assert rejection.reason == "daily_buy_quantity_exceeds_dated_maximum"
    assert (
        PreTradeStep._dated_order_check(order.with_quantity(100_000), context) is None
    )
    book.cancel(pending.client_id)
    assert (
        PreTradeStep._dated_order_check(
            order, replace(context, pending_tickets=book.get_pending())
        )
        is None
    )
    assert (
        PreTradeStep._dated_order_check(
            order, replace(context, accepted_orders=(pending,), pending_tickets=())
        )
        is not None
    )
