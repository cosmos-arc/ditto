"""EngineLoop unit tests — 7 scenarios with mock objects + boundary tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from types import MappingProxyType
from typing import NamedTuple
from unittest.mock import Mock

import pytest
from ditto_backtest.data_feed import Slice
from ditto_backtest.engine import EngineConfig, EngineLoop, EngineOptions
from ditto_backtest.result import (
    BacktestCheckpoint,
    BacktestDelayedSignalSnapshot,
    BacktestFrozenQuantitySnapshot,
    BacktestRuntimeStateCapture,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
    BacktestStrategyContextSnapshot,
    BacktestTargetWeightSnapshot,
)
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.trade_builder import (
    FifoOpenEntrySnapshot,
    TradeBuilderStateSnapshot,
    TradeMatchingMethod,
)
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
from ditto_kernel.time_context import TimeContext
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.accounting import (
    AccountView,
    CashBook,
    Position,
)
from ditto_risk.pre_trade import (
    Decision,
    OrderCheckResult,
)
from ditto_strategy.alpha.context import StrategyContextSnapshot
from ditto_strategy.alpha.models import TargetPortfolio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


DAYS = ["2026-03-01", "2026-03-02", "2026-03-03"]
_CANONICAL_SPEC_HASH = "d" * 64
_EMPTY_PARAMETER_HASH = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def test_engine_config_requires_full_canonical_spec_hash() -> None:
    """执行配置不得缺失或接受截断的 spec hash。"""
    required: dict[str, object] = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-03",
        "initial_cash": 1_000_000.0,
        "base_spec_hash": "b" * 64,
        "parameter_hash": _EMPTY_PARAMETER_HASH,
        "effective_parameters": (),
        "research_snapshot_id": None,
        "research_snapshot_manifest_hash": None,
    }

    with pytest.raises(TypeError, match="spec_hash"):
        EngineConfig(**required)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="spec_hash"):
        EngineConfig(**required, spec_hash="a" * 16)  # type: ignore[arg-type]


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


def _make_account_view_with_position() -> AccountView:
    """构建带持仓的账户快照，用于 checkpoint state 断言。"""
    cash = CashBook(available=700_000.0, settled=680_000.0, frozen=20_000.0)
    position = Position(
        instrument_id=InstrumentId(2),
        quantity=300,
        available_quantity=200,
        average_cost=100.0,
        market_value=33_000.0,
        unrealized_pnl=3_000.0,
        realized_pnl=500.0,
        total_fees=12.5,
    )
    return AccountView(
        positions=MappingProxyType({InstrumentId(2): position}),
        cash=cash,
        total_value=733_000.0,
        nav=733_000.0,
        exposure=33_000.0,
    )


def _make_snapshot(
    iid: int = 1,
    close: float = 10.0,
) -> MarketSnapshot:
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


def _make_slice(date: str, bars: dict[int, MarketSnapshot] | None = None) -> Slice:
    bars = bars or {1: _make_snapshot()}
    return Slice(
        trade_date=date,
        step_time=datetime(2026, 3, 1, 15, 0),
        bars=bars,
    )


def _make_target(date: str = "2026-03-01") -> TargetPortfolio:
    return TargetPortfolio(
        trade_date=date,
        strategy_id="default",
        run_id="run-001",
        positions={1: 0.5},
        cash_target=0.5,
    )


def _make_order(
    iid: int = 1,
    qty: int = 100,
    direction: OrderSide = OrderSide.BUY,
) -> Order:
    return Order(
        client_id=ClientOrderId(value="order-001"),
        instrument_id=iid,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=qty,
    )


def _make_config() -> EngineConfig:
    return EngineConfig(
        start_date="2026-03-01",
        end_date="2026-03-03",
        initial_cash=1_000_000.0,
        spec_hash=_CANONICAL_SPEC_HASH,
        base_spec_hash=_CANONICAL_SPEC_HASH,
        parameter_hash=_EMPTY_PARAMETER_HASH,
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        strategy_id="default",
        strategy_run_id="run-001",
    )


def _make_clock() -> SimulatedClock:
    """构建测试用 SimulatedClock — naive datetime 以匹配 Slice.step_time."""
    return SimulatedClock(initial=datetime(2026, 3, 1, 15, 0))


def _make_synchronizer(
    data_feed: Mock,
    config: EngineConfig,
    clock: SimulatedClock,
) -> Mock:
    """构建 mock Synchronizer — 按交易日生成 TimeSlice 流.

    stream() 使用 callable 以延迟读取 data_feed.trading_days()，
    确保在调用时（而非构建时）获取最新的 return_value。
    """
    sync = Mock(spec=Synchronizer)
    sync.clock.return_value = clock

    def _make_stream() -> list[TimeSlice]:
        from datetime import timedelta

        step_time = datetime(2026, 3, 1, 15, 0)
        trading_days = [d for d in data_feed.trading_days() if d >= config.start_date]
        slices: list[TimeSlice] = []
        for day in trading_days:
            tc = TimeContext(
                decision_time=step_time,
                knowledge_date=(
                    step_time.date() - timedelta(days=config.knowledge_lag_days)
                ),
                trade_date=day,
            )
            slices.append(TimeSlice(time_context=tc, bars={}))
        return iter(slices)

    sync.stream.side_effect = _make_stream
    return sync


def _make_engine_loop(
    config: EngineConfig | None = None,
    pipeline: Mock | None = None,
    planner: Mock | None = None,
    brokerage: Mock | None = None,
    pre_trade_check: Mock | None = None,
    data_feed: Mock | None = None,
    fee_model: Mock | None = None,
    restore_runtime_state: BacktestRuntimeStateSnapshot | None = None,
) -> EngineLoop:
    config = config or _make_config()
    pipeline = pipeline or Mock()
    planner = planner or Mock()
    brokerage = brokerage or Mock()
    pre_trade_check = pre_trade_check or Mock()
    data_feed = data_feed or Mock()
    fee_model = fee_model or Mock()

    # Default data_feed mock
    if not data_feed.trading_days.called and not hasattr(
        data_feed, "_side_effects_set"
    ):
        data_feed.trading_days.return_value = DAYS

    clock = _make_clock()
    return EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        synchronizer=_make_synchronizer(data_feed, config, clock),
        options=EngineOptions(
            fee_model=fee_model,
            restore_runtime_state=restore_runtime_state,
        ),
    )


class _WiredMocks(NamedTuple):
    """_make_wired_engine_loop 返回的 mock 引用集合."""

    loop: EngineLoop
    pipeline: Mock
    brokerage: Mock
    data_feed: Mock


def _make_wired_engine_loop(
    should_stop: Callable[[], bool] | None = None,
    on_checkpoint: Callable[[object], None] | None = None,
    execution_delay: int = 0,
) -> _WiredMocks:
    """构建完整 mock 的 EngineLoop（3 天回测 + pipeline/planner/brokerage 配置）.

    集中管理 TestThreeDayStep 和 TestCooperativeCancellation 共享的
    mock setup，消除重复。
    """
    config = replace(_make_config(), execution_delay=execution_delay)
    data_feed = Mock()
    data_feed.trading_days.return_value = DAYS
    data_feed.get_slice.side_effect = [_make_slice(d) for d in DAYS]

    pipeline = Mock()
    pipeline.run.return_value = _make_target()

    planner = Mock()
    order = _make_order()
    plan = Mock(
        plan_id="plan-001",
        trade_date="2026-03-01",
        orders=(order,),
        estimated_turnover=0.0,
        estimated_cost=0.0,
        blocked_orders=(),
    )
    planner.plan.return_value = plan

    brokerage = Mock()
    brokerage.get_account.return_value = _make_account_view()
    brokerage.place_order.return_value = Mock()
    brokerage.process_pending.return_value = ()

    pre_trade_check = Mock()
    pre_trade_check.check_order.return_value = OrderCheckResult(
        decision=Decision.ACCEPT,
        order_id="order-001",
    )

    fee_model = Mock()
    fee_model.estimate.return_value = 5.0

    clock = _make_clock()
    loop = EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        synchronizer=_make_synchronizer(data_feed, config, clock),
        options=EngineOptions(
            fee_model=fee_model,
            should_stop=should_stop,
            on_checkpoint=on_checkpoint,
        ),
    )
    return _WiredMocks(
        loop=loop,
        pipeline=pipeline,
        brokerage=brokerage,
        data_feed=data_feed,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_engine_loop_accepts_dependency_bundle() -> None:
    """EngineLoop should accept runtime collaborators as one dependency bundle."""
    from ditto_backtest.engine import EngineLoopDeps

    config = _make_config()
    data_feed = Mock()
    data_feed.trading_days.return_value = []

    synchronizer = Mock(spec=Synchronizer)
    synchronizer.clock.return_value = _make_clock()
    synchronizer.stream.return_value = iter(())

    brokerage = Mock()
    brokerage.get_account.return_value = _make_account_view()

    loop = EngineLoop(
        config,
        EngineLoopDeps(
            pipeline=Mock(),
            planner=Mock(),
            brokerage=brokerage,
            pre_trade_check=Mock(),
            data_feed=data_feed,
            synchronizer=synchronizer,
            options=EngineOptions(),
        ),
    )

    result = loop.run()

    assert result.run_id == "run-001"
    assert result.period == ("2026-03-01", "2026-03-03")


class TestThreeDayStep:
    """Scenario 1: 3-day backtest with pipeline + planner + brokerage."""

    def test_three_day_step(self) -> None:
        """3 trading days → pipeline called 3 times, result has correct period."""
        wired = _make_wired_engine_loop()
        result = wired.loop.run()

        assert result.period == ("2026-03-01", "2026-03-03")
        assert result.run_id == "run-001"
        assert wired.pipeline.run.call_count == 3
        assert wired.brokerage.place_order.call_count == 3


class TestDefaultInputBundlePitBoundary:
    """Default input bundle must use the synchronizer's frozen market bars."""

    def test_default_bundle_uses_synchronizer_bars_not_second_slice_read(self) -> None:
        """普通策略输入不得从 EngineLoop 的第二次 get_slice 读取污染 bar."""
        config = replace(
            _make_config(),
            start_date="2026-03-01",
            end_date="2026-03-01",
        )
        iid = InstrumentId(1)
        synchronizer_bar = _make_snapshot(iid=1, close=10.0)
        polluted_second_read_bar = _make_snapshot(iid=1, close=99.0)

        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = Slice(
            trade_date="2026-03-01",
            step_time=datetime(2026, 3, 1, 15, 0),
            bars={iid: polluted_second_read_bar},
            benchmark_close=None,
        )

        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = _make_clock()
        sync.stream.return_value = iter(
            [
                TimeSlice(
                    time_context=tc,
                    bars={iid: synchronizer_bar},
                ),
            ],
        )

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        planner.plan.return_value = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.get_order_book.return_value = Mock()
        brokerage.process_pending.return_value = ()

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=Mock(),
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(fee_model=Mock()),
        )

        loop.run()

        input_bundle = pipeline.run.call_args.args[1]
        assert input_bundle.market_data["close"].to_list() == [10.0]

    def test_default_bundle_uses_synchronizer_benchmark_not_second_slice_read(
        self,
    ) -> None:
        """普通策略输入不得从 EngineLoop 的第二次 get_slice 读取污染 benchmark."""
        config = replace(
            _make_config(),
            start_date="2026-03-01",
            end_date="2026-03-01",
        )
        iid = InstrumentId(1)
        synchronizer_bar = _make_snapshot(iid=1, close=10.0)
        polluted_second_read_bar = _make_snapshot(iid=1, close=99.0)

        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = Slice(
            trade_date="2026-03-01",
            step_time=datetime(2026, 3, 1, 15, 0),
            bars={iid: polluted_second_read_bar},
            benchmark_close=9999.0,
        )

        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = _make_clock()
        sync.stream.return_value = iter(
            [
                TimeSlice(
                    time_context=tc,
                    bars={iid: synchronizer_bar},
                    benchmark_close=3000.0,
                ),
            ],
        )

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        planner.plan.return_value = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.get_order_book.return_value = Mock()
        brokerage.process_pending.return_value = ()

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=Mock(),
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(fee_model=Mock()),
        )

        loop.run()

        input_bundle = pipeline.run.call_args.args[1]
        assert input_bundle.benchmark_close == 3000.0


class TestRunManifestSourceSnapshots:
    """RunManifest input refs should use synchronizer-carried provenance."""

    def test_manifest_uses_synchronizer_source_snapshot_ids(self) -> None:
        """Manifest 不应从 EngineLoop 的第二次 get_slice 读取 snapshot 污染值."""
        config = replace(
            _make_config(),
            start_date="2026-03-01",
            end_date="2026-03-01",
        )
        iid = InstrumentId(1)
        synchronizer_bar = _make_snapshot(iid=1, close=10.0)
        polluted_second_read_bar = _make_snapshot(iid=1, close=99.0)
        snapshot_id = "snapshot:tushare:stock_daily:2026-03-01:sync"

        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = Slice(
            trade_date="2026-03-01",
            step_time=datetime(2026, 3, 1, 15, 0),
            bars={iid: polluted_second_read_bar},
            benchmark_close=None,
            source_snapshot_ids={
                iid: "snapshot:tushare:stock_daily:2026-03-01:polluted",
            },
        )

        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = _make_clock()
        sync.stream.return_value = iter(
            [
                TimeSlice(
                    time_context=tc,
                    bars={iid: synchronizer_bar},
                    source_snapshot_ids={iid: snapshot_id},
                ),
            ],
        )

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        planner.plan.return_value = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.get_order_book.return_value = Mock()
        brokerage.process_pending.return_value = ()

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=Mock(),
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(fee_model=Mock()),
        )

        result = loop.run()

        assert result.manifest.input_ref_details[0].source_snapshot_id == snapshot_id


class TestNonRebalanceDaySkipsPipeline:
    """Scenario 2: Non-rebalance days skip pipeline."""

    def test_non_rebalance_day_skips_pipeline(self) -> None:
        """When _is_rebalance_day returns False, pipeline is NOT called."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = [_make_slice(d) for d in DAYS]

        pipeline = Mock()
        planner = Mock()
        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()
        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        # Patch _is_rebalance_day to return False for all dates
        original = loop._is_rebalance_day
        loop._is_rebalance_day = lambda date: False  # type: ignore[method-assign]

        loop.run()

        pipeline.run.assert_not_called()
        planner.plan.assert_not_called()

        # Restore
        loop._is_rebalance_day = original  # type: ignore[method-assign]


class TestPreTradeRejectSkipsOrder:
    """Scenario 3: PreTrade reject → order NOT placed."""

    def test_pre_trade_reject_skips_order(self) -> None:
        """Rejected order should NOT be submitted to brokerage."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01")

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        order = _make_order()
        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(order,),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.REJECT,
            order_id="order-001",
            reason="insufficient buying power",
            triggered_checks=("buying_power",),
        )

        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )
        loop.run()

        brokerage.place_order.assert_not_called()


class TestPreTradeResizeApplied:
    """Scenario 4: PreTrade resize → resized order placed."""

    def test_pre_trade_resize_applied(self) -> None:
        """Accepted with resized_quantity → order resized and placed."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01")

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        original_order = _make_order(qty=150)
        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(original_order,),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        # Resize 150 → 200 (next lot size multiple)
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
            resized_quantity=200,
            triggered_checks=("lot_size",),
        )

        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )
        loop.run()

        # Verify the resized order was placed
        brokerage.place_order.assert_called_once()
        placed_order = brokerage.place_order.call_args[0][0]
        assert placed_order.quantity == 200


class TestRollingContextUpdates:
    """Scenario 5: Rolling context updates after each accepted order."""

    def test_rolling_context_updates(self) -> None:
        """PreTrade context should be updated after each accepted order (F1)."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01")

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        order1 = _make_order(iid=1)
        order2 = _make_order(iid=2)
        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(order1, order2),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
        )

        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        clock = _make_clock()

        # 构建 mock Synchronizer — 含 bars 以匹配 Slice 数据
        slice_data = data_feed.get_slice.return_value
        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        ts = TimeSlice(time_context=tc, bars=slice_data.bars)
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = clock
        sync.stream.return_value = iter([ts])

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(fee_model=fee_model),
        )
        loop.run()

        # check_order should be called twice (once per order)
        assert pre_trade_check.check_order.call_count == 2

        # Verify context rolling: second call's context should differ from first
        # The second call receives the updated context (with order1 accepted)
        first_call_context = pre_trade_check.check_order.call_args_list[0][0][1]
        second_call_context = pre_trade_check.check_order.call_args_list[1][0][1]
        # Context is a frozen dataclass — with_order_accepted should produce
        # a new instance, so they are different objects
        assert first_call_context is not second_call_context


class TestProcessInputConversion:
    """Scenario 6: Slice → ProcessInput conversion for brokerage.process_pending."""

    def test_process_input_conversion(self) -> None:
        """Slice is correctly converted to ProcessInput
        for brokerage.process_pending."""
        from ditto_execution.brokerage import ProcessInput

        config = _make_config()
        bars = {
            1: _make_snapshot(iid=1, close=10.0),
            2: _make_snapshot(iid=2, close=20.0),
        }
        slice_data = Slice(
            trade_date="2026-03-01",
            step_time=datetime(2026, 3, 1, 15, 0),
            bars=bars,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = slice_data

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()

        # 构建 mock Synchronizer — 含 bars 以匹配 Slice 数据
        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        ts = TimeSlice(time_context=tc, bars=bars)
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = clock
        sync.stream.return_value = iter([ts])

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(fee_model=fee_model),
        )
        loop.run()

        # Verify brokerage.process_pending was called with correct ProcessInput
        brokerage.process_pending.assert_called_once()
        call_arg = brokerage.process_pending.call_args[0][0]
        assert isinstance(call_arg, ProcessInput)
        assert call_arg.step_time == datetime(2026, 3, 1, 15, 0)
        assert call_arg.trade_date == "2026-03-01"
        assert 1 in call_arg.bars
        assert 2 in call_arg.bars
        assert call_arg.bars[1].close == 10.0
        assert call_arg.bars[2].close == 20.0


class TestRuleProviderInjection:
    """EngineLoop 注入 InstrumentRuleProvider → 传递规则给 Planner。"""

    def test_rule_provider_passes_rules_to_planner(self) -> None:
        """rule_provider 存在时，planner.plan 收到 rules 参数。"""
        from ditto_kernel.trading import InstrumentRuleProvider

        config = _make_config()
        bars = {
            1: _make_snapshot(iid=1),
            2: _make_snapshot(iid=2),
        }
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01", bars)

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        account_view = _make_account_view()
        brokerage = Mock()
        brokerage.get_account.return_value = account_view
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        rule_provider = Mock(spec=InstrumentRuleProvider)
        rules = {1: ("defn", "rule", "fee"), 2: ("defn", "rule", "fee")}
        rule_provider.get_rules.return_value = rules

        clock = _make_clock()

        # 构建 mock Synchronizer — 含 bars 以传递 instrument_ids
        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        ts = TimeSlice(time_context=tc, bars=bars)
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = clock
        sync.stream.return_value = iter([ts])

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(
                fee_model=fee_model,
                rule_provider=rule_provider,
            ),
        )
        loop.run()

        # rule_provider.get_rules called with correct args
        rule_provider.get_rules.assert_called_once_with(
            "2026-03-01",
            [1, 2],
        )

        # planner.plan received rules
        planner.plan.assert_called_once()
        call_kwargs = planner.plan.call_args[1]
        assert call_kwargs["rules"] == rules

    def test_no_rule_provider_planner_no_rules(self) -> None:
        """rule_provider 为 None 时，planner.plan 收到 rules=None。"""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01")

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )
        loop.run()

        planner.plan.assert_called_once()
        call_kwargs = planner.plan.call_args[1]
        assert call_kwargs["rules"] is None


class TestEmptyPlanNoOrders:
    """Scenario 7: Empty plan — no orders placed."""

    def test_empty_plan_no_orders(self) -> None:
        """Planner returns empty orders list → no place_order calls."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01")

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),  # Empty
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )
        result = loop.run()

        assert brokerage.place_order.call_count == 0
        assert result.total_trades == 0
        assert len(result.orders) == 0


# ---------------------------------------------------------------------------
# Part 05: _is_rebalance_day 边界测试
# ---------------------------------------------------------------------------


class TestIsRebalanceDay:
    """_is_rebalance_day 日期格式与频率边界测试."""

    def test_daily_always_true(self) -> None:
        config = _make_config()
        loop = _make_engine_loop(config=config)
        assert loop._is_rebalance_day("2026-03-01") is True
        assert loop._is_rebalance_day("2026-03-15") is True

    def test_fold_schedule_rebalances_only_at_fold_start(self) -> None:
        config = replace(_make_config(), rebalance_freq="fold_schedule")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}

        assert loop._is_rebalance_day(DAYS[0]) is True
        assert loop._is_rebalance_day(DAYS[1]) is False

    @pytest.mark.parametrize(
        "frequency",
        ["weekly", "monthly", "fold_schedule"],
    )
    def test_resume_preserves_original_calendar_phase(self, frequency: str) -> None:
        """A suffix run must not reinterpret its first day as a fold boundary."""
        config = replace(
            _make_config(),
            start_date=DAYS[-1],
            rebalance_freq=frequency,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        runtime = BacktestRuntimeStateSnapshot.from_state(
            BacktestRuntimeStateCapture(
                trade_builder_state=TradeBuilderStateSnapshot(
                    method=TradeMatchingMethod.FIFO,
                    counter=0,
                ),
                rebalance_calendar_start=DAYS[0],
            )
        )
        loop = _make_engine_loop(
            config=config,
            data_feed=data_feed,
            restore_runtime_state=runtime,
        )

        execution_days = loop._build_trading_days()

        assert execution_days == [DAYS[-1]]
        assert loop._is_rebalance_day(DAYS[-1]) is False

    @pytest.mark.parametrize(
        "frequency",
        ["weekly", "monthly", "fold_schedule"],
    )
    def test_fresh_mid_feed_run_starts_a_new_calendar_phase(
        self,
        frequency: str,
    ) -> None:
        """A fresh configured window still rebalances on its first session."""
        config = replace(
            _make_config(),
            start_date=DAYS[-1],
            rebalance_freq=frequency,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        loop = _make_engine_loop(config=config, data_feed=data_feed)

        execution_days = loop._build_trading_days()

        assert execution_days == [DAYS[-1]]
        assert loop._is_rebalance_day(DAYS[-1]) is True

    def test_weekly_monday_true(self) -> None:
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        # 2026-03-02 is Monday; prev trading day 2026-03-01 is Sunday (ISO week 9 vs 9)
        # 但 2026-03-01 isocalendar() week 9, 2026-03-02 isocalendar() week 10
        assert loop._is_rebalance_day("2026-03-02") is True

    def test_weekly_tuesday_false(self) -> None:
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        # 2026-03-03 is Tuesday; prev trading day 2026-03-02 is Monday (same ISO week)
        assert loop._is_rebalance_day("2026-03-03") is False

    def test_weekly_first_trading_day_of_week(self) -> None:
        """当周无周一交易日（如节假日），第一个交易日仍为 rebalance day。"""
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        # 2026-03-01 is Sunday (ISO week 9), 2026-03-04 is Wednesday (ISO week 10)
        loop._trading_days = ("2026-03-01", "2026-03-04")
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        assert loop._is_rebalance_day("2026-03-04") is True

    def test_weekly_invalid_date_fallback(self) -> None:
        """date 不在 trading_days 中 → weekly 模式下 fallback 为 daily (return True)."""
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        assert loop._is_rebalance_day("not-a-date") is True

    def test_monthly_first_day_of_month(self) -> None:
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        # First trading day in list → idx=0 → True
        assert loop._is_rebalance_day("2026-03-01") is True

    def test_monthly_same_month_false(self) -> None:
        """同一月内非首日 → False."""
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        # "2026-03-02" same month as "2026-03-01" (idx 0) → False
        assert loop._is_rebalance_day("2026-03-02") is False

    def test_monthly_different_month_true(self) -> None:
        """跨月 → True."""
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = ("2026-03-31", "2026-04-01")
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        # "2026-04-01" has month_prefix "2026-04", prev "2026-03" different → True
        assert loop._is_rebalance_day("2026-04-01") is True

    def test_monthly_date_not_in_trading_days_fallback(self) -> None:
        """date 不在 trading_days 中 → fallback 为 daily (return True)."""
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        loop._trading_day_index = {d: i for i, d in enumerate(loop._trading_days)}
        assert loop._is_rebalance_day("2026-06-01") is True

    def test_unknown_freq_defaults_true(self) -> None:
        """未知 rebalance_freq → 默认返回 True."""
        config = replace(_make_config(), rebalance_freq="quarterly")
        loop = _make_engine_loop(config=config)
        assert loop._is_rebalance_day("2026-03-01") is True


# ---------------------------------------------------------------------------
# T10: StepChain 失败日志 + skipped_dates
# ---------------------------------------------------------------------------


class TestStepChainFailureLogging:
    """Step 失败时记录 warning 日志 + 累积 skipped_dates."""

    def test_step_failure_records_skipped_date(self) -> None:
        """某个 Step 失败 → 该日期出现在 skipped_dates."""
        from ditto_backtest.steps import StepResult

        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = [_make_slice(d) for d in DAYS]

        pipeline = Mock()
        planner = Mock()
        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        # 让第二个 trading day 的 DataFetchStep 失败
        call_count = 0

        def _mock_execute(ctx: object) -> StepResult:
            nonlocal call_count
            call_count += 1
            # 第二次调用（对应第二天）失败
            if call_count == 2:
                return StepResult.fail("data fetch error")
            return StepResult.ok()

        # 替换 steps 的 execute 方法
        mock_step = Mock()
        mock_step.execute = _mock_execute
        loop._steps = (mock_step,)

        result = loop.run()

        assert result.skipped_dates == ("2026-03-02",)

    def test_all_steps_succeed_no_skipped_dates(self) -> None:
        """所有 Step 成功 → skipped_dates 为空."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = [_make_slice(d) for d in DAYS]

        pipeline = Mock()
        pipeline.run.return_value = _make_target()
        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        result = loop.run()

        assert result.skipped_dates == ()

    def test_step_failure_logs_warning(self) -> None:
        """Step 失败时 logger.warning 被调用."""
        from unittest.mock import patch

        from ditto_backtest.steps import StepResult

        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = _make_slice("2026-03-01")

        pipeline = Mock()
        planner = Mock()
        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        # 让 step 失败
        mock_step = Mock()
        mock_step.execute.return_value = StepResult.fail("test error msg")
        loop._steps = (mock_step,)

        with patch("ditto_backtest.engine.logger") as mock_logger:
            result = loop.run()

        assert result.skipped_dates == ("2026-03-01",)
        # _step 中的 warning: logger.warning(
        #   "Step {} failed on {}: {}", step_name, date, errors)
        step_warning_call = mock_logger.warning.call_args_list[0]
        # args: ("Step {} failed on {}: {}", step_name, date, errors)
        assert step_warning_call[0][2] == "2026-03-01"
        assert "test error msg" in step_warning_call[0][3]
        # run 结尾的 skipped_dates 摘要
        summary_call = mock_logger.warning.call_args_list[-1]
        assert summary_call[0][0] == "StepChain skipped {} date(s): {}"

    def test_multiple_failures_all_recorded(self) -> None:
        """多个日期失败 → 全部出现在 skipped_dates."""
        from ditto_backtest.steps import StepResult

        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = [_make_slice(d) for d in DAYS]

        pipeline = Mock()
        planner = Mock()
        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        fee_model = Mock()

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        # 让所有 step 失败
        mock_step = Mock()
        mock_step.execute.return_value = StepResult.fail("always fail")
        loop._steps = (mock_step,)

        result = loop.run()

        assert result.skipped_dates == tuple(DAYS)


# ---------------------------------------------------------------------------
# T11: Cooperative cancellation via should_stop callback
# ---------------------------------------------------------------------------


class TestCooperativeCancellation:
    """should_stop 回调实现协作式取消."""

    def test_should_stop_halts_iteration(self) -> None:
        """should_stop() 返回 True → EngineLoop 提前终止迭代."""
        call_count = 0

        def _should_stop() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        wired = _make_wired_engine_loop(should_stop=_should_stop)
        result = wired.loop.run()

        assert result.cancelled is True
        # 第 1 天正常执行，第 2 天 should_stop 返回 True → 跳过
        # _build_step_context 不再调用 data_feed.get_slice()（直接从 TimeSlice 构建）
        assert wired.data_feed.get_slice.call_count == 0

    def test_final_day_checkpoint_is_published_only_after_terminal_flush(self) -> None:
        """A crash before tail flush leaves the prior resumable boundary durable."""
        checkpoints: list[BacktestCheckpoint] = []
        wired = _make_wired_engine_loop(
            on_checkpoint=checkpoints.append,
            execution_delay=1,
        )

        def _crash_before_flush() -> None:
            raise RuntimeError("crash-before-terminal-flush")

        wired.loop._flush_delayed_signals = _crash_before_flush  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="crash-before-terminal-flush"):
            wired.loop.run()

        assert [item.completed_trade_date for item in checkpoints] == DAYS[:-1]
        assert checkpoints[-1].resume_from == DAYS[-1]

    def test_terminal_checkpoint_is_not_published_before_artifact_commit(self) -> None:
        """A terminal engine snapshot is not itself a recoverable commit."""
        checkpoints: list[BacktestCheckpoint] = []
        wired = _make_wired_engine_loop(
            on_checkpoint=checkpoints.append,
            execution_delay=1,
        )

        result = wired.loop.run()

        assert [item.completed_trade_date for item in checkpoints] == DAYS[:-1]
        assert result.last_checkpoint is not None
        assert result.last_checkpoint.completed_trade_date == DAYS[-1]
        assert result.last_checkpoint.can_resume is False

    def test_cancelled_result_carries_resume_checkpoint(self) -> None:
        """取消前最后完成日应产生可恢复 checkpoint，resume_from 指向下一交易日。"""
        call_count = 0
        checkpoints: list[object] = []

        def _should_stop() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        wired = _make_wired_engine_loop(
            should_stop=_should_stop,
            on_checkpoint=checkpoints.append,
        )
        result = wired.loop.run()

        assert result.cancelled is True
        assert result.last_checkpoint is not None
        assert result.last_checkpoint.completed_trade_date == "2026-03-01"
        assert result.last_checkpoint.resume_from == "2026-03-02"
        assert result.last_checkpoint.can_resume is True
        assert checkpoints == [result.last_checkpoint]

    def test_checkpoint_carries_account_state_snapshot(self) -> None:
        """checkpoint 应携带恢复所需的账户现金与持仓状态快照。"""
        call_count = 0

        def _should_stop() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        wired = _make_wired_engine_loop(should_stop=_should_stop)
        account_view = _make_account_view_with_position()
        wired.brokerage.get_account.return_value = account_view

        result = wired.loop.run()

        assert result.last_checkpoint is not None
        account_state = result.last_checkpoint.account_state
        assert account_state is not None
        assert account_state.cash_available == 700_000.0
        assert account_state.cash_settled == 680_000.0
        assert account_state.cash_frozen == 20_000.0
        assert account_state.nav == 733_000.0
        assert account_state.positions[0].instrument_id == InstrumentId(2)
        assert account_state.positions[0].quantity == 300
        assert account_state.state_hash.startswith("sha256:")

    def test_checkpoint_carries_settlement_state_snapshot(self) -> None:
        """checkpoint 应携带未来解冻队列，支持后续 state restore。"""
        call_count = 0

        def _should_stop() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        settlement_state = BacktestSettlementStateSnapshot(
            frozen_quantities=(
                BacktestFrozenQuantitySnapshot(
                    instrument_id=InstrumentId(1),
                    settle_date="2026-03-03",
                    quantity=1000,
                ),
            ),
        )
        wired = _make_wired_engine_loop(should_stop=_should_stop)
        wired.brokerage.get_settlement_state_snapshot.return_value = settlement_state

        result = wired.loop.run()

        assert result.last_checkpoint is not None
        assert result.last_checkpoint.settlement_state == settlement_state
        assert (
            result.last_checkpoint.settlement_state_hash == settlement_state.state_hash
        )

    def test_checkpoint_carries_runtime_state_snapshot(self) -> None:
        """checkpoint 应携带 pending orders 与 delayed signal queue 证据。"""
        call_count = 0

        def _should_stop() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        pending_order = _make_order(qty=300)
        pending_ticket = OrderTicket(
            order=pending_order,
            status=OrderStatus.SUBMITTED,
        )
        order_book = Mock()
        order_book.get_pending.return_value = (pending_ticket,)

        wired = _make_wired_engine_loop(
            should_stop=_should_stop,
            execution_delay=2,
        )
        wired.brokerage.get_order_book.return_value = order_book

        result = wired.loop.run()

        assert result.last_checkpoint is not None
        runtime_state = result.last_checkpoint.runtime_state
        assert isinstance(runtime_state, BacktestRuntimeStateSnapshot)
        assert runtime_state.pending_orders[0].client_order_id == "order-001"
        assert runtime_state.pending_orders[0].leaves_quantity == 300
        # Cooperative pause/cancel is a resumable boundary, not terminal
        # completion: queued signals must enter the checkpoint unchanged.
        assert len(runtime_state.delayed_signals) == 1
        assert runtime_state.delayed_signals[0].trade_date == "2026-03-01"
        wired.brokerage.place_order.assert_not_called()
        assert runtime_state.state_hash.startswith("sha256:")

    def test_should_stop_never_triggered(self) -> None:
        """should_stop() 始终返回 False → 正常执行全部天数."""
        wired = _make_wired_engine_loop(should_stop=lambda: False)
        result = wired.loop.run()

        assert result.cancelled is False
        # _build_step_context 不再调用 data_feed.get_slice()
        assert wired.data_feed.get_slice.call_count == 0

    def test_should_stop_none_runs_fully(self) -> None:
        """should_stop=None → 正常执行全部天数."""
        wired = _make_wired_engine_loop(should_stop=None)
        result = wired.loop.run()

        assert result.cancelled is False
        # _build_step_context 不再调用 data_feed.get_slice()
        assert wired.data_feed.get_slice.call_count == 0


# ---------------------------------------------------------------------------
# T12: execution_delay 延迟执行
# ---------------------------------------------------------------------------


class TestExecutionDelay:
    """execution_delay 信号延迟执行测试."""

    def _make_delay_loop(
        self,
        execution_delay: int = 1,
        targets: list[TargetPortfolio] | None = None,
        on_checkpoint: Callable[[object], None] | None = None,
        restore_runtime_state: BacktestRuntimeStateSnapshot | None = None,
    ) -> tuple[EngineLoop, Mock, Mock, Mock]:
        """构建 execution_delay 测试用的 EngineLoop + 关键 mock。"""
        config = replace(
            _make_config(),
            execution_delay=execution_delay,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = _make_slice

        pipeline = Mock()
        if targets is not None:
            pipeline.run.side_effect = targets
        else:
            pipeline.run.return_value = _make_target()

        order = _make_order()
        planner = Mock()
        if restore_runtime_state is not None:
            planner.snapshot_id_counter = Mock(return_value=0)
            planner.restore_id_counter = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(order,),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        if restore_runtime_state is not None:
            brokerage.snapshot_fill_counter = Mock(return_value=0)
            brokerage.restore_fill_counter = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
        )
        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(
                fee_model=fee_model,
                on_checkpoint=on_checkpoint,
                restore_runtime_state=restore_runtime_state,
            ),
        )
        return loop, pipeline, planner, brokerage

    def test_delay_0_same_as_no_delay(self) -> None:
        """execution_delay=0: 行为与不设置完全一致（3 天 3 次执行）."""
        wired = _make_wired_engine_loop()
        result = wired.loop.run()

        assert result.period == ("2026-03-01", "2026-03-03")
        assert wired.pipeline.run.call_count == 3
        assert wired.brokerage.place_order.call_count == 3

    def test_delay_1_first_day_no_execution(self) -> None:
        """execution_delay=1: 首日信号入队延迟，尾部 flush → 3 天 3 次执行。"""
        loop, pipeline, _planner, brokerage = self._make_delay_loop(
            execution_delay=1,
        )
        loop.run()

        # pipeline 每天都生成信号 (3 天 3 次)
        assert pipeline.run.call_count == 3
        # 首日信号入队，Day 1 执行；Day 1 信号 Day 2 执行；Day 2 信号 flush → 3 次
        assert brokerage.place_order.call_count == 3

    def test_delay_1_signal_executed_next_day(self) -> None:
        """execution_delay=1: Day 0 的信号在 Day 1 执行（planner 收到延迟信号）。"""
        targets = [_make_target(d) for d in DAYS]
        loop, _pipeline, planner, _brokerage = self._make_delay_loop(
            execution_delay=1,
            targets=targets,
        )
        loop.run()

        # Day 1 执行 Day 0 信号, Day 2 执行 Day 1 信号, flush 执行 Day 2 信号 → 3 次
        assert planner.plan.call_count == 3
        # 验证 planner 第一次调用收到的是 Day 0 的 target
        first_call_target = planner.plan.call_args_list[0][1]["target"]
        assert first_call_target is targets[0]

    def test_restore_runtime_state_rehydrates_delayed_signal_queue(self) -> None:
        """Resume restores queues, locks, ID counters, and open trade state."""
        restore_state = BacktestRuntimeStateSnapshot(
            delayed_signals=(
                BacktestDelayedSignalSnapshot(
                    queue_index=0,
                    trade_date="2026-02-27",
                    strategy_id="default",
                    run_id="parent-run",
                    cash_target=0.25,
                    positions=(
                        BacktestTargetWeightSnapshot(
                            instrument_id=InstrumentId(2),
                            target_weight=0.75,
                        ),
                    ),
                ),
            ),
            strategy_context=(
                BacktestStrategyContextSnapshot.from_strategy_snapshot(
                    StrategyContextSnapshot(
                        risk_locked_instruments={
                            InstrumentId(2): ("cooldown", "2026-03-10"),
                        },
                        positions={InstrumentId(2): 8.5},
                    )
                )
            ),
            planner_id_counter=9,
            brokerage_fill_counter=4,
            trade_builder_state=TradeBuilderStateSnapshot(
                method=TradeMatchingMethod.FIFO,
                counter=3,
                fifo_open_entries=(
                    FifoOpenEntrySnapshot(
                        trade_id="trade-3",
                        instrument_id=InstrumentId(2),
                        direction=OrderSide.BUY,
                        entry_date=date(2026, 2, 27),
                        entry_price=8.5,
                        entry_fee=5.0,
                        original_quantity=100,
                        remaining_quantity=100,
                        entry_order_id="plan-order-8",
                    ),
                ),
            ),
        )
        loop, _pipeline, planner, brokerage = self._make_delay_loop(
            execution_delay=1,
            restore_runtime_state=restore_state,
        )
        planner.snapshot_id_counter.return_value = 9
        brokerage.snapshot_fill_counter.return_value = 4

        result = loop.run()

        planner.restore_id_counter.assert_called_once_with(9)
        brokerage.restore_fill_counter.assert_called_once_with(4)
        first_call_target = planner.plan.call_args_list[0][1]["target"]
        assert first_call_target.trade_date == "2026-02-27"
        assert first_call_target.positions == {InstrumentId(2): 0.75}
        assert first_call_target.cash_target == 0.25
        assert planner.plan.call_args_list[0][1]["locked_instruments"] == {
            InstrumentId(2)
        }
        assert result.last_checkpoint is not None
        assert result.last_checkpoint.runtime_state is not None
        assert (
            result.last_checkpoint.runtime_state.trade_builder_state
            == restore_state.trade_builder_state
        )

    def test_delay_1_trailing_signal_flushed(self) -> None:
        """execution_delay=1: 回测结束后尾部信号被 flush 执行。"""
        loop, pipeline, planner, brokerage = self._make_delay_loop(
            execution_delay=1,
        )
        loop.run()

        # 3 天每天生成信号，尾部 flush 确保 Day 2 信号被执行
        assert pipeline.run.call_count == 3
        assert brokerage.place_order.call_count == 3
        assert planner.plan.call_count == 3

    def test_final_checkpoint_includes_trailing_flush_orders(self) -> None:
        """最终 checkpoint 应反映 tail flush 追加后的订单数量。"""
        checkpoints: list[BacktestCheckpoint] = []
        loop, _pipeline, _planner, _brokerage = self._make_delay_loop(
            execution_delay=1,
            on_checkpoint=checkpoints.append,
        )

        result = loop.run()

        assert result.last_checkpoint is not None
        assert result.last_checkpoint.resume_from is None
        assert result.last_checkpoint.order_count == len(result.orders)
        assert checkpoints[-1].can_resume is True
        assert checkpoints[-1].completed_trade_date == DAYS[-2]

    def test_final_day_failure_cannot_republish_mutated_prior_checkpoint(self) -> None:
        """Only a successful daily boundary may replace the durable checkpoint."""
        from ditto_backtest.steps import StepResult

        checkpoints: list[BacktestCheckpoint] = []
        loop, _pipeline, _planner, _brokerage = self._make_delay_loop(
            execution_delay=1,
            on_checkpoint=checkpoints.append,
        )
        audit_step = Mock()
        audit_step.execute.side_effect = (
            StepResult.ok(),
            StepResult.ok(),
            StepResult.fail("final audit failure"),
            StepResult.ok(),
        )
        loop._steps = (*loop._steps[:-1], audit_step)

        result = loop.run()

        assert result.skipped_dates == (DAYS[-1],)
        assert len(checkpoints) == 2
        durable = checkpoints[-1]
        assert durable.completed_trade_date == DAYS[-2]
        assert durable.resume_from == DAYS[-1]
        assert durable.runtime_state is not None
        assert [item.trade_date for item in durable.runtime_state.delayed_signals] == [
            DAYS[0]
        ]
        assert result.last_checkpoint == durable

    def test_delay_1_no_skipped_dates(self) -> None:
        """execution_delay=1: PlanningStep 被跳过而非 fail，无 skipped_dates."""
        loop, _pipeline, _planner, _brokerage = self._make_delay_loop(
            execution_delay=1,
        )
        result = loop.run()

        assert result.skipped_dates == ()

    def test_delay_1_flush_runs_audit_step(self) -> None:
        """execution_delay=1: flush 阶段应执行 AuditStep，记录审计数据."""
        from ditto_backtest.audit.collector import ExecutionAuditCollector
        from ditto_backtest.audit.state import ExecutionAuditStateSnapshot

        audit_collector = Mock(spec=ExecutionAuditCollector)
        audit_collector.snapshot_state.return_value = ExecutionAuditStateSnapshot()
        config = replace(
            _make_config(),
            execution_delay=1,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = _make_slice

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        order = _make_order()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(order,),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
        )
        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(
                fee_model=fee_model,
                audit_collector=audit_collector,
            ),
        )
        loop.run()

        # 3 normal days + 1 flush = 4 record_account_view calls
        call_dates = [
            call[0][0] for call in audit_collector.record_account_view.call_args_list
        ]
        assert len(call_dates) == 4
        assert call_dates[-1] == DAYS[-1]

    def test_flush_propagates_unexpected_error(self) -> None:
        """flush 延迟信号时，get_slice 异常应向上传播而非被静默吞掉."""
        targets = [_make_target()]
        loop, _pipeline, _planner, _brokerage = self._make_delay_loop(
            execution_delay=1,
            targets=targets,
        )
        loop._data_feed.get_slice = Mock(
            side_effect=RuntimeError("unexpected DB error")
        )

        with pytest.raises(RuntimeError, match="unexpected DB error"):
            loop._execute_delayed_signal(_make_target())

    def test_flush_uses_configured_knowledge_lag_days(self) -> None:
        """flush 阶段的 knowledge_date 使用 config.knowledge_lag_days."""
        from datetime import timedelta

        from ditto_backtest.steps import StepResult

        config = replace(
            _make_config(),
            execution_delay=1,
            knowledge_lag_days=3,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = _make_slice

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        order = _make_order()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(order,),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
        )
        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        # Capture StepContext from flush step execution
        captured_ctxs: list[object] = []

        def _capturing_execute(ctx: object) -> StepResult:
            captured_ctxs.append(ctx)
            return StepResult.ok()

        mock_step = Mock()
        mock_step.execute = _capturing_execute
        loop._steps = (mock_step,)

        loop._execute_delayed_signal(_make_target())

        # flush 应产生至少一个 StepContext
        assert len(captured_ctxs) >= 1
        ctx = captured_ctxs[0]
        tc = ctx.time_context  # type: ignore[attr-defined]

        # _make_slice 的 step_time = datetime(2026, 3, 1, 15, 0)
        # knowledge_lag_days=3 → knowledge_date = 2026-02-26
        expected_knowledge = tc.decision_time.date() - timedelta(days=3)
        assert tc.knowledge_date == expected_knowledge

    def test_flush_carries_order_book(self) -> None:
        """flush 阶段的 StepContext 应携带 order_book."""
        from ditto_backtest.steps import StepResult

        config = replace(
            _make_config(),
            execution_delay=1,
        )
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = _make_slice

        planner = Mock()
        plan = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )
        planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.process_pending.return_value = ()
        mock_order_book = Mock()
        brokerage.get_order_book.return_value = mock_order_book

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
        )
        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        clock = _make_clock()
        loop = EngineLoop(
            config=config,
            pipeline=Mock(),
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            synchronizer=_make_synchronizer(data_feed, config, clock),
            options=EngineOptions(fee_model=fee_model),
        )

        captured_ctxs: list[object] = []

        def _capturing_execute(ctx: object) -> StepResult:
            captured_ctxs.append(ctx)
            return StepResult.ok()

        mock_step = Mock()
        mock_step.execute = _capturing_execute
        loop._steps = (mock_step,)

        loop._execute_delayed_signal(_make_target())

        assert len(captured_ctxs) >= 1
        ctx = captured_ctxs[0]
        assert ctx.order_book is mock_order_book  # type: ignore[attr-defined]

    def test_flush_uses_last_timeslice_bars_not_second_slice_read(self) -> None:
        """尾部 flush 不得从第二次 get_slice 读取污染 bar."""
        config = replace(
            _make_config(),
            start_date="2026-03-01",
            end_date="2026-03-01",
            execution_delay=1,
        )
        iid = InstrumentId(1)
        frozen_bar = _make_snapshot(iid=1, close=10.0)
        polluted_bar = _make_snapshot(iid=1, close=99.0)

        data_feed = Mock()
        data_feed.trading_days.return_value = ["2026-03-01"]
        data_feed.get_slice.return_value = Slice(
            trade_date="2026-03-01",
            step_time=datetime(2026, 3, 1, 15, 0),
            bars={iid: polluted_bar},
            benchmark_close=9999.0,
        )

        pipeline = Mock()
        pipeline.run.return_value = _make_target()

        planner = Mock()
        planner.plan.return_value = Mock(
            plan_id="plan-001",
            trade_date="2026-03-01",
            orders=(),
            estimated_turnover=0.0,
            estimated_cost=0.0,
            blocked_orders=(),
        )

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view()
        brokerage.get_order_book.return_value = Mock()
        brokerage.process_pending.return_value = ()

        tc = TimeContext(
            decision_time=datetime(2026, 3, 1, 15, 0),
            knowledge_date=datetime(2026, 2, 28).date(),
            trade_date="2026-03-01",
        )
        sync = Mock(spec=Synchronizer)
        sync.clock.return_value = _make_clock()
        sync.stream.return_value = iter(
            [
                TimeSlice(
                    time_context=tc,
                    bars={iid: frozen_bar},
                    benchmark_close=3000.0,
                ),
            ],
        )

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=Mock(),
            data_feed=data_feed,
            synchronizer=sync,
            options=EngineOptions(fee_model=Mock()),
        )

        loop.run()

        flush_input = brokerage.process_pending.call_args_list[-1].args[0]
        assert flush_input.bars[iid].close == 10.0
