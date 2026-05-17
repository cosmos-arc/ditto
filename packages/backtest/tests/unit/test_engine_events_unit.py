"""Engine 域事件接入 EngineLoop 单元测试."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from unittest.mock import Mock

from ditto_backtest.config import EngineConfig
from ditto_backtest.data_feed import Slice
from ditto_backtest.engine import EngineLoop, EngineOptions
from ditto_execution.events import (
    OrderFilled,
    OrderSubmitted,
)
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel import SimpleEventBus
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import DomainEvent
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.strategy import RiskScope
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
from ditto_kernel.time_context import TimeContext
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting import (
    AccountView,
    CashBook,
    FillEvent,
)
from ditto_risk.events import RiskGuardTriggered
from ditto_risk.post_trade import (
    RiskAction,
    RiskActionType,
    RiskSeverity,
)
from ditto_risk.pre_trade import Decision, OrderCheckResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


DAYS = ["2026-03-01"]

STEP_TIME = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)


def _make_clock() -> SimulatedClock:
    """构建测试用 SimulatedClock — tz-aware 以匹配 Slice.step_time."""
    return SimulatedClock(initial=STEP_TIME)


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
    )


def _make_snapshot(iid: int = 1, close: float = 10.0) -> MarketSnapshot:
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


def _make_slice(date: str = "2026-03-01") -> Slice:
    return Slice(
        trade_date=date,
        step_time=STEP_TIME,
        bars={1: _make_snapshot()},
    )


def _make_order(iid: int = 1, qty: int = 100) -> Order:
    return Order(
        client_id=ClientOrderId(value="order-001"),
        instrument_id=iid,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=qty,
    )


def _make_fill(iid: int = 1) -> FillEvent:
    return FillEvent(
        fill_id="fill-001",
        order_id="order-001",
        instrument_id=iid,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=5.0,
        slippage=0.001,
        event_time=STEP_TIME,
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _make_config() -> EngineConfig:
    return EngineConfig(
        start_date="2026-03-01",
        end_date="2026-03-01",
        initial_cash=1_000_000.0,
        strategy_id="default",
        strategy_run_id="run-001",
    )


def _make_engine_loop(
    event_bus: SimpleEventBus | None = None,
    post_trade_guard: Mock | None = None,
    brokerage: Mock | None = None,
    planner: Mock | None = None,
) -> EngineLoop:
    """构建测试用 EngineLoop — 跳过 rebalance day 以隔离事件测试."""
    config = _make_config()
    pipeline = Mock()
    planner = planner or Mock()
    custom_brokerage = brokerage is not None
    brokerage = brokerage or Mock()
    pre_trade_check = Mock()
    data_feed = Mock()
    fee_model = Mock()

    data_feed.trading_days.return_value = DAYS
    data_feed.get_slice.return_value = _make_slice()
    brokerage.get_account.return_value = _make_account_view()
    if not custom_brokerage:
        brokerage.process_pending.return_value = ()

    clock = _make_clock()

    # 构建 mock Synchronizer — 按 DAYS 生成 TimeSlice 流
    trading_days = [d for d in DAYS if d >= config.start_date]
    slices: list[TimeSlice] = []
    for day in trading_days:
        tc = TimeContext(
            decision_time=STEP_TIME,
            knowledge_date=STEP_TIME.date() - timedelta(days=1),
            trade_date=day,
        )
        slices.append(TimeSlice(time_context=tc, bars={}))
    sync = Mock(spec=Synchronizer)
    sync.clock.return_value = clock
    sync.stream.return_value = iter(slices)

    return EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        synchronizer=sync,
        options=EngineOptions(
            fee_model=fee_model,
            event_bus=event_bus,
            post_trade_guard=post_trade_guard,
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEngineLoopEvents:
    """EngineLoop 域事件接入测试."""

    def test_order_submitted_on_place_order(self) -> None:
        """place_order 后发布 OrderSubmitted 事件."""
        event_bus = SimpleEventBus()
        collected: list[DomainEvent] = []
        event_bus.subscribe("order_submitted", collected.append)

        order = _make_order()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(order,),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner = Mock()
        planner.plan.return_value = plan

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            order_id="order-001",
            decision=Decision.ACCEPT,
        )

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.place_order.return_value = Mock()
        brokerage.process_pending.return_value = ()

        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        config = _make_config()
        data_feed = Mock(
            trading_days=Mock(return_value=DAYS),
            get_slice=Mock(return_value=_make_slice()),
        )
        clock = _make_clock()

        # 构建 mock Synchronizer
        trading_days = [d for d in DAYS if d >= config.start_date]
        slices: list[TimeSlice] = []
        for day in trading_days:
            tc = TimeContext(
                decision_time=STEP_TIME,
                knowledge_date=STEP_TIME.date() - timedelta(days=1),
                trade_date=day,
            )
            slices.append(TimeSlice(time_context=tc, bars={}))
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = clock
        sync.stream.return_value = iter(slices)

        loop = EngineLoop(
            config=config,
            pipeline=Mock(),
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(
                fee_model=fee_model,
                event_bus=event_bus,
            ),
        )

        loop.run()

        submitted = [e for e in collected if isinstance(e, OrderSubmitted)]
        assert len(submitted) >= 1
        assert submitted[0].order_id == "order-001"
        assert submitted[0].instrument_id == 1

    def test_order_filled_on_process_pending(self) -> None:
        """process_pending 后发布 OrderFilled 事件."""
        event_bus = SimpleEventBus()
        collected: list[DomainEvent] = []
        event_bus.subscribe("order_filled", collected.append)

        fill = _make_fill()
        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = (fill,)

        # 跳过 rebalance — 非 rebalance day 只触发 process_pending
        loop = _make_engine_loop(
            event_bus=event_bus,
            brokerage=brokerage,
        )
        loop._is_rebalance_day = lambda date: False  # type: ignore[method-assign]

        loop.run()

        filled_events = [e for e in collected if isinstance(e, OrderFilled)]
        assert len(filled_events) >= 1
        assert filled_events[0].order_id == "order-001"
        assert filled_events[0].fill_price == 10.0

    def test_risk_guard_triggered_on_post_trade(self) -> None:
        """PostTrade 风控扫描发布 RiskGuardTriggered 事件."""
        event_bus = SimpleEventBus()
        collected: list[DomainEvent] = []
        event_bus.subscribe("risk_guard_triggered", collected.append)

        risk_action = RiskAction(
            rule_id="max_drawdown",
            instrument_id=1,
            scope=RiskScope.INSTRUMENT,
            severity=RiskSeverity.CRITICAL,
            action_type=RiskActionType.LIQUIDATE,
            detail="drawdown exceeded",
            current_value=0.15,
            threshold=0.10,
            cooldown_until_date="2026-03-02",
        )
        post_trade_guard = Mock()
        post_trade_guard.scan.return_value = (risk_action,)

        # 跳过 rebalance — PostTrade 在 rebalance 检查之前执行
        loop = _make_engine_loop(
            event_bus=event_bus,
            post_trade_guard=post_trade_guard,
        )
        loop._is_rebalance_day = lambda date: False  # type: ignore[method-assign]

        loop.run()

        risk_events = [e for e in collected if isinstance(e, RiskGuardTriggered)]
        assert len(risk_events) >= 1
        assert risk_events[0].rule_name == "max_drawdown"
        assert risk_events[0].severity == RiskSeverity.CRITICAL

    def test_no_events_when_event_bus_none(self) -> None:
        """event_bus=None 时零副作用 — 不抛异常."""
        fill = _make_fill()
        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = (fill,)

        loop = _make_engine_loop(event_bus=None, brokerage=brokerage)
        loop._is_rebalance_day = lambda date: False  # type: ignore[method-assign]

        # 不应抛异常
        result = loop.run()
        assert result.run_id == "run-001"
