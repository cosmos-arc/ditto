"""
ExecutionStep -- 处理 pending 订单成交.

对应 EngineLoop._step() 中成交处理部分:
  1. 从 slice_ 构建 ProcessInput
  2. brokerage.process_pending(process_input) -> fills
  3. 发布 OrderFilled 事件
  4. fills 追加到 ctx.step_fills
"""

from __future__ import annotations

from ditto_execution.brokerage import Brokerage, ProcessInput
from ditto_execution.events import OrderFilled
from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus

from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["ExecutionStep"]


class ExecutionStep:
    """成交处理步骤 -- 处理 pending 订单成交."""

    def __init__(
        self,
        brokerage: Brokerage,
        event_bus: EventBus | None,
        clock: Clock,
    ) -> None:
        self._brokerage = brokerage
        self._event_bus = event_bus
        self._clock = clock

    def execute(self, ctx: StepContext) -> StepResult:
        """处理成交。"""
        ctx.require_slice()

        # 构建 ProcessInput
        process_input = ProcessInput(
            step_time=ctx.time_context.decision_time,
            trade_date=ctx.time_context.trade_date,
            bars=ctx.bars,
        )

        # 处理成交
        fills = self._brokerage.process_pending(process_input)

        # 追加到 ctx.step_fills
        ctx.step_fills.extend(fills)

        # 发布 OrderFilled 事件
        if self._event_bus is not None:
            for fill in fills:
                self._event_bus.publish(
                    OrderFilled(
                        order_id=fill.order_id,
                        fill_price=fill.fill_price,
                        filled_quantity=fill.filled_quantity,
                        fee=fill.fee,
                        timestamp=self._clock.now(),
                    ),
                )

        return StepResult.ok()
