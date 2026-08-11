"""Application adapter for the backtest-owned continuous risk port."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ditto_application.processes.risk.backtest_adapter import (
    ContinuousRiskBacktestAdapter,
)
from ditto_application.processes.risk.fingerprint import position_fingerprint
from ditto_backtest.risk_runtime import BacktestRiskContext
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import Account, CashBook, FillEvent, Position
from ditto_risk.continuous_gate import ContinuousRiskGate


def _account_view():
    return Account(
        cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
    ).get_view()


def _context() -> BacktestRiskContext:
    return BacktestRiskContext(
        trade_date="2026-04-01",
        account_view=_account_view(),
        bars={},
    )


def test_adapter_runs_gate_and_round_trips_canonical_state() -> None:
    adapter = ContinuousRiskBacktestAdapter(
        gate=ContinuousRiskGate(account_id="research-1", sleeve_id="core"),
        account_id="research-1",
        sleeve_id="core",
    )
    daily = adapter.daily_scan(_context())
    order = Order(
        client_id=ClientOrderId("order-1"),
        instrument_id=1,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=100,
        price=10.0,
        trade_date="2026-04-01",
    )

    decision = adapter.pre_trade(order, _context())
    payload_json = adapter.snapshot_state_json()

    assert daily.readiness == "ready"
    assert decision.allow is True
    assert decision.adjusted_order == order
    assert payload_json.startswith('{"account_id":"research-1"')

    restored = ContinuousRiskBacktestAdapter(
        gate=ContinuousRiskGate(account_id="research-1", sleeve_id="core"),
        account_id="research-1",
        sleeve_id="core",
    )
    restored.restore_state_json(payload_json, _account_view())
    assert restored.snapshot_state_json() == payload_json


def test_adapter_replays_an_earlier_fill_idempotently_after_later_fills() -> None:
    adapter = ContinuousRiskBacktestAdapter(
        gate=ContinuousRiskGate(account_id="research-1", sleeve_id="core"),
        account_id="research-1",
        sleeve_id="core",
    )
    first = FillEvent(
        fill_id="fill-1",
        order_id="order-1",
        instrument_id=1,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=1.0,
        slippage=0.0,
        event_time=datetime(2026, 4, 1, 2, tzinfo=UTC),
        cumulative_quantity=100,
        leaves_quantity=0,
    )

    adapter.post_fill(first, _context(), "event-1")
    adapter.post_fill(
        replace(first, fill_id="fill-2", order_id="order-2"),
        _context(),
        "event-2",
    )
    before_replay = adapter.snapshot_state_json()
    adapter.post_fill(first, _context(), "event-1")

    assert adapter.snapshot_state_json() == before_replay


def test_position_fingerprint_ignores_t1_availability_but_not_holdings() -> None:
    position = Position(
        instrument_id=1,
        quantity=100,
        available_quantity=0,
        average_cost=10.0,
        market_value=1_000.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )

    frozen = Account(positions={1: position}).get_view()
    settled = Account(
        positions={1: replace(position, available_quantity=100)}
    ).get_view()
    changed = Account(
        positions={1: replace(position, quantity=200, available_quantity=100)}
    ).get_view()

    assert position_fingerprint(frozen) == position_fingerprint(settled)
    assert position_fingerprint(frozen) != position_fingerprint(changed)
