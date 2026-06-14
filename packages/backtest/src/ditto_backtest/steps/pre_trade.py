"""
PreTradeStep -- PreTrade 校验 + 订单提交.

对应 EngineLoop._step() 中 PreTrade 部分:
  1. 构建 PreTradeContext
  2. 逐单校验 (composite_pre_trade_check.check_order)
  3. ACCEPT/RESIZE -> 提交订单 + 发布 OrderSubmitted 事件
  4. REJECT -> 跳过
  5. F1: 滚动更新 PreTradeContext
  6. 记录 PreTrade 决策审计
  7. 仅在调仓日 + 有 execution_plan 时执行
"""

from __future__ import annotations

from typing import ClassVar

from ditto_execution.brokerage import Brokerage
from ditto_execution.events import OrderSubmitted
from ditto_execution.orders.model import Order
from ditto_kernel import traced
from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_kernel.trading import FeeModel
from ditto_portfolio.accounting import CashAccountBuyingPower
from ditto_risk.pre_trade import (
    CompositePreTradeCheck,
    Decision,
    OrderCheckResult,
    PreTradeContext,
)

from ditto_backtest.audit.records import PreTradeDecisionRecord
from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["PreTradeStep"]


class PreTradeStep:
    """PreTrade 校验步骤 -- 逐单检查 + 提交订单."""

    _DECISION_MAP: ClassVar[dict[Decision, str]] = {
        Decision.ACCEPT: "accepted",
        Decision.REJECT: "rejected",
        Decision.RESIZE: "resized",
    }

    def __init__(
        self,
        pre_trade_check: CompositePreTradeCheck,
        brokerage: Brokerage,
        fee_model: FeeModel | None,
        event_bus: EventBus | None,
        clock: Clock,
    ) -> None:
        self._pre_trade_check = pre_trade_check
        self._brokerage = brokerage
        self._fee_model = fee_model
        self._event_bus = event_bus
        self._clock = clock

    @traced("backtest.step.pre_trade")
    def execute(self, ctx: StepContext) -> StepResult:
        """执行 PreTrade 校验循环。"""
        if not ctx.is_rebalance_day:
            return StepResult.skipped()

        if ctx.execution_plan is None:
            return StepResult.skipped()

        ctx.require_slice()
        ctx.require_account_view()

        # 构建 PreTradeContext
        pre_trade_context = self._build_pre_trade_context(ctx)

        # 逐单校验
        decisions: list[PreTradeDecisionRecord] = []
        for order in ctx.execution_plan.orders:
            result = self._check_order(order, pre_trade_context)

            # 计算最终数量
            if result.decision == Decision.REJECT:
                final_qty = 0
            elif result.resized_quantity is not None:
                final_qty = result.resized_quantity
            else:
                final_qty = order.quantity

            # 审计记录
            decisions.append(
                PreTradeDecisionRecord(
                    trade_date=ctx.time_context.trade_date,
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    direction=order.direction.value,
                    original_quantity=order.quantity,
                    final_quantity=final_qty,
                    decision=self._DECISION_MAP.get(
                        result.decision,
                        result.decision.value,
                    ),
                    reason=result.reason,
                    check_sequence=result.triggered_checks,
                )
            )

            if result.decision == Decision.REJECT:
                continue

            # 确定最终订单
            final_order = (
                order.with_quantity(result.resized_quantity)
                if result.resized_quantity is not None
                else order
            )

            # 提交订单
            self._place_order(final_order)

            # 追加到 step_orders
            ctx.step_orders.append(final_order)

            # 发布 OrderSubmitted 事件
            self._publish_order_submitted(final_order)

            # F1: 滚动更新 PreTradeContext
            pre_trade_context = pre_trade_context.with_order_accepted(final_order)

        # 记录 PreTrade 决策
        ctx.pre_trade_decisions.extend(decisions)

        return StepResult.ok()

    def _build_pre_trade_context(self, ctx: StepContext) -> PreTradeContext:
        """构建 PreTrade 校验上下文。"""
        # require_*() 已在 execute() 中调用，此处一定非 None
        account_view = ctx.require_account_view()

        return PreTradeContext(
            account_view=account_view,
            rules=ctx.rules or {},
            market_snapshots=ctx.bars,
            fee_model=self._fee_model,
            buying_power_model=CashAccountBuyingPower(),
            pending_tickets=ctx.order_book.get_pending() if ctx.order_book else (),
        )

    def _check_order(
        self,
        order: Order,
        pre_trade_context: PreTradeContext,
    ) -> OrderCheckResult:
        """调用 pre_trade_check.check_order。"""
        return self._pre_trade_check.check_order(order, pre_trade_context)

    def _place_order(self, order: Order) -> None:
        """通过 brokerage 提交订单。"""
        self._brokerage.place_order(order)

    def _publish_order_submitted(self, order: Order) -> None:
        """发布 OrderSubmitted 事件。"""
        if self._event_bus is not None:
            self._event_bus.publish(
                OrderSubmitted(
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    side=order.direction.value,
                    quantity=order.quantity,
                    timestamp=self._clock.now(),
                ),
            )
