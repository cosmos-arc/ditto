"""
Phase 0.1-0.5 单元测试 — TradingStep Protocol + StepResult + StepContext + Steps.

RED -> GREEN: 验证 TradingStep 协议、StepResult、StepContext 和所有 Step 实现。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import MagicMock, Mock

import pytest
from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.cash import CashBook
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import Order, OrderBookReadOnly, OrderType
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.backtest.audit import ExecutionAuditCollector
from ditto_engine.backtest.data_feed import MarketSnapshot, Slice
from ditto_engine.backtest.steps import (
    AuditStep,
    DataFetchStep,
    ExecutionStep,
    PlanningStep,
    PreTradeStep,
    RiskScanStep,
    StepContext,
    StepResult,
    StrategyStep,
    TradingStep,
)
from ditto_engine.execution.planner import ExecutionPlan
from ditto_engine.risk.post_trade import (
    RiskAction,
    RiskActionType,
    RiskScope,
    RiskSeverity,
)
from ditto_kernel.clock import Clock
from ditto_kernel.enums import OrderSide
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


IID_1: InstrumentId = 1
IID_2: InstrumentId = 2


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


def _make_slice(
    date: str = "2026-03-01",
    bars: dict[int, MarketSnapshot] | None = None,
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
    """构建测试用 RiskAction。"""
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
    """构建测试用 FillEvent。"""
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
    """构建测试用 Order。"""
    return Order(
        order_id=order_id,
        instrument_id=instrument_id,
        order_type=OrderType.MARKET,
        direction=direction,
        quantity=quantity,
    )


def _make_execution_plan(orders: tuple[Order, ...] | None = None) -> ExecutionPlan:
    """构建测试用 ExecutionPlan。"""
    return ExecutionPlan(
        plan_id="plan-1",
        trade_date="2026-03-01",
        orders=orders or (_make_order(),),
        estimated_turnover=10_000.0,
        estimated_cost=5.0,
        blocked_orders=(),
    )


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------


class TestStepResult:
    """StepResult 数据类测试。"""

    def test_ok_factory(self) -> None:
        result = StepResult.ok()
        assert result.success is True
        assert result.errors == ()
        assert result.audit_data == {}

    def test_skipped_factory(self) -> None:
        result = StepResult.skipped()
        assert result.success is True
        assert result.errors == ()
        assert result.audit_data == {}

    def test_fail_factory(self) -> None:
        result = StepResult.fail("err1", "err2")
        assert result.success is False
        assert result.errors == ("err1", "err2")
        assert result.audit_data == {}

    def test_with_audit_data(self) -> None:
        result = StepResult(success=True, audit_data={"key": "value"})
        assert result.audit_data == {"key": "value"}

    def test_frozen(self) -> None:
        result = StepResult.ok()
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StepContext
# ---------------------------------------------------------------------------


class TestStepContext:
    """StepContext 可变共享状态测试。"""

    def test_basic_fields(self) -> None:
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        assert ctx.date == "2025-01-15"
        assert ctx.is_rebalance_day is True

    def test_default_none_fields(self) -> None:
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        assert ctx.slice_ is None
        assert ctx.account_view is None
        assert ctx.target_portfolio is None
        assert ctx.execution_plan is None
        assert ctx.rules is None

    def test_default_list_fields_empty(self) -> None:
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        assert ctx.step_orders == []
        assert ctx.step_fills == []
        assert ctx.pre_trade_decisions == []

    def test_mutable_step_outputs(self) -> None:
        """StepContext 是可变的 -- Steps 会写入结果字段。"""
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        ctx.slice_ = "fake_slice"  # type: ignore[assignment]
        assert ctx.slice_ == "fake_slice"

    def test_mutable_step_orders(self) -> None:
        """step_orders 可以被 Steps 追加。"""
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        ctx.step_orders.append("order1")  # type: ignore[arg-type]
        assert len(ctx.step_orders) == 1


# ---------------------------------------------------------------------------
# TradingStep Protocol
# ---------------------------------------------------------------------------


class TestTradingStepProtocol:
    """验证 TradingStep 可以被正确实现。"""

    def test_concrete_step_satisfies_protocol(self) -> None:
        """自定义 Step 实现 TradingStep Protocol。"""

        class FakeStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.ok()

        step: TradingStep = FakeStep()  # type: ignore[assignment]
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        result = step.execute(ctx)
        assert result.success is True

    def test_step_returns_skipped(self) -> None:
        """Step 可以返回 skipped 结果。"""

        class SkipStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.skipped()

        step: TradingStep = SkipStep()  # type: ignore[assignment]
        ctx = StepContext(date="2025-01-15", is_rebalance_day=False)
        result = step.execute(ctx)
        assert result.success is True

    def test_step_returns_failure(self) -> None:
        """Step 可以返回失败结果。"""

        class FailStep:
            def execute(self, ctx: StepContext) -> StepResult:
                return StepResult.fail("something went wrong")

        step: TradingStep = FailStep()  # type: ignore[assignment]
        ctx = StepContext(date="2025-01-15", is_rebalance_day=True)
        result = step.execute(ctx)
        assert result.success is False
        assert "something went wrong" in result.errors


# ---------------------------------------------------------------------------
# DataFetchStep (Phase 0.2)
# ---------------------------------------------------------------------------


class TestDataFetchStep:
    """DataFetchStep: 获取 Slice + 账户快照 + 清除锁定。"""

    def test_sets_slice_and_account_view(self) -> None:
        """执行后 ctx.slice_ 和 ctx.account_view 被正确设置。"""
        slice_ = _make_slice(bars={IID_1: _make_snapshot(IID_1)})
        account_view = _make_account_view()
        clock = _make_clock()

        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=clock,
            brokerage=Mock(get_account=Mock(return_value=account_view)),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.slice_ is slice_
        assert ctx.account_view is account_view

    def test_advances_clock(self) -> None:
        """执行后 clock.advance_to 被调用。"""
        step_time = datetime(2026, 3, 1, 15, 0)
        slice_ = Slice(
            trade_date="2026-03-01",
            step_time=step_time,
            bars={IID_1: _make_snapshot(IID_1)},
        )
        clock = _make_clock()

        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=clock,
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        clock.advance_to.assert_called_once_with(step_time)

    def test_collects_input_instruments(self) -> None:
        """slice_.bars 的所有 instrument_id 被收集到 input_instruments。"""
        bars = {
            IID_1: _make_snapshot(IID_1),
            IID_2: _make_snapshot(IID_2),
        }
        slice_ = _make_slice(bars=bars)
        input_instruments: set[InstrumentId] = set()

        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=input_instruments,
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        assert IID_1 in input_instruments
        assert IID_2 in input_instruments

    def test_clears_strategy_context_locks(self) -> None:
        """执行后 strategy_context 的到期锁被清除。"""
        strategy_context = StrategyContext()
        # cooldown_until = "2026-02-28"（已过期），date = "2026-03-01"
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-02-28")

        slice_ = _make_slice()
        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=strategy_context,
            input_instruments=set(),
            bar_fingerprints={},
        )

        # 锁在 2026-02-28 到期，2026-03-01 清除
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        # cooldown_until < date -> 锁被清除
        assert not strategy_context.is_locked(IID_1)

    def test_preserves_active_strategy_context_locks(self) -> None:
        """未到期锁在 clear_locks 后仍然保留。"""
        strategy_context = StrategyContext()
        # cooldown_until = "2026-03-05"（未过期）
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-03-05")

        slice_ = _make_slice()
        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=strategy_context,
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        # cooldown_until > date -> 锁保留
        assert strategy_context.is_locked(IID_1)

    def test_satisfies_trading_step_protocol(self) -> None:
        """DataFetchStep 满足 TradingStep Protocol。"""
        step: TradingStep = DataFetchStep(  # type: ignore[assignment]
            data_feed=Mock(get_slice=Mock(return_value=_make_slice())),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        result = step.execute(ctx)
        assert result.success is True


# ---------------------------------------------------------------------------
# RiskScanStep (Phase 0.3)
# ---------------------------------------------------------------------------


class TestRiskScanStep:
    """RiskScanStep: PostTrade 风控扫描 + 锁管理。"""

    def _make_ctx_with_data(self) -> StepContext:
        """构建包含 slice_ 和 account_view 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        return ctx

    def test_skips_when_no_post_trade_guard(self) -> None:
        """post_trade_guard 为 None 时跳过风控扫描。"""
        step = RiskScanStep(
            post_trade_guard=None,
            audit_collector=None,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True

    def test_scans_and_locks_instruments(self) -> None:
        """REDUCE_POSITION + INSTRUMENT scope -> 锁定标的。"""
        action = _make_risk_action(
            action_type=RiskActionType.REDUCE_POSITION,
            instrument_id=IID_1,
            scope=RiskScope.INSTRUMENT,
            cooldown_until_date="2026-03-05",
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)

        assert result.success is True
        assert strategy_context.is_locked(IID_1)

    def test_liquidate_locks_instrument(self) -> None:
        """LIQUIDATE + INSTRUMENT scope -> 锁定标的。"""
        action = _make_risk_action(
            action_type=RiskActionType.LIQUIDATE,
            instrument_id=IID_1,
            scope=RiskScope.INSTRUMENT,
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        assert strategy_context.is_locked(IID_1)

    def test_alert_does_not_lock_instrument(self) -> None:
        """ALERT action 不锁定标的（action_type 不在锁定范围）。"""
        action = _make_risk_action(
            action_type=RiskActionType.ALERT,
            instrument_id=IID_1,
            scope=RiskScope.INSTRUMENT,
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        assert not strategy_context.is_locked(IID_1)

    def test_portfolio_scope_does_not_lock(self) -> None:
        """PORTFOLIO scope 不锁定（只有 INSTRUMENT scope 才锁定）。"""
        action = _make_risk_action(
            action_type=RiskActionType.REDUCE_POSITION,
            instrument_id=None,
            scope=RiskScope.PORTFOLIO,
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        # PORTFOLIO scope -> 不锁定任何标的
        assert len(strategy_context.get_locked_instruments()) == 0

    def test_records_risk_scan_audit(self) -> None:
        """有 audit_collector 时记录风控扫描审计。"""
        action = _make_risk_action()
        guard = Mock(scan=Mock(return_value=[action]))
        collector = Mock(spec=ExecutionAuditCollector)

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=collector,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        collector.record_risk_scan.assert_called_once()
        call_args = collector.record_risk_scan.call_args
        assert call_args[0][0] == "2026-03-01"  # date

    def test_publishes_risk_guard_triggered_event(self) -> None:
        """有 event_bus 时发布 RiskGuardTriggered 事件。"""
        action = _make_risk_action()
        guard = Mock(scan=Mock(return_value=[action]))
        event_bus = Mock()

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=event_bus,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]
        assert event.rule_name == "single_loss_limit"

    def test_no_audit_when_no_risk_actions(self) -> None:
        """guard 扫描无结果时不记录审计。"""
        guard = Mock(scan=Mock(return_value=[]))
        collector = Mock(spec=ExecutionAuditCollector)

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=collector,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        collector.record_risk_scan.assert_not_called()

    def test_satisfies_trading_step_protocol(self) -> None:
        """RiskScanStep 满足 TradingStep Protocol。"""
        step: TradingStep = RiskScanStep(  # type: ignore[assignment]
            post_trade_guard=None,
            audit_collector=None,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True


# ---------------------------------------------------------------------------
# StrategyStep (Phase 0.4)
# ---------------------------------------------------------------------------


class TestStrategyStep:
    """StrategyStep: 运行策略 Pipeline -> TargetPortfolio。"""

    def _make_ctx_with_data(self) -> StepContext:
        """构建包含 slice_ 和 account_view 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        return ctx

    def test_skips_when_not_rebalance_day(self) -> None:
        """非调仓日跳过策略运行。"""
        step = StrategyStep(
            pipeline=Mock(),
            strategy_context=StrategyContext(),
            strategy_id="test-strategy",
            strategy_run_id="run-1",
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=False)
        ctx.slice_ = _make_slice()
        result = step.execute(ctx)

        assert result.success is True

    def test_runs_pipeline_on_rebalance_day(self) -> None:
        """调仓日运行 pipeline 并设置 ctx.target_portfolio。"""
        target = Mock(name="target_portfolio")
        pipeline = Mock(run=Mock(return_value=target))

        step = StrategyStep(
            pipeline=pipeline,
            strategy_context=StrategyContext(),
            strategy_id="test-strategy",
            strategy_run_id="run-1",
        )

        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.target_portfolio is target
        pipeline.run.assert_called_once()

    def test_builds_input_bundle_from_slice(self) -> None:
        """从 slice_.bars 构建 StrategyInputBundle 传给 pipeline。"""
        target = Mock(name="target_portfolio")
        pipeline = Mock(run=Mock(return_value=target))

        step = StrategyStep(
            pipeline=pipeline,
            strategy_context=StrategyContext(),
            strategy_id="test-strategy",
            strategy_run_id="run-1",
        )

        bars = {IID_1: _make_snapshot(IID_1, close=10.0)}
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice(bars=bars)
        ctx.account_view = _make_account_view()

        step.execute(ctx)

        # 验证 pipeline.run 收到的 input_bundle 含正确的 trade_date
        call_args = pipeline.run.call_args
        input_bundle = call_args[0][1]  # 第二个位置参数
        assert input_bundle.trade_date == "2026-03-01"
        assert input_bundle.strategy_id == "test-strategy"
        assert input_bundle.run_id == "run-1"

    def test_satisfies_trading_step_protocol(self) -> None:
        """StrategyStep 满足 TradingStep Protocol。"""
        step: TradingStep = StrategyStep(  # type: ignore[assignment]
            pipeline=Mock(run=Mock(return_value=Mock())),
            strategy_context=StrategyContext(),
            strategy_id="test",
            strategy_run_id="run-1",
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True


# ---------------------------------------------------------------------------
# PlanningStep (Phase 0.4)
# ---------------------------------------------------------------------------


class TestPlanningStep:
    """PlanningStep: 获取规则 + 调用 planner.plan()。"""

    def _make_ctx_with_target(self) -> StepContext:
        """构建包含 slice_, account_view, target_portfolio 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        ctx.target_portfolio = Mock(name="target_portfolio")
        return ctx

    def test_skips_when_not_rebalance_day(self) -> None:
        """非调仓日跳过计划生成。"""
        step = PlanningStep(
            planner=Mock(),
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=False)
        result = step.execute(ctx)

        assert result.success is True

    def test_plans_on_rebalance_day(self) -> None:
        """调仓日调用 planner.plan 并设置 ctx.execution_plan。"""
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))

        step = PlanningStep(
            planner=planner,
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )

        ctx = self._make_ctx_with_target()
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.execution_plan is plan

    def test_fetches_rules_from_provider(self) -> None:
        """有 rule_provider 时获取规则并传给 planner。"""
        rules = {IID_1: Mock(name="rules")}
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))
        rule_provider = Mock(get_rules=Mock(return_value=rules))

        step = PlanningStep(
            planner=planner,
            rule_provider=rule_provider,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )

        ctx = self._make_ctx_with_target()
        step.execute(ctx)

        # 验证 rule_provider.get_rules 被调用
        rule_provider.get_rules.assert_called_once()
        # 验证 planner.plan 收到 rules
        planner.plan.assert_called_once()
        call_kwargs = planner.plan.call_args
        assert call_kwargs[1]["rules"] is rules or call_kwargs[0][3] is rules

    def test_observes_rules_in_collector(self) -> None:
        """有 rule_ref_collector 时观察规则引用。"""
        rules = {IID_1: Mock(name="rules")}
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))
        rule_provider = Mock(get_rules=Mock(return_value=rules))
        collector = Mock()

        step = PlanningStep(
            planner=planner,
            rule_provider=rule_provider,
            rule_ref_collector=collector,
            strategy_context=StrategyContext(),
        )

        ctx = self._make_ctx_with_target()
        step.execute(ctx)

        collector.observe.assert_called_once()

    def test_passes_locked_instruments_to_planner(self) -> None:
        """strategy_context 中被锁定的标的传给 planner。"""
        plan = _make_execution_plan()
        planner = Mock(plan=Mock(return_value=plan))
        strategy_context = StrategyContext()
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-03-05")

        step = PlanningStep(
            planner=planner,
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=strategy_context,
        )

        ctx = self._make_ctx_with_target()
        step.execute(ctx)

        planner.plan.assert_called_once()
        call_kwargs = planner.plan.call_args
        locked = (
            call_kwargs[1].get("locked_instruments")
            if call_kwargs[1]
            else call_kwargs[0][4]
            if len(call_kwargs[0]) > 4
            else None
        )
        assert locked is not None
        assert IID_1 in locked

    def test_satisfies_trading_step_protocol(self) -> None:
        """PlanningStep 满足 TradingStep Protocol。"""
        step: TradingStep = PlanningStep(  # type: ignore[assignment]
            planner=Mock(plan=Mock(return_value=_make_execution_plan())),
            rule_provider=None,
            rule_ref_collector=None,
            strategy_context=StrategyContext(),
        )
        ctx = self._make_ctx_with_target()
        result = step.execute(ctx)
        assert result.success is True


# ---------------------------------------------------------------------------
# PreTradeStep (Phase 0.5)
# ---------------------------------------------------------------------------


class TestPreTradeStep:
    """PreTradeStep: PreTrade 校验 + 订单提交。"""

    def _make_ctx_with_plan(self) -> StepContext:
        """构建包含 execution_plan 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
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

        ctx = StepContext(date="2026-03-01", is_rebalance_day=False)
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

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.execution_plan = None
        result = step.execute(ctx)

        assert result.success is True

    def test_checks_orders_and_places_accepted(self) -> None:
        """校验通过 -> 提交订单 + 追加到 step_orders。"""
        from ditto_engine.risk.pre_trade import Decision

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
        from ditto_engine.risk.pre_trade import Decision

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
        from ditto_engine.risk.pre_trade import Decision

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
        from ditto_engine.risk.pre_trade import Decision

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
        from ditto_engine.risk.pre_trade import Decision

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
        from ditto_engine.risk.pre_trade import Decision

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


# ---------------------------------------------------------------------------
# ExecutionStep (Phase 0.5)
# ---------------------------------------------------------------------------


class TestExecutionStep:
    """ExecutionStep: 处理成交 (process_pending)。"""

    def _make_ctx_with_data(self) -> StepContext:
        """构建包含 slice_ 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        return ctx

    def test_processes_pending_fills(self) -> None:
        """执行后 fills 被追加到 ctx.step_fills。"""
        fill = _make_fill()
        brokerage = Mock(
            process_pending=Mock(return_value=(fill,)),
        )

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)

        assert result.success is True
        assert fill in ctx.step_fills

    def test_builds_process_input_from_slice(self) -> None:
        """从 slice_ 构建 ProcessInput 传给 brokerage。"""
        brokerage = Mock(process_pending=Mock(return_value=()))

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=None,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        brokerage.process_pending.assert_called_once()
        process_input = brokerage.process_pending.call_args[0][0]
        assert process_input.trade_date == "2026-03-01"

    def test_publishes_order_filled_events(self) -> None:
        """有 event_bus 时为每个 fill 发布 OrderFilled 事件。"""
        fill_1 = _make_fill(order_id="ord-1")
        fill_2 = _make_fill(order_id="ord-2")
        event_bus = Mock()
        brokerage = Mock(
            process_pending=Mock(return_value=(fill_1, fill_2)),
        )

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=event_bus,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        # 每个 fill 发布一个事件
        assert event_bus.publish.call_count == 2

    def test_no_fills_no_events(self) -> None:
        """无成交时不发布事件。"""
        event_bus = Mock()
        brokerage = Mock(process_pending=Mock(return_value=()))

        step = ExecutionStep(
            brokerage=brokerage,
            event_bus=event_bus,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        event_bus.publish.assert_not_called()
        assert len(ctx.step_fills) == 0

    def test_satisfies_trading_step_protocol(self) -> None:
        """ExecutionStep 满足 TradingStep Protocol。"""
        step: TradingStep = ExecutionStep(  # type: ignore[assignment]
            brokerage=Mock(process_pending=Mock(return_value=())),
            event_bus=None,
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True


# ---------------------------------------------------------------------------
# AuditStep (Phase 0.5)
# ---------------------------------------------------------------------------


class TestAuditStep:
    """AuditStep: 记录账户快照 + 成交 + 平仓交易审计。"""

    def _make_ctx_with_fills(self) -> StepContext:
        """构建包含 slice_, fills 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        fill = _make_fill()
        ctx.step_fills.append(fill)
        return ctx

    def test_records_account_view(self) -> None:
        """记录每日账户快照到 audit_collector。"""
        account_view = _make_account_view()
        brokerage = Mock(get_account=Mock(return_value=account_view))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        result = step.execute(ctx)

        assert result.success is True
        collector.record_account_view.assert_called_once_with(
            "2026-03-01",
            account_view,
        )

    def test_records_fills(self) -> None:
        """记录每个 fill 到 audit_collector。"""
        fill = _make_fill()
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        collector.record_fill.assert_called_once_with(fill)

    def test_records_closed_trades(self) -> None:
        """通过 trade_builder 匹配成交 -> 记录已平仓交易。"""
        trade = Mock(trade_id="trade-1")
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[trade]),
        )
        recorded_ids: set[str] = set()

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=recorded_ids,
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        collector.record_closed_trade.assert_called_once_with(trade)
        assert "trade-1" in recorded_ids

    def test_deduplicates_closed_trades(self) -> None:
        """已记录的 trade_id 不重复记录。"""
        trade = Mock(trade_id="trade-1")
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[trade]),
        )
        recorded_ids: set[str] = {"trade-1"}  # 已存在

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=recorded_ids,
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        # 已记录的不重复
        collector.record_closed_trade.assert_not_called()

    def test_passes_fills_to_trade_builder(self) -> None:
        """每个 fill 传给 trade_builder.on_fill。"""
        fill = _make_fill()
        account_view = _make_account_view()
        brokerage = Mock(get_account=Mock(return_value=account_view))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        trade_builder.on_fill.assert_called_once_with(fill, account_view)

    def test_skips_when_no_audit_collector(self) -> None:
        """audit_collector 为 None 时跳过审计。"""
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=None,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        result = step.execute(ctx)

        assert result.success is True

    def test_satisfies_trading_step_protocol(self) -> None:
        """AuditStep 满足 TradingStep Protocol。"""
        step: TradingStep = AuditStep(  # type: ignore[assignment]
            audit_collector=None,
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            trade_builder=Mock(
                on_fill=Mock(),
                get_closed_trades=Mock(return_value=[]),
            ),
            recorded_trade_ids=set(),
        )
        ctx = self._make_ctx_with_fills()
        result = step.execute(ctx)
        assert result.success is True
