"""Uninterrupted and checkpoint/resume backtests must produce equal execution."""

from __future__ import annotations

from datetime import datetime

from ditto_backtest.audit.collector import ExecutionAuditCollector
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.config import EngineConfig
from ditto_backtest.data_feed import Slice
from ditto_backtest.engine import EngineLoop, EngineOptions
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestRuntimeStateSnapshot,
)
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.statistics import build_report
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_execution.fills import Filled
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    InstrumentDefinition,
    MarketSnapshot,
    TradingRuleSet,
)
from ditto_portfolio.accounting import Account, CashBook, FillEvent, Position
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.pipeline import StrategyInputBundle

_DAYS = ("2026-03-01", "2026-03-02", "2026-03-03")
_A = InstrumentId(1)
_LOCKED_B = InstrumentId(2)
_C = InstrumentId(3)
_SPEC_HASH = "d" * 64
_EMPTY_PARAMETER_HASH = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


class _ThreeDayFeed:
    def trading_days(self) -> list[str]:
        return list(_DAYS)

    def get_slice(self, trade_date: str) -> Slice:
        bars = {
            iid: MarketSnapshot(
                trade_date=trade_date,
                instrument_id=iid,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                prev_close=10.0,
                volume=1_000_000.0,
                amount=10_000_000.0,
            )
            for iid in (_A, _LOCKED_B, _C)
        }
        return Slice(
            trade_date=trade_date,
            step_time=datetime.fromisoformat(f"{trade_date}T15:00:00"),
            bars=bars,
        )


class _LockingTargetsPipeline:
    def run(
        self,
        context: StrategyContext,
        bundle: StrategyInputBundle,
    ) -> TargetPortfolio:
        if bundle.trade_date == _DAYS[0]:
            context.lock_instrument(
                _LOCKED_B,
                "cooldown",
                cooldown_until="2026-03-10",
            )
        positions = {
            _DAYS[0]: {_A: 0.0201},
            _DAYS[1]: {_A: 0.0201, _LOCKED_B: 0.0101},
            _DAYS[2]: {_A: 0.0201, _LOCKED_B: 0.0101, _C: 0.0101},
        }[bundle.trade_date]
        return TargetPortfolio(
            trade_date=bundle.trade_date,
            strategy_id=bundle.strategy_id,
            run_id=bundle.run_id,
            positions=positions,
            cash_target=1.0 - sum(positions.values()),
        )


class _HundredShareFillModel:
    def try_fill(
        self,
        order: Order,
        market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> Filled:
        del definition, trading_rule
        quantity = min(100, order.quantity)
        return Filled(
            fill_event=FillEvent(
                fill_id="",
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                direction=order.direction,
                filled_quantity=quantity,
                fill_price=market.close,
                fee=0.0,
                slippage=0.0,
                event_time=datetime.min,
                cumulative_quantity=0,
                leaves_quantity=order.quantity - quantity,
            )
        )


def _config(*, start_date: str, run_id: str) -> EngineConfig:
    return EngineConfig(
        start_date=start_date,
        end_date=_DAYS[-1],
        initial_cash=100_000.0,
        spec_hash=_SPEC_HASH,
        base_spec_hash=_SPEC_HASH,
        parameter_hash=_EMPTY_PARAMETER_HASH,
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        strategy_id="resume-determinism",
        strategy_run_id=run_id,
        execution_delay=1,
    )


def _account_from_snapshot(snapshot: BacktestAccountStateSnapshot) -> Account:
    cash = CashBook(
        available=snapshot.cash_available,
        settled=snapshot.cash_settled,
        frozen=snapshot.cash_frozen,
    )
    positions = {
        item.instrument_id: Position(
            instrument_id=item.instrument_id,
            quantity=item.quantity,
            available_quantity=item.available_quantity,
            average_cost=item.average_cost,
            market_value=item.market_value,
            unrealized_pnl=item.unrealized_pnl,
            realized_pnl=item.realized_pnl,
            total_fees=item.total_fees,
        )
        for item in snapshot.positions
    }
    return Account(cash=cash, positions=positions)


def _order_book_from_runtime(runtime: BacktestRuntimeStateSnapshot) -> OrderBook:
    book = OrderBook(journal=InMemoryOrderEventJournal())
    for item in runtime.pending_orders:
        book.restore_ticket(
            OrderTicket(
                order=Order(
                    client_id=ClientOrderId(item.client_order_id),
                    instrument_id=item.instrument_id,
                    order_type=OrderType(item.order_type),
                    direction=OrderSide(item.direction),
                    quantity=item.quantity,
                    price=item.price,
                    stop_price=item.stop_price,
                    trade_date=item.trade_date,
                ),
                status=OrderStatus(item.status),
                filled_quantity=item.filled_quantity,
                filled_price=item.filled_price,
                average_fill_price=item.average_fill_price,
            )
        )
    return book


def _loop(
    *,
    start_date: str,
    run_id: str,
    account: Account | None = None,
    order_book: OrderBook | None = None,
    runtime: BacktestRuntimeStateSnapshot | None = None,
    should_stop: object | None = None,
    audit_collector: ExecutionAuditCollector | None = None,
) -> EngineLoop:
    config = _config(start_date=start_date, run_id=run_id)
    feed = _ThreeDayFeed()
    brokerage = BacktestBrokerage(
        account=account
        or Account(cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)),
        order_book=order_book or OrderBook(journal=InMemoryOrderEventJournal()),
        model=BrokerageModel(fill_model=_HundredShareFillModel()),
    )
    clock = SimulatedClock(initial=datetime(2026, 3, 1, 15, 0))
    return EngineLoop(
        config=config,
        pipeline=_LockingTargetsPipeline(),  # type: ignore[arg-type]
        planner=SimpleExecutionPlanner(),
        brokerage=brokerage,
        pre_trade_check=CompositePreTradeCheck(checks=()),
        data_feed=feed,  # type: ignore[arg-type]
        synchronizer=BacktestSynchronizer(
            data_feed=feed,  # type: ignore[arg-type]
            clock=clock,
            start_date=start_date,
        ),
        options=EngineOptions(
            audit_collector=audit_collector or ExecutionAuditCollector(),
            restore_runtime_state=runtime,
            should_stop=should_stop,  # type: ignore[arg-type]
        ),
    )


def test_uninterrupted_equals_checkpoint_resume_with_all_runtime_state() -> None:  # noqa: PLR0915
    """Pending work, cooldown locks, and IDs survive one cooperative pause."""
    uninterrupted_audit = ExecutionAuditCollector()
    uninterrupted = _loop(
        start_date=_DAYS[0],
        run_id="full",
        audit_collector=uninterrupted_audit,
    ).run()
    stop_calls = 0

    def _stop_before_day_three() -> bool:
        nonlocal stop_calls
        stop_calls += 1
        return stop_calls >= 3

    parent_audit = ExecutionAuditCollector()
    parent = _loop(
        start_date=_DAYS[0],
        run_id="parent",
        should_stop=_stop_before_day_three,
        audit_collector=parent_audit,
    ).run()
    assert parent.cancelled is True
    assert parent.last_checkpoint is not None
    account_state = parent.last_checkpoint.account_state
    runtime = parent.last_checkpoint.runtime_state
    assert account_state is not None
    assert runtime is not None
    assert [item.client_order_id for item in runtime.pending_orders] == ["plan-order-1"]
    assert runtime.pending_orders[0].leaves_quantity == 100
    assert len(runtime.delayed_signals) == 1
    assert runtime.planner_id_counter == 2
    assert runtime.brokerage_fill_counter == 1
    assert runtime.trade_builder_state is not None
    assert runtime.trade_builder_state.counter == 1
    assert [
        entry.trade_id for entry in runtime.trade_builder_state.fifo_open_entries
    ] == ["trade-1"]
    runtime_json = runtime.to_json()
    restored_runtime = BacktestRuntimeStateSnapshot.from_json(runtime_json)
    assert restored_runtime.to_json() == runtime_json
    assert restored_runtime.state_hash == runtime.state_hash
    # A cooperative pause is not terminal completion: open trades remain only
    # in checkpoint state and must not be emitted as closed audit records.
    assert parent_audit.get_closed_trades() == ()
    assert [lock.instrument_id for lock in runtime.strategy_context.risk_locks] == [
        _LOCKED_B
    ]

    resumed_audit = ExecutionAuditCollector()
    resumed = _loop(
        start_date=_DAYS[2],
        run_id="resumed",
        account=_account_from_snapshot(account_state),
        order_book=_order_book_from_runtime(restored_runtime),
        runtime=restored_runtime,
        audit_collector=resumed_audit,
    ).run()

    assert parent.orders + resumed.orders == uninterrupted.orders
    assert parent.fills + resumed.fills == uninterrupted.fills
    assert resumed.account_view == uninterrupted.account_view
    assert [order.client_id.value for order in resumed.orders] == ["plan-order-4"]
    assert [fill.fill_id for fill in resumed.fills] == ["fill-2", "fill-3"]
    # The resumed-day pipeline targets B but never recreates its day-one lock;
    # only restored checkpoint state can keep B out of the generated orders.
    assert all(order.instrument_id != _LOCKED_B for order in resumed.orders)
    assert any(order.instrument_id == _C for order in resumed.orders)
    assert resumed.last_checkpoint is not None
    assert uninterrupted.last_checkpoint is not None
    resumed_runtime = resumed.last_checkpoint.runtime_state
    full_runtime = uninterrupted.last_checkpoint.runtime_state
    assert resumed_runtime is not None
    assert full_runtime is not None
    assert resumed_runtime.strategy_context.risk_locks[0].instrument_id == _LOCKED_B
    assert resumed_runtime.trade_builder_state == full_runtime.trade_builder_state
    assert resumed_runtime.trade_builder_state is not None
    assert resumed_runtime.trade_builder_state.counter == 3
    assert resumed_runtime.trade_builder_state.fifo_open_entries == ()
    assert [trade.trade_id for trade in resumed_audit.get_closed_trades()] == [
        "trade-1",
        "trade-2",
        "trade-3",
    ]
    assert build_report(
        resumed_audit,
        run_id="logical-run",
    ) == build_report(
        uninterrupted_audit,
        run_id="logical-run",
    )
