"""
TradingStep Protocol + StepResult + StepContext + Steps -- 回测引擎步骤化定义.

Phase 0.1-0.5: 定义回测引擎拆分所需的核心协议、数据结构和所有 Step 实现。

- TradingStep Protocol: 每个步骤必须实现的接口
- StepResult: 步骤执行结果（成功/失败/审计数据）
- StepContext: 单日步骤链的共享可变状态
- DataFetchStep: 数据获取 + 账户快照 + 清除锁定
- RiskScanStep: PostTrade 风控扫描 + 锁管理
- StrategyStep: 策略 Pipeline -> TargetPortfolio
- PlanningStep: 规则获取 + ExecutionPlanner -> ExecutionPlan
- PreTradeStep: PreTrade 校验 + 订单提交
- ExecutionStep: 成交处理 (process_pending)
- AuditStep: 审计记录 (account_view + fills + closed_trades)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

import polars as pl
from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_kernel.identity import InstrumentId

from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.buying_power import CashAccountBuyingPower
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import Order
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.backtest.audit.collector import ExecutionAuditCollector
from ditto_engine.backtest.audit.records import PreTradeDecisionRecord, RiskScanRecord
from ditto_engine.backtest.data_feed import DataFeed, Slice
from ditto_engine.backtest.manifest import RuleRefCollector
from ditto_engine.events import OrderFilled, OrderSubmitted, RiskGuardTriggered
from ditto_engine.execution.brokerage import Brokerage, ProcessInput
from ditto_engine.execution.planner import ExecutionPlan, ExecutionPlanner
from ditto_engine.execution.reality import FeeModel
from ditto_engine.execution.rules import InstrumentRuleProvider, InstrumentRules
from ditto_engine.execution.targets import TargetPortfolioLike
from ditto_engine.execution.trade_builder import TradeBuilder
from ditto_engine.risk.post_trade import (
    PostTradeRiskGuard,
    RiskActionType,
    RiskScope,
)
from ditto_engine.risk.pre_trade import (
    CompositePreTradeCheck,
    Decision,
    OrderCheckResult,
    PreTradeContext,
)

__all__ = [
    "AuditStep",
    "DataFetchStep",
    "ExecutionStep",
    "PlanningStep",
    "PreTradeStep",
    "RiskScanStep",
    "StepContext",
    "StepResult",
    "StrategyStep",
    "TradingStep",
]


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepResult:
    """
    单个 TradingStep 的执行结果.

    Attributes:
        success: 是否执行成功
        errors: 错误信息列表（成功时为空）
        audit_data: 审计数据（步骤特定）

    """

    success: bool
    errors: tuple[str, ...] = ()
    audit_data: dict[str, object] = field(default_factory=dict)

    @classmethod
    def ok(cls) -> StepResult:
        """成功结果。"""
        return cls(success=True)

    @classmethod
    def skipped(cls) -> StepResult:
        """跳过结果（也算成功）。"""
        return cls(success=True)

    @classmethod
    def fail(cls, *errors: str) -> StepResult:
        """失败结果。"""
        return cls(success=False, errors=errors)


# ---------------------------------------------------------------------------
# StepContext
# ---------------------------------------------------------------------------


@dataclass
class StepContext:
    """
    单日步骤链的共享可变状态.

    由 EngineLoop 在每日迭代开始时创建，传递给所有 TradingStep。
    Steps 通过读写此对象共享数据。

    Attributes:
        date: 当前交易日 (YYYY-MM-DD)
        is_rebalance_day: 是否为调仓日
        slice_: 当日市场数据切片（由 DataFetchStep 设置）
        account_view: 账户快照（由 DataFetchStep 设置）
        target_portfolio: 目标组合（由 StrategyStep 设置，仅调仓日）
        execution_plan: 执行计划（由 PlanningStep 设置，仅调仓日）
        rules: 三层规则（由 PlanningStep 设置，仅调仓日）
        step_orders: 当日已提交订单（由 PreTradeStep 追加）
        step_fills: 当日成交事件（由 ExecutionStep 追加）
        pre_trade_decisions: PreTrade 决策记录（由 PreTradeStep 追加）

    """

    # -- Day info (set by EngineLoop) --
    date: str
    is_rebalance_day: bool

    # -- Step outputs (set by steps, read by subsequent steps) --
    slice_: Slice | None = None
    account_view: AccountView | None = None
    target_portfolio: TargetPortfolioLike | None = None
    execution_plan: ExecutionPlan | None = None
    rules: dict[InstrumentId, InstrumentRules] | None = None

    # -- Daily accumulators (appended by steps) --
    step_orders: list[Order] = field(default_factory=list)
    step_fills: list[FillEvent] = field(default_factory=list)
    pre_trade_decisions: list[PreTradeDecisionRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TradingStep Protocol
# ---------------------------------------------------------------------------


class TradingStep(Protocol):
    """
    回测引擎步骤接口.

    每个步骤实现此接口，接收 StepContext，返回 StepResult。
    EngineLoop 按顺序调用所有步骤的 execute 方法。
    """

    def execute(self, ctx: StepContext) -> StepResult:
        """执行步骤，返回结果。"""
        ...


# ---------------------------------------------------------------------------
# DataFetchStep (Phase 0.2)
# ---------------------------------------------------------------------------


class DataFetchStep:
    """
    数据获取步骤 -- 从 DataFeed 获取 Slice + 账户快照 + 清除到期锁定.

    对应 EngineLoop._step() 的前半部分:
      1. data_feed.get_slice(date) -> Slice
      2. clock.advance_to(slice.step_time)
      3. brokerage.get_account() -> AccountView
      4. input_instruments.update(slice.bars.keys())
      5. strategy_context.clear_locks(date)
      6. bar_fingerprints 累积 (date, close) 用于数据指纹

    执行后 ctx.slice_ 和 ctx.account_view 被设置。
    """

    def __init__(
        self,
        data_feed: DataFeed,
        clock: Clock,
        brokerage: Brokerage,
        strategy_context: StrategyContext,
        input_instruments: set[InstrumentId],
        bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]],
    ) -> None:
        self._data_feed = data_feed
        self._clock = clock
        self._brokerage = brokerage
        self._strategy_context = strategy_context
        self._input_instruments = input_instruments
        self._bar_fingerprints = bar_fingerprints

    def execute(self, ctx: StepContext) -> StepResult:
        """获取当日数据并设置到 StepContext。"""
        slice_ = self._data_feed.get_slice(ctx.date)
        self._clock.advance_to(slice_.step_time)
        account_view = self._brokerage.get_account()

        # 收集输入标的 -- 用于 RunManifest input_refs
        self._input_instruments.update(slice_.bars.keys())

        # 累积 bar 数据指纹 -- (date, close) per instrument
        for iid, bar in slice_.bars.items():
            if iid not in self._bar_fingerprints:
                self._bar_fingerprints[iid] = []
            self._bar_fingerprints[iid].append((ctx.date, bar.close))

        # 每日清除到期锁定 -- cooldown 未到期的锁定保留
        self._strategy_context.clear_locks(ctx.date)

        # 写入 context 供后续步骤使用
        ctx.slice_ = slice_
        ctx.account_view = account_view

        return StepResult.ok()


# ---------------------------------------------------------------------------
# RiskScanStep (Phase 0.3)
# ---------------------------------------------------------------------------


class RiskScanStep:
    """
    PostTrade 风控扫描步骤 -- 扫描风险 + 锁定标的 + 发布事件.

    对应 EngineLoop._step() 中 PostTrade 风控部分:
      1. post_trade_guard.scan(account_view, slice_) -> RiskAction[]
      2. 记录风控审计 (audit_collector)
      3. 对 REDUCE_POSITION/LIQUIDATE + INSTRUMENT scope 锁定标的
      4. 发布 RiskGuardTriggered 事件 (event_bus)
    """

    def __init__(
        self,
        post_trade_guard: PostTradeRiskGuard | None,
        audit_collector: ExecutionAuditCollector | None,
        event_bus: EventBus | None,
        strategy_context: StrategyContext,
        clock: Clock,
    ) -> None:
        self._post_trade_guard = post_trade_guard
        self._audit_collector = audit_collector
        self._event_bus = event_bus
        self._strategy_context = strategy_context
        self._clock = clock

    def execute(self, ctx: StepContext) -> StepResult:
        """执行风控扫描。"""
        if self._post_trade_guard is None:
            return StepResult.skipped()

        if ctx.slice_ is None or ctx.account_view is None:
            return StepResult.fail("slice_ and account_view required")

        risk_actions = self._post_trade_guard.scan(ctx.account_view, ctx.slice_)

        # 审计日志: 记录风控扫描结果
        if risk_actions and self._audit_collector is not None:
            self._audit_collector.record_risk_scan(
                ctx.date,
                tuple(
                    RiskScanRecord(
                        trade_date=ctx.date,
                        rule_id=action.rule_id,
                        instrument_id=action.instrument_id,
                        scope=action.scope,
                        severity=action.severity,
                        action_taken=action.action_type,
                        detail=action.detail,
                        current_value=action.current_value,
                        threshold=action.threshold,
                    )
                    for action in risk_actions
                ),
            )

        # 锁定标的 + 发布事件
        for action in risk_actions:
            if (
                action.action_type
                in (RiskActionType.REDUCE_POSITION, RiskActionType.LIQUIDATE)
                and action.scope == RiskScope.INSTRUMENT
                and action.instrument_id is not None
            ):
                self._strategy_context.lock_instrument(
                    action.instrument_id,
                    action.detail,
                    cooldown_until=action.cooldown_until_date,
                )

            # 发布 RiskGuardTriggered 事件
            if self._event_bus is not None:
                self._event_bus.publish(
                    RiskGuardTriggered(
                        rule_name=action.rule_id,
                        severity=action.severity.value,
                        details={"instrument_id": action.instrument_id},
                        timestamp=self._clock.now(),
                    ),
                )

        return StepResult.ok()


# ---------------------------------------------------------------------------
# StrategyStep (Phase 0.4)
# ---------------------------------------------------------------------------


class StrategyStep:
    """
    策略运行步骤 -- 运行 Pipeline -> TargetPortfolio.

    对应 EngineLoop._step() 中策略部分:
      1. 从 slice_.bars 构建 StrategyInputBundle
      2. pipeline.run(strategy_context, input_bundle) -> TargetPortfolio
      3. 仅在调仓日执行，非调仓日跳过
    """

    def __init__(
        self,
        pipeline: StrategyPipeline,
        strategy_context: StrategyContext,
        strategy_id: str,
        strategy_run_id: str,
        input_bundle_builder: (
            Callable[[StepContext], StrategyInputBundle] | None
        ) = None,
    ) -> None:
        self._pipeline = pipeline
        self._strategy_context = strategy_context
        self._strategy_id = strategy_id
        self._strategy_run_id = strategy_run_id
        self._input_bundle_builder = input_bundle_builder

    def execute(self, ctx: StepContext) -> StepResult:
        """运行策略 Pipeline。"""
        if not ctx.is_rebalance_day:
            return StepResult.skipped()

        if ctx.slice_ is None:
            return StepResult.fail("slice_ required")

        # 从 slice_.bars 构建 StrategyInputBundle
        if self._input_bundle_builder is not None:
            input_bundle = self._input_bundle_builder(ctx)
        else:
            input_bundle = self._build_input_bundle(ctx)

        # 运行 Pipeline
        target = self._pipeline.run(self._strategy_context, input_bundle)

        # 设置到 context 供后续步骤使用
        ctx.target_portfolio = target

        return StepResult.ok()

    def _build_input_bundle(self, ctx: StepContext) -> StrategyInputBundle:
        """从 Slice 构建 StrategyInputBundle（默认实现）。"""
        slice_ = ctx.slice_
        if slice_ is None:  # guarded by execute() -- unreachable in practice
            msg = "slice_ required"
            raise ValueError(msg)
        bars = slice_.bars
        instrument_ids = list(bars.keys())

        instruments = pl.DataFrame(
            {"instrument_id": instrument_ids},
        )

        market_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []
        for iid, bar in bars.items():
            market_rows.append(
                {
                    "instrument_id": iid,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
            signal_rows.append(
                {
                    "instrument_id": iid,
                    "signal_value": (
                        (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                    ),
                }
            )

        return StrategyInputBundle(
            trade_date=ctx.date,
            strategy_id=self._strategy_id,
            run_id=self._strategy_run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=pl.DataFrame(signal_rows),
            benchmark_close=getattr(slice_, "benchmark_close", None),
        )


# ---------------------------------------------------------------------------
# PlanningStep (Phase 0.4)
# ---------------------------------------------------------------------------


class PlanningStep:
    """
    执行计划步骤 -- 获取规则 + 调用 planner.plan().

    对应 EngineLoop._step() 中计划部分:
      1. 通过 rule_provider 获取三层规则
      2. rule_ref_collector.observe() 收集规则引用
      3. planner.plan(target, account_view, ...) -> ExecutionPlan
      4. 仅在调仓日执行
    """

    def __init__(
        self,
        planner: ExecutionPlanner,
        rule_provider: InstrumentRuleProvider | None,
        rule_ref_collector: RuleRefCollector | None,
        strategy_context: StrategyContext,
    ) -> None:
        self._planner = planner
        self._rule_provider = rule_provider
        self._rule_ref_collector = rule_ref_collector
        self._strategy_context = strategy_context

    def execute(self, ctx: StepContext) -> StepResult:
        """生成执行计划。"""
        if not ctx.is_rebalance_day:
            return StepResult.skipped()

        if (
            ctx.slice_ is None
            or ctx.account_view is None
            or ctx.target_portfolio is None
        ):
            return StepResult.fail(
                "slice_, account_view, and target_portfolio required",
            )

        # 获取三层规则
        rules = self._fetch_rules(ctx)

        # 写入 context 供 PreTradeStep 使用
        ctx.rules = rules

        # 收集规则引用
        if self._rule_ref_collector is not None:
            self._rule_ref_collector.observe(ctx.date, rules)

        # 生成执行计划
        plan = self._planner.plan(
            target=ctx.target_portfolio,
            account_view=ctx.account_view,
            trade_date=ctx.date,
            market_snapshots=ctx.slice_.bars,
            rules=rules,
            locked_instruments=self._strategy_context.get_locked_instruments(),
        )

        ctx.execution_plan = plan

        return StepResult.ok()

    def _fetch_rules(
        self,
        ctx: StepContext,
    ) -> dict[InstrumentId, InstrumentRules] | None:
        """通过 RuleProvider 获取三层规则，无 provider 返回 None。"""
        if self._rule_provider is None:
            return None
        slice_ = ctx.slice_
        if slice_ is None:  # guarded by execute() -- unreachable in practice
            msg = "slice_ required"
            raise ValueError(msg)
        instrument_ids = list(slice_.bars.keys())
        return self._rule_provider.get_rules(ctx.date, instrument_ids)


# ---------------------------------------------------------------------------
# PreTradeStep (Phase 0.5)
# ---------------------------------------------------------------------------


class PreTradeStep:
    """
    PreTrade 校验步骤 -- 逐单检查 + 提交订单.

    对应 EngineLoop._step() 中 PreTrade 部分:
      1. 构建 PreTradeContext
      2. 逐单校验 (composite_pre_trade_check.check_order)
      3. ACCEPT/RESIZE -> 提交订单 + 发布 OrderSubmitted 事件
      4. REJECT -> 跳过
      5. F1: 滚动更新 PreTradeContext
      6. 记录 PreTrade 决策审计
      7. 仅在调仓日 + 有 execution_plan 时执行
    """

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

    def execute(self, ctx: StepContext) -> StepResult:
        """执行 PreTrade 校验循环。"""
        if not ctx.is_rebalance_day:
            return StepResult.skipped()

        if ctx.execution_plan is None:
            return StepResult.skipped()

        if ctx.slice_ is None or ctx.account_view is None:
            return StepResult.fail("slice_ and account_view required")

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
                    trade_date=ctx.date,
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
        # Narrowing: execute() guards ensure non-None
        account_view = ctx.account_view
        slice_ = ctx.slice_
        if account_view is None or slice_ is None:
            msg = "account_view and slice_ required"
            raise ValueError(msg)

        return PreTradeContext(
            account_view=account_view,
            rules=ctx.rules or {},
            market_snapshots=slice_.bars,
            fee_model=self._fee_model,
            buying_power_model=CashAccountBuyingPower(),
            pending_tickets=account_view.order_book.get_pending(),
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


# ---------------------------------------------------------------------------
# ExecutionStep (Phase 0.5)
# ---------------------------------------------------------------------------


class ExecutionStep:
    """
    成交处理步骤 -- 处理 pending 订单成交.

    对应 EngineLoop._step() 中成交处理部分:
      1. 从 slice_ 构建 ProcessInput
      2. brokerage.process_pending(process_input) -> fills
      3. 发布 OrderFilled 事件
      4. fills 追加到 ctx.step_fills
    """

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
        if ctx.slice_ is None:
            return StepResult.fail("slice_ required")

        # 构建 ProcessInput
        process_input = ProcessInput(
            step_time=ctx.slice_.step_time,
            trade_date=ctx.date,
            bars=ctx.slice_.bars,
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


# ---------------------------------------------------------------------------
# AuditStep (Phase 0.5)
# ---------------------------------------------------------------------------


class AuditStep:
    """
    审计记录步骤 -- 记录 account_view + fills + closed_trades.

    对应 EngineLoop._record_step_audit():
      1. 获取最新 account_view
      2. 记录 account_view 到 audit_collector
      3. 记录每个 fill
      4. 通过 trade_builder 匹配成交 -> 记录已平仓交易
    """

    def __init__(
        self,
        audit_collector: ExecutionAuditCollector | None,
        brokerage: Brokerage,
        trade_builder: TradeBuilder,
        recorded_trade_ids: set[str],
    ) -> None:
        self._audit_collector = audit_collector
        self._brokerage = brokerage
        self._trade_builder = trade_builder
        self._recorded_trade_ids = recorded_trade_ids

    def execute(self, ctx: StepContext) -> StepResult:
        """记录审计数据。"""
        if self._audit_collector is None:
            return StepResult.skipped()

        # 获取最新账户快照
        account_view = self._brokerage.get_account()

        # 记录账户快照
        self._audit_collector.record_account_view(ctx.date, account_view)

        # 记录每个 fill + 传给 trade_builder
        for fill in ctx.step_fills:
            self._audit_collector.record_fill(fill)
            self._trade_builder.on_fill(fill, account_view)

        # 记录已平仓交易（去重）
        for trade in self._trade_builder.get_closed_trades():
            if trade.trade_id not in self._recorded_trade_ids:
                self._audit_collector.record_closed_trade(trade)
                self._recorded_trade_ids.add(trade.trade_id)

        return StepResult.ok()
