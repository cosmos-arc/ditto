"""EngineLoop unit tests — 7 scenarios with mock objects + boundary tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import MappingProxyType
from unittest.mock import Mock

import pytest
from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.cash import CashBook
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import (
    Order,
    OrderBookReadOnly,
    OrderSide,
    OrderType,
)
from ditto_engine.backtest.data_feed import MarketSnapshot, Slice
from ditto_engine.backtest.engine import EngineConfig, EngineLoop, EngineOptions
from ditto_engine.backtest.risk.pre_trade import (
    Decision,
    OrderCheckResult,
)
from ditto_engine.strategy.models import TargetPortfolio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


DAYS = ["2026-03-01", "2026-03-02", "2026-03-03"]


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
        order_id="order-001",
        instrument_id=iid,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=qty,
    )


def _make_fill(fill_id: str = "fill-001") -> FillEvent:
    return FillEvent(
        fill_id=fill_id,
        order_id="order-001",
        instrument_id=1,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=5.0,
        slippage=0.001,
        event_time=datetime(2026, 3, 1, 15, 0),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _make_config() -> EngineConfig:
    return EngineConfig(
        start_date="2026-03-01",
        end_date="2026-03-03",
        initial_cash=1_000_000.0,
        strategy_id="default",
        strategy_run_id="run-001",
    )


def _make_engine_loop(
    config: EngineConfig | None = None,
    pipeline: Mock | None = None,
    planner: Mock | None = None,
    brokerage: Mock | None = None,
    pre_trade_check: Mock | None = None,
    data_feed: Mock | None = None,
    fee_model: Mock | None = None,
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

    return EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=data_feed,
        options=EngineOptions(fee_model=fee_model),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThreeDayStep:
    """Scenario 1: 3-day backtest with pipeline + planner + brokerage."""

    def test_three_day_step(self) -> None:
        """3 trading days → pipeline called 3 times, result has correct period."""
        config = _make_config()
        data_feed = Mock()
        data_feed.trading_days.return_value = DAYS
        data_feed.get_slice.side_effect = [_make_slice(d) for d in DAYS]

        pipeline = Mock()
        target = _make_target()
        pipeline.run.return_value = target

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

        account_view = _make_account_view()
        brokerage = Mock()
        brokerage.get_account.return_value = account_view
        brokerage.place_order.return_value = Mock()
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="order-001",
        )

        fee_model = Mock()
        fee_model.estimate.return_value = 5.0

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=EngineOptions(fee_model=fee_model),
        )
        result = loop.run()

        assert result.period == ("2026-03-01", "2026-03-03")
        assert result.run_id == "run-001"
        assert pipeline.run.call_count == 3
        assert brokerage.place_order.call_count == 3


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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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
        from ditto_engine.execution.brokerage import ProcessInput

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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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
        from ditto_engine.execution.rules import InstrumentRuleProvider

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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=EngineOptions(fee_model=fee_model, rule_provider=rule_provider),
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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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

        loop = EngineLoop(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
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

    def test_weekly_monday_true(self) -> None:
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        # 2026-03-02 is Monday; prev trading day 2026-03-01 is Sunday (ISO week 9 vs 9)
        # 但 2026-03-01 isocalendar() week 9, 2026-03-02 isocalendar() week 10
        assert loop._is_rebalance_day("2026-03-02") is True

    def test_weekly_tuesday_false(self) -> None:
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        # 2026-03-03 is Tuesday; prev trading day 2026-03-02 is Monday (same ISO week)
        assert loop._is_rebalance_day("2026-03-03") is False

    def test_weekly_first_trading_day_of_week(self) -> None:
        """当周无周一交易日（如节假日），第一个交易日仍为 rebalance day。"""
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        # 2026-03-01 is Sunday (ISO week 9), 2026-03-04 is Wednesday (ISO week 10)
        loop._trading_days = ("2026-03-01", "2026-03-04")
        assert loop._is_rebalance_day("2026-03-04") is True

    def test_weekly_invalid_date_raises(self) -> None:
        """date 不在 trading_days 中 → weekly 模式下 .index() 抛出 ValueError."""
        config = replace(_make_config(), rebalance_freq="weekly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        with pytest.raises(ValueError):
            loop._is_rebalance_day("not-a-date")

    def test_monthly_first_day_of_month(self) -> None:
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        # First trading day in list → idx=0 → True
        assert loop._is_rebalance_day("2026-03-01") is True

    def test_monthly_same_month_false(self) -> None:
        """同一月内非首日 → False."""
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        # "2026-03-02" same month as "2026-03-01" (idx 0) → False
        assert loop._is_rebalance_day("2026-03-02") is False

    def test_monthly_different_month_true(self) -> None:
        """跨月 → True."""
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = ("2026-03-31", "2026-04-01")
        # "2026-04-01" has month_prefix "2026-04", prev "2026-03" different → True
        assert loop._is_rebalance_day("2026-04-01") is True

    def test_monthly_date_not_in_trading_days_raises(self) -> None:
        """date 不在 trading_days 中 → .index() 抛出 ValueError."""
        config = replace(_make_config(), rebalance_freq="monthly")
        loop = _make_engine_loop(config=config)
        loop._trading_days = tuple(DAYS)
        with pytest.raises(ValueError):
            loop._is_rebalance_day("2026-06-01")

    def test_unknown_freq_defaults_true(self) -> None:
        """未知 rebalance_freq → 默认返回 True."""
        config = replace(_make_config(), rebalance_freq="quarterly")
        loop = _make_engine_loop(config=config)
        assert loop._is_rebalance_day("2026-03-01") is True
