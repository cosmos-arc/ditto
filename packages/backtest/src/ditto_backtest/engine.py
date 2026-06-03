"""
EngineLoop -- 回测引擎主循环.

V1 每日循环 (通过 TradingStep chain 编排):
  1. DataFetchStep: 账户快照 + 数据指纹 + 清除锁定
  2. RiskScanStep: PostTrade 风控扫描 + 锁管理
  3. StrategyStep: 策略 Pipeline -> TargetPortfolio (仅调仓日)
  4. PlanningStep: ExecutionPlanner -> ExecutionPlan (仅调仓日)
  5. PreTradeStep: PreTrade 校验 + 订单提交 (仅调仓日)
  6. ExecutionStep: 订单成交处理
  7. AuditStep: 审计记录 (账户快照 + 成交 + 已平仓交易)

Synchronizer 驱动主循环 — EngineLoop 不知道自己的模式（回测/实盘）。
EngineOptions / assemble_engine_result 已拆至 engine_steps.py。
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import cast

from ditto_execution.brokerage import Brokerage
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.planner import ExecutionPlanner
from ditto_execution.targets import TargetPortfolioLike
from ditto_execution.trade_builder import (
    FifoTradeBuilder,
    FlatToFlatTradeBuilder,
    TradeBuilder,
    TradeMatchingMethod,
)
from ditto_kernel import traced
from ditto_kernel.identity import InstrumentId
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
from ditto_kernel.time_context import TimeContext
from ditto_portfolio.accounting import AccountView, FillEvent
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from loguru import logger

from ditto_backtest.config import EngineConfig, EngineMode
from ditto_backtest.data_feed import DataFeed, Slice
from ditto_backtest.engine_steps import (
    EngineOptions,
    StepDeps,
    assemble_engine_result,
    build_steps,
    is_rebalance_day,
)
from ditto_backtest.manifest import (
    RuleRefCollector,
    build_run_manifest,
)
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestCheckpoint,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
    EngineResult,
)
from ditto_backtest.steps import (
    DataFetchStep,
    PlanningStep,
    RiskScanStep,
    StepContext,
    StrategyStep,
    TradingStep,
)
from ditto_backtest.steps.input_bundle import build_input_bundle

__all__ = [
    "EngineConfig",
    "EngineLoop",
    "EngineMode",
    "EngineOptions",
    "EngineResult",
    "assemble_engine_result",
]


# ---------------------------------------------------------------------------
# EngineLoop
# ---------------------------------------------------------------------------


class EngineLoop:
    """
    回测引擎主循环 -- 通过 TradingStep chain 编排每日执行流程.

    实现 TradingLoop Protocol（结构化子类型）。

    Step Chain:
      DataFetchStep -> RiskScanStep -> StrategyStep -> PlanningStep
      -> PreTradeStep -> ExecutionStep -> AuditStep

    Parameters
    ----------
        config: 引擎配置
        pipeline: 策略 Pipeline
        planner: 执行计划器
        brokerage: 经纪商 (构造时传入 rules_getter)
        pre_trade_check: 组合 PreTrade 校验
        data_feed: 市场数据源（保留：用于 get_slice 获取 benchmark_close 等）
        synchronizer: 时间同步器（Synchronizer 驱动主循环）
        options: 可选组件 (费率模型、规则提供者、风控、审计、事件总线)

    """

    def __init__(
        self,
        config: EngineConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: DataFeed,
        synchronizer: Synchronizer,
        options: EngineOptions,
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._planner = planner
        self._brokerage = brokerage
        self._pre_trade_check = pre_trade_check
        self._data_feed = data_feed
        self._synchronizer = synchronizer
        self._init_options(options)
        self._init_state(config)
        self._trade_builder = self._create_trade_builder(config)
        self._recorded_trade_ids: set[str] = set()
        self._steps = self._build_steps()

    # -- R1: __init__ helpers --------------------------------------------------

    @staticmethod
    def _create_trade_builder(config: EngineConfig) -> TradeBuilder:
        """根据 config.trade_matching 创建成交匹配器。"""
        if config.trade_matching == TradeMatchingMethod.FLAT_TO_FLAT:
            return FlatToFlatTradeBuilder()
        return FifoTradeBuilder()

    def _init_options(self, options: EngineOptions) -> None:
        """从 EngineOptions 初始化可选组件引用。"""
        self._fee_model = options.fee_model
        self._rule_provider = options.rule_provider
        self._post_trade_guard = options.post_trade_guard
        self._audit_collector = options.audit_collector
        self._event_bus = options.event_bus
        self._input_bundle_builder = options.input_bundle_builder
        self._random_seed = options.random_seed
        self._should_stop = options.should_stop
        self._on_progress = options.on_progress
        self._on_checkpoint = options.on_checkpoint
        self._restore_runtime_state = options.restore_runtime_state
        self._on_step_complete = options.on_step_complete

    def _init_state(self, config: EngineConfig) -> None:
        """初始化跨日可变状态。"""
        self._fills: list[FillEvent] = []
        self._orders: list[Order] = []
        self._strategy_context = StrategyContext()
        self._execution_delay = config.execution_delay
        self._knowledge_lag_days = config.knowledge_lag_days
        self._signal_queue: deque[TargetPortfolioLike] = deque()
        self._restore_delayed_signals()
        self._last_time_slice: TimeSlice | None = None
        self._rule_ref_collector = RuleRefCollector()
        self._trading_days: tuple[str, ...] = ()
        self._trading_day_index: dict[str, int] = {}
        self._input_instruments: set[InstrumentId] = set()
        self._bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]] = {}
        self._source_snapshot_ids: dict[InstrumentId, set[str]] = {}
        self._last_checkpoint: BacktestCheckpoint | None = None

    def _restore_delayed_signals(self) -> None:
        """Restore delayed signal queue from checkpoint runtime state."""
        runtime_state = self._restore_runtime_state
        if runtime_state is None:
            return
        for signal in sorted(
            runtime_state.delayed_signals,
            key=lambda item: item.queue_index,
        ):
            self._signal_queue.append(
                TargetPortfolio(
                    trade_date=signal.trade_date,
                    strategy_id=signal.strategy_id,
                    run_id=signal.run_id,
                    positions={
                        weight.instrument_id: weight.target_weight
                        for weight in signal.positions
                    },
                    cash_target=signal.cash_target,
                )
            )

    def _build_steps(self) -> tuple[TradingStep, ...]:
        """构建 TradingStep chain — 委托给 engine_steps.build_steps。"""
        return build_steps(
            StepDeps(
                config=self._config,
                pipeline=self._pipeline,
                planner=self._planner,
                brokerage=self._brokerage,
                pre_trade_check=self._pre_trade_check,
                clock=self._synchronizer.clock(),
                fee_model=self._fee_model,
                rule_provider=self._rule_provider,
                post_trade_guard=self._post_trade_guard,
                audit_collector=self._audit_collector,
                event_bus=self._event_bus,
                input_bundle_builder=self._input_bundle_builder,
                strategy_context=self._strategy_context,
                input_instruments=self._input_instruments,
                bar_fingerprints=self._bar_fingerprints,
                source_snapshot_ids=self._source_snapshot_ids,
                rule_ref_collector=self._rule_ref_collector,
                trade_builder=self._trade_builder,
                recorded_trade_ids=self._recorded_trade_ids,
                build_input_bundle_fn=self._build_input_bundle,
            ),
        )

    # -- public ---------------------------------------------------------------

    @traced("engine.backtest.run")
    def run(self) -> EngineResult:
        """
        执行完整回测.

        通过 Synchronizer 驱动主循环，逐日执行策略决策和订单处理.
        """
        run_id = self._config.strategy_run_id or uuid.uuid4().hex[:8]
        trading_days = self._build_trading_days()
        start = trading_days[0] if trading_days else self._config.start_date
        end = trading_days[-1] if trading_days else self._config.end_date

        skipped, cancelled = self._run_main_loop(run_id, trading_days)
        self._flush_delayed_signals()

        account_view = self._brokerage.get_account()
        self._refresh_final_checkpoint(account_view)
        self._flush_open_trades()

        manifest = build_run_manifest(
            run_id=run_id,
            config=self._config,
            input_instruments=self._input_instruments,
            bar_fingerprints=self._bar_fingerprints,
            source_snapshot_ids=self._source_snapshot_ids,
            rule_refs=self._rule_ref_collector.rule_refs,
            random_seed=self._random_seed,
        )
        return assemble_engine_result(
            run_id=run_id,
            start=start,
            end=end,
            account_view=account_view,
            manifest=manifest,
            fills=self._fills,
            orders=self._orders,
            skipped=skipped,
            cancelled=cancelled,
            last_checkpoint=self._last_checkpoint,
        )

    # -- R2: run helpers ------------------------------------------------------

    def _build_trading_days(self) -> list[str]:
        """构建 trading_days 索引 — 用于 is_rebalance_day() 计算。"""
        days = self._data_feed.trading_days()
        trading_days = [d for d in days if d >= self._config.start_date]
        self._trading_days = tuple(trading_days)
        self._trading_day_index = {d: i for i, d in enumerate(self._trading_days)}
        return trading_days

    def _run_main_loop(
        self,
        run_id: str,
        trading_days: list[str],
    ) -> tuple[list[str], bool]:
        """执行主循环 — 返回 (skipped_dates, cancelled)。"""
        skipped: list[str] = []
        cancelled = False
        completed_days = 0
        total_days = len(trading_days)

        for time_slice in self._synchronizer.stream():
            self._synchronizer.clock().advance_to(
                time_slice.time_context.decision_time,
            )
            if self._should_stop is not None and self._should_stop():
                cancelled = True
                break
            trade_date = time_slice.time_context.trade_date
            self._last_time_slice = time_slice
            if not self._step(time_slice):
                skipped.append(trade_date)
            else:
                completed_days += 1
                self._record_checkpoint(
                    run_id=run_id,
                    trade_date=trade_date,
                    completed_days=completed_days,
                    total_days=total_days,
                )
                if self._on_progress is not None:
                    self._on_progress(completed_days, total_days)

        if skipped:
            logger.warning(
                "StepChain skipped {} date(s): {}",
                len(skipped),
                skipped,
            )
        return skipped, cancelled

    def _record_checkpoint(
        self,
        *,
        run_id: str,
        trade_date: str,
        completed_days: int,
        total_days: int,
    ) -> None:
        """记录最后成功交易日的恢复 checkpoint。"""
        idx = self._trading_day_index.get(trade_date)
        resume_from = None
        if idx is not None and idx + 1 < len(self._trading_days):
            resume_from = self._trading_days[idx + 1]

        account_view = self._brokerage.get_account()
        checkpoint = BacktestCheckpoint(
            run_id=run_id,
            strategy_id=self._config.strategy_id,
            completed_trade_date=trade_date,
            resume_from=resume_from,
            completed_days=completed_days,
            total_days=total_days,
            nav=account_view.nav,
            fill_count=len(self._fills),
            order_count=len(self._orders),
            account_state=BacktestAccountStateSnapshot.from_account_view(account_view),
            settlement_state=self._settlement_state_snapshot(),
            runtime_state=self._runtime_state_snapshot(),
        )
        self._last_checkpoint = checkpoint
        if self._on_checkpoint is not None:
            self._on_checkpoint(checkpoint)

    def _refresh_final_checkpoint(self, account_view: AccountView) -> None:
        """
        尾部 flush 后刷新最终 checkpoint 的账户与执行统计。

        无论 checkpoint 是否携带 resume_from 边界，都需要在
        execution_delay 尾部 flush 后刷新 NAV/fill/order/account-state，
        否则 resume 后的 checkpoint 将反映 flush 前的陈旧状态。
        """
        checkpoint = self._last_checkpoint
        if checkpoint is None:
            return

        refreshed = replace(
            checkpoint,
            nav=account_view.nav,
            fill_count=len(self._fills),
            order_count=len(self._orders),
            account_state=BacktestAccountStateSnapshot.from_account_view(account_view),
            settlement_state=self._settlement_state_snapshot(),
            runtime_state=self._runtime_state_snapshot(),
        )
        if refreshed == checkpoint:
            return

        self._last_checkpoint = refreshed
        if self._on_checkpoint is not None:
            self._on_checkpoint(refreshed)

    def _flush_delayed_signals(self) -> None:
        """Flush 延迟信号 — 回测结束时执行队列中剩余的延迟信号。"""
        while self._execution_delay > 0 and self._signal_queue:
            signal = self._signal_queue.popleft()
            self._execute_delayed_signal(signal)

    def _flush_open_trades(self) -> None:
        """Flush 未平仓交易 — 回测结束时记录剩余开仓交易。"""
        if self._audit_collector is not None:
            for trade in self._trade_builder.flush():
                if trade.trade_id not in self._recorded_trade_ids:
                    self._audit_collector.record_closed_trade(trade)
                    self._recorded_trade_ids.add(trade.trade_id)

    def _settlement_state_snapshot(self) -> BacktestSettlementStateSnapshot | None:
        """Read optional settlement/frozen queue state from backtest brokerage."""
        method_obj = getattr(self._brokerage, "get_settlement_state_snapshot", None)
        if not callable(method_obj):
            return None
        method = cast(Callable[[], object], method_obj)
        snapshot = method()
        if isinstance(snapshot, BacktestSettlementStateSnapshot):
            return snapshot
        return None

    def _runtime_state_snapshot(self) -> BacktestRuntimeStateSnapshot:
        """Capture pending OMS tickets and delayed engine signals."""
        return BacktestRuntimeStateSnapshot.from_state(
            pending_tickets=self._pending_order_tickets(),
            delayed_signals=tuple(self._signal_queue),
        )

    def _pending_order_tickets(self) -> tuple[OrderTicket, ...]:
        """Read pending order tickets when the brokerage exposes a real order book."""
        order_book_method = getattr(self._brokerage, "get_order_book", None)
        if not callable(order_book_method):
            return ()
        order_book = order_book_method()
        get_pending = getattr(order_book, "get_pending", None)
        if not callable(get_pending):
            return ()
        pending_obj = get_pending()
        if not isinstance(pending_obj, tuple):
            return ()
        pending_tuple = cast(tuple[object, ...], pending_obj)
        pending_tickets: list[OrderTicket] = []
        for ticket in pending_tuple:
            if not isinstance(ticket, OrderTicket):
                return ()
            pending_tickets.append(ticket)
        return tuple(pending_tickets)

    # -- internals ------------------------------------------------------------

    def _build_input_bundle(self, date: str, slice_: Slice) -> StrategyInputBundle:
        """
        构建 StrategyInputBundle -- 子类可覆盖以注入自定义列.

        默认实现委托给 build_input_bundle() 共享函数。
        """
        return build_input_bundle(
            trade_date=date,
            strategy_id=self._config.strategy_id,
            run_id=self._config.strategy_run_id,
            bars=slice_.bars,
            benchmark_close=slice_.benchmark_close,
        )

    def _dequeue_delayed_signal(self) -> TargetPortfolioLike | None:
        """取出到期的延迟信号。队列中信号数 >= execution_delay 时才有信号到期。"""
        if (
            self._execution_delay > 0
            and len(self._signal_queue) >= self._execution_delay
        ):
            return self._signal_queue.popleft()
        return None

    def _execute_delayed_signal(self, signal: TargetPortfolioLike) -> None:
        """
        对延迟信号执行 Planning -> PreTrade -> Execution 子链（尾部 flush）。

        跳过 DataFetchStep / RiskScanStep / StrategyStep，
        执行 PlanningStep -> PreTradeStep -> ExecutionStep -> AuditStep。
        run() 驱动的尾部 flush 复用主循环最后一个 TimeSlice，避免重读
        DataFeed 时混入 late-arriving market inputs。
        """
        last_date = self._trading_days[-1] if self._trading_days else ""
        logger.warning(
            "Flush: delayed signal on last_date={}",
            last_date,
        )

        ctx = self._build_delayed_flush_context(last_date)
        ctx.target_portfolio = signal
        ctx.account_view = self._brokerage.get_account()
        ctx.order_book = self._brokerage.get_order_book()

        for step in self._steps:
            if isinstance(step, (DataFetchStep, RiskScanStep, StrategyStep)):
                continue
            if isinstance(step, PlanningStep):
                ctx.target_portfolio = signal
                ctx.is_rebalance_day = True
            result = step.execute(ctx)
            if not result.success:
                step_name = type(step).__name__
                logger.warning("Flush step {} failed", step_name)
                return

        self._fills.extend(ctx.step_fills)
        self._orders.extend(ctx.step_orders)

    def _build_delayed_flush_context(self, last_date: str) -> StepContext:
        """构造尾部 flush 上下文，优先复用最后一个 TimeSlice 的 PIT 输入。"""
        time_slice = self._last_time_slice
        if time_slice is not None:
            tc = time_slice.time_context
            slice_ = Slice(
                trade_date=tc.trade_date,
                step_time=tc.decision_time,
                bars=time_slice.bars,
                benchmark_close=time_slice.benchmark_close,
                source_snapshot_ids=time_slice.source_snapshot_ids,
            )
            return StepContext(
                time_context=tc,
                is_rebalance_day=True,
                bars=time_slice.bars,
                source_snapshot_ids=time_slice.source_snapshot_ids,
                slice_=slice_,
            )

        try:
            slice_ = self._data_feed.get_slice(last_date)
        except Exception:
            logger.exception("Flush: unexpected error getting slice for {}", last_date)
            raise

        tc = TimeContext(
            decision_time=slice_.step_time,
            knowledge_date=(
                slice_.step_time.date() - timedelta(days=self._knowledge_lag_days)
            ),
            trade_date=slice_.trade_date,
        )
        return StepContext(
            time_context=tc,
            is_rebalance_day=True,
            bars=slice_.bars,
            source_snapshot_ids=slice_.source_snapshot_ids,
            slice_=slice_,
        )

    def _step(self, time_slice: TimeSlice) -> bool:
        """执行单日步骤 -- 通过 Step chain 编排。返回 False 表示某 step 失败。"""
        trade_date = time_slice.time_context.trade_date
        ctx = self._build_step_context(time_slice)
        delay = self._execution_delay
        deferred_signal = self._dequeue_delayed_signal()

        # 执行 Step chain
        for step in self._steps:
            if self._process_delayed_signal(step, ctx, delay, deferred_signal):
                continue
            t0 = time.monotonic()
            result = step.execute(ctx)
            elapsed = time.monotonic() - t0
            if not result.success:
                self._log_step_failure(step, result, trade_date)
                if self._on_step_complete is not None:
                    self._on_step_complete(type(step).__name__, elapsed, False)
                return False
            if self._on_step_complete is not None:
                self._on_step_complete(type(step).__name__, elapsed, True)
            self._enqueue_signal(step, ctx, delay)

        # 累积跨日结果
        self._fills.extend(ctx.step_fills)
        self._orders.extend(ctx.step_orders)
        self._record_audit(trade_date, ctx)
        return True

    # -- R3: _step helpers ----------------------------------------------------

    def _build_step_context(self, time_slice: TimeSlice) -> StepContext:
        """
        构建当日 StepContext。

        Synchronizer 产出的 TimeSlice 是每步唯一 PIT 可见行情输入源。
        直接从 TimeSlice 构建 Slice，避免冗余的 DataFeed.get_slice() 调用。
        """
        trade_date = time_slice.time_context.trade_date
        is_rebalance = self._is_rebalance_day(trade_date)
        slice_ = Slice(
            trade_date=trade_date,
            step_time=time_slice.time_context.decision_time,
            bars=time_slice.bars,
            benchmark_close=time_slice.benchmark_close,
            source_snapshot_ids=time_slice.source_snapshot_ids,
        )
        return StepContext(
            time_context=time_slice.time_context,
            is_rebalance_day=is_rebalance,
            bars=time_slice.bars,
            source_snapshot_ids=time_slice.source_snapshot_ids,
            slice_=slice_,
        )

    @staticmethod
    def _log_step_failure(step: TradingStep, result: object, trade_date: str) -> None:
        """记录 step 失败日志。"""
        step_name = type(step).__name__
        errors = getattr(result, "errors", None)
        msg = "; ".join(errors) if errors else "unknown"
        logger.warning("Step {} failed on {}: {}", step_name, trade_date, msg)

    def _enqueue_signal(
        self,
        step: TradingStep,
        ctx: StepContext,
        delay: int,
    ) -> None:
        """execution_delay: StrategyStep 后将当日信号入队并清除。"""
        if delay > 0 and isinstance(step, StrategyStep):
            if ctx.target_portfolio is not None:
                self._signal_queue.append(ctx.target_portfolio)
            ctx.target_portfolio = None

    def _process_delayed_signal(
        self,
        step: TradingStep,
        ctx: StepContext,
        delay: int,
        deferred_signal: TargetPortfolioLike | None,
    ) -> bool:
        """处理延迟信号逻辑 — 返回 True 表示应跳过当前 step。"""
        if delay <= 0 or not isinstance(step, PlanningStep):
            return False
        # 无延迟信号时跳过 PlanningStep（信号已入队，等待 N 日后执行）
        if deferred_signal is None:
            return True
        # PlanningStep 前恢复延迟信号
        ctx.target_portfolio = deferred_signal
        ctx.is_rebalance_day = True
        return False

    def _record_audit(self, trade_date: str, ctx: StepContext) -> None:
        """审计日志: 批量记录 PreTrade 决策。"""
        if self._audit_collector is not None and ctx.pre_trade_decisions:
            self._audit_collector.record_pre_trade_decisions(
                trade_date,
                tuple(ctx.pre_trade_decisions),
            )

    def _is_rebalance_day(self, date: str) -> bool:
        """根据配置判断是否为调仓日 — 委托给 engine_steps.is_rebalance_day。"""
        return is_rebalance_day(
            date,
            self._config.rebalance_freq,
            self._trading_days,
            self._trading_day_index,
        )
