"""
Pytest conftest for backtest unit tests -- shared helpers.

所有 backtest 子测试使用的工厂函数和常量。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_backtest.data_feed import MarketSnapshot, Slice
from ditto_execution.planner import ExecutionPlan
from ditto_kernel.clock import Clock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.order_book import Order, OrderBookReadOnly
from ditto_risk.post_trade import (
    RiskAction,
    RiskActionType,
    RiskScope,
    RiskSeverity,
)

IID_1 = InstrumentId(1)
IID_2 = InstrumentId(2)


def _make_snapshot(iid: InstrumentId = IID_1, close: float = 10.0) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-03-01",
        instrument_id=iid,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=10_000_000.0,
    )


def _make_slice(
    date: str = "2026-03-01",
    bars: dict[InstrumentId, MarketSnapshot] | None = None,
) -> Slice:
    bars = bars or {IID_1: _make_snapshot(IID_1)}
    return Slice(
        trade_date=date,
        step_time=datetime(2026, 3, 1, 15, 0),
        bars=bars,
    )


def _make_cash(available: float = 500_000.0) -> CashBook:
    return CashBook(available=available, settled=available, frozen=0.0)


def _make_account_view(cash: CashBook | None = None) -> AccountView:
    cash = cash or _make_cash()
    return AccountView(
        positions=MappingProxyType({}),
        cash=cash,
        total_value=1_000_000.0,
        nav=1_000_000.0,
        exposure=0.0,
        pending_buy_value=0.0,
        order_book=OrderBookReadOnly({}),
    )


def _make_clock() -> MagicMock:
    clock = MagicMock(spec=Clock)
    clock.now.return_value = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    return clock


def _make_risk_action(
    action_type: RiskActionType = RiskActionType.REDUCE_POSITION,
    instrument_id: InstrumentId | None = IID_1,
    scope: RiskScope = RiskScope.INSTRUMENT,
    severity: RiskSeverity = RiskSeverity.CRITICAL,
    rule_id: str = "single_loss_limit",
    cooldown_until_date: str | None = "2026-03-05",
) -> RiskAction:
    return RiskAction(
        action_type=action_type,
        instrument_id=instrument_id,
        scope=scope,
        severity=severity,
        rule_id=rule_id,
        detail="test risk action",
        current_value=0.15,
        threshold=0.10,
        cooldown_until_date=cooldown_until_date,
    )


def _make_fill(
    order_id: str = "ord-1",
    instrument_id: InstrumentId = IID_1,
    direction: OrderSide = OrderSide.BUY,
) -> FillEvent:
    return FillEvent(
        fill_id="fill-1",
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=100,
        fill_price=10.0,
        fee=5.0,
        slippage=0.0,
        event_time=datetime(2026, 3, 1, 15, 0),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _make_order(
    order_id: str = "ord-1",
    instrument_id: InstrumentId = IID_1,
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 100,
) -> Order:
    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
    )


def _make_execution_plan(orders: tuple[Order, ...] | None = None) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        trade_date="2026-03-01",
        orders=orders or (_make_order(),),
        estimated_turnover=10_000.0,
        estimated_cost=5.0,
        blocked_orders=(),
    )
