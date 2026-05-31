"""Pre-trade context and data models — 订单提交前校验的上下文与结果类型."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from ditto_kernel.identity import (
    InstrumentId as _InstrumentId,
)
from ditto_kernel.order import OrderSide
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
    FeeModel,
    FeeSchedule,
    InstrumentRules,
    MarketSnapshot,
)
from ditto_portfolio.accounting import (
    AccountView,
    BuyingPowerModel,
    CashBook,
)

from ditto_risk.contracts import PreTradeOrder, PreTradeTicket

__all__ = [
    "Decision",
    "OrderCheckResult",
    "PreTradeContext",
]


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class Decision(StrEnum):
    """PreTrade 校验决策类型。"""

    ACCEPT = "accept"
    REJECT = "reject"
    RESIZE = "resize"


# ---------------------------------------------------------------------------
# PreTradeContext — F1 rolling context (V3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreTradeContext:
    """
    PreTrade 校验所需的只读上下文 — 每笔订单通过后滚动更新。

    V3 完整版：使用 rules + market_snapshots + buying_power_model
    替代 V1 的 estimated_prices / lot_size / fee_schedule。

    Attributes:
        account_view: 账户只读快照
        rules: 三层规则映射 (instrument_id -> InstrumentRules)
        market_snapshots: 市场快照映射 (instrument_id -> MarketSnapshot)
        fee_model: 手续费估算模型
        buying_power_model: 购买力模型
        pending_tickets: 当日已提交待处理订单

    """

    account_view: AccountView
    rules: dict[_InstrumentId, InstrumentRules]
    market_snapshots: dict[_InstrumentId, MarketSnapshot]
    buying_power_model: BuyingPowerModel
    fee_model: FeeModel | None = None
    pending_tickets: tuple[PreTradeTicket, ...] = ()

    # -- 辅助方法 ---------------------------------------------------------

    def price_for(self, iid: _InstrumentId) -> float | None:
        """从 market_snapshots 获取 close price。"""
        snapshot = self.market_snapshots.get(iid)
        if snapshot is None:
            return None
        return snapshot.close

    def lot_size_for(self, iid: _InstrumentId) -> int:
        """从 rules[iid][0].lot_size 获取，默认 DEFAULT_LOT_SIZE。"""
        instrument_rules = self.rules.get(iid)
        if instrument_rules is None:
            return DEFAULT_LOT_SIZE
        return instrument_rules[0].lot_size

    def fee_schedule_for(self, iid: _InstrumentId) -> FeeSchedule:
        """从 rules[iid][2] 获取。"""
        instrument_rules = self.rules.get(iid)
        if instrument_rules is None:
            return FeeSchedule(
                instrument_id=_InstrumentId(0),
                as_of_date="",
                commission_rate=DEFAULT_COMMISSION_RATE,
                min_commission=DEFAULT_MIN_COMMISSION,
                stamp_duty_rate=0.0,
                transfer_fee_rate=0.0,
            )
        return instrument_rules[2]

    def estimate_order_cost(self, order: PreTradeOrder) -> float:
        """估算订单成本 = price * quantity + fee。"""
        price = self.price_for(order.instrument_id)
        if price is None:
            return 0.0
        cost = order.quantity * price
        fee_schedule = self.fee_schedule_for(order.instrument_id)
        cost += (
            self.fee_model.estimate(order, price, fee_schedule)
            if self.fee_model is not None
            else 0.0
        )
        return cost

    def with_order_accepted(self, order: PreTradeOrder) -> PreTradeContext:
        """返回包含此订单影响的新上下文 — 保持 frozen 语义 (F1)。"""
        price = self.price_for(order.instrument_id)
        if price is None:
            return self

        estimated_cost = self.estimate_order_cost(order)

        if order.direction == OrderSide.BUY:
            new_cash = CashBook(
                available=self.account_view.cash.available - estimated_cost,
                settled=self.account_view.cash.settled,
                frozen=self.account_view.cash.frozen + estimated_cost,
            )
            new_view = replace(
                self.account_view,
                cash=new_cash,
            )
        else:
            # B3: 卖出时递减 available_quantity — 防止批内超卖
            position = self.account_view.positions.get(order.instrument_id)
            if position is not None:
                new_available = max(
                    0,
                    position.available_quantity - order.quantity,
                )
                new_position = replace(
                    position,
                    available_quantity=new_available,
                )
                new_positions = dict(self.account_view.positions)
                new_positions[order.instrument_id] = new_position
                new_view = replace(
                    self.account_view,
                    positions=new_positions,
                )
            else:
                new_view = self.account_view

        return replace(
            self,
            account_view=new_view,
        )


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderCheckResult:
    """
    PreTrade 校验结果。

    Attributes:
        decision: 校验决策 (ACCEPT / REJECT / RESIZE)
        order_id: 关联订单 ID
        resized_quantity: RESIZE 时的建议数量 (None = 未 resize)
        reason: 拒绝原因 (None = 通过或无原因)
        triggered_checks: 触发的规则名称列表

    """

    decision: Decision
    order_id: str
    resized_quantity: int | None = None
    reason: str | None = None
    triggered_checks: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def accept_order(order_id: str) -> OrderCheckResult:
    """构建 accept 结果的简写 — constraints/exposure 共享。"""
    return OrderCheckResult(decision=Decision.ACCEPT, order_id=order_id)
