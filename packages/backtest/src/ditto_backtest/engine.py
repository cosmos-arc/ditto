"""
EngineLoop -- 回测引擎主循环.

V1 每日循环 (通过 TradingStep chain 编排):
  1. DataFetchStep: 获取 Slice + 账户快照 + 清除锁定
  2. RiskScanStep: PostTrade 风控扫描 + 锁管理
  3. StrategyStep: 策略 Pipeline -> TargetPortfolio (仅调仓日)
  4. PlanningStep: ExecutionPlanner -> ExecutionPlan (仅调仓日)
  5. PreTradeStep: PreTrade 校验 + 订单提交 (仅调仓日)
  6. ExecutionStep: 订单成交处理
  7. AuditStep: 审计记录 (账户快照 + 成交 + 已平仓交易)

EngineOptions / assemble_engine_result 已拆至 engine_steps.py。
"""

from __future__ import annotations

import uuid
from collections import deque

from ditto_execution.brokerage import Brokerage
from ditto_execution.planner import ExecutionPlanner
from ditto_execution.targets import TargetPortfolioLike
from ditto_execution.trade_builder import (
    FifoTradeBuilder,
    FlatToFlatTradeBuilder,
    TradeMatchingMethod,
)
from ditto_kernel import traced
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import FillEvent, Order
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from loguru import logger

from ditto_backtest.config import EngineConfig, EngineMode
from ditto_backtest.data_feed import DataFeed, Slice

# Re-export from extracted module
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
from ditto_backtest.result import EngineResult
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
        data_feed: 市场数据源
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
        options: EngineOptions,
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._planner = planner
        self._brokerage = brokerage
        self._pre_trade_check = pre_trade_check
        self._data_feed = data_feed
        self._clock = options.clock
        self._fee_model = options.fee_model
        self._rule_provider = options.rule_provider
        self._post_trade_guard = options.post_trade_guard
        self._audit_collector = options.audit_collector
        self._event_bus = options.event_bus
        self._input_bundle_builder = options.input_bundle_builder
        self._random_seed = options.random_seed
        self._should_stop = options.should_stop
        self._on_progress = options.on_progress

        # 跨日可变状态
        self._fills: list[FillEvent] = []
        self._orders: list[Order] = []

        self._strategy_context = StrategyContext()
        self._execution_delay = config.execution_delay
        self._signal_queue: deque[TargetPortfolioLike] = deque()
        self._rule_ref_collector = RuleRefCollector()
        self._trading_days: tuple[str, ...] = ()
        self._trading_day_index: dict[str, int] = {}
        self._input_instruments: set[InstrumentId] = set()
        self._bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]] = {}

        # TradeBuilder -- 根据 config.trade_matching 创建成交匹配器
        if config.trade_matching == TradeMatchingMethod.FLAT_TO_FLAT:
            self._trade_builder = FlatToFlatTradeBuilder()
        else:
            self._trade_builder = FifoTradeBuilder()
        self._recorded_trade_ids: set[str] = set()

        # 构建 Step chain
        self._steps = self._build_steps()

    def _build_steps(self) -> tuple[TradingStep, ...]:
        """构建 TradingStep chain — 委托给 engine_steps.build_steps。"""
        return build_steps(
            StepDeps(
                config=self._config,
                pipeline=self._pipeline,
                planner=self._planner,
                brokerage=self._brokerage,
                pre_trade_check=self._pre_trade_check,
                data_feed=self._data_feed,
                clock=self._clock,
                fee_model=self._fee_model,
                rule_provider=self._rule_provider,
                post_trade_guard=self._post_trade_guard,
                audit_collector=self._audit_collector,
                event_bus=self._event_bus,
                input_bundle_builder=self._input_bundle_builder,
                strategy_context=self._strategy_context,
                input_instruments=self._input_instruments,
                bar_fingerprints=self._bar_fingerprints,
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

        遍历交易日历, 逐日执行策略决策和订单处理.
        """
        run_id = self._config.strategy_run_id or uuid.uuid4().hex[:8]
        days = self._data_feed.trading_days()
        # 过滤到配置区间：DataFeed 可能加载了 start_date 之前的额外数据（lookback）
        trading_days = [d for d in days if d >= self._config.start_date]
        self._trading_days = tuple(trading_days)
        self._trading_day_index = {d: i for i, d in enumerate(self._trading_days)}
        start = trading_days[0] if trading_days else self._config.start_date
        end = trading_days[-1] if trading_days else self._config.end_date

        skipped: list[str] = []
        cancelled = False
        completed_days = 0
        total_days = len(trading_days)
        for date in trading_days:
            if self._should_stop is not None and self._should_stop():
                cancelled = True
                break
            if not self._step(date):
                skipped.append(date)
            else:
                completed_days += 1
                if self._on_progress is not None:
                    self._on_progress(completed_days, total_days)

        if skipped:
            logger.warning(
                "StepChain skipped {} date(s): {}",
                len(skipped),
                skipped,
            )

        # flush 延迟信号 -- 回测结束时执行队列中剩余的延迟信号
        while self._execution_delay > 0 and self._signal_queue:
            signal = self._signal_queue.popleft()
            self._execute_delayed_signal(signal)

        account_view = self._brokerage.get_account()

        # flush 未平仓交易 -- 回测结束时记录剩余开仓交易
        if self._audit_collector is not None:
            for trade in self._trade_builder.flush():
                if trade.trade_id not in self._recorded_trade_ids:
                    self._audit_collector.record_closed_trade(trade)
                    self._recorded_trade_ids.add(trade.trade_id)

        manifest = build_run_manifest(
            run_id=run_id,
            config=self._config,
            input_instruments=self._input_instruments,
            bar_fingerprints=self._bar_fingerprints,
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
        )

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
        尾部 flush 为"最佳努力"执行，非 PIT 精确。
        """
        last_date = self._trading_days[-1] if self._trading_days else ""
        logger.warning(
            "Flush: delayed signal on last_date={} (best-effort execution)",
            last_date,
        )
        ctx = StepContext(date=last_date, is_rebalance_day=True)
        ctx.target_portfolio = signal

        # 预填 PlanningStep 所需的 slice_ 和 account_view
        try:
            ctx.slice_ = self._data_feed.get_slice(last_date)
        except Exception:
            logger.exception("Flush: unexpected error getting slice for {}", last_date)
            raise
        ctx.account_view = self._brokerage.get_account()

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

    def _step(self, date: str) -> bool:
        """执行单日步骤 -- 通过 Step chain 编排。返回 False 表示某 step 失败。"""
        is_rebalance = self._is_rebalance_day(date)
        ctx = StepContext(date=date, is_rebalance_day=is_rebalance)
        delay = self._execution_delay
        deferred_signal = self._dequeue_delayed_signal()

        # 执行 Step chain
        for step in self._steps:
            # execution_delay: 无延迟信号时跳过 PlanningStep
            # （信号已入队，等待 N 日后执行）
            if delay > 0 and deferred_signal is None and isinstance(step, PlanningStep):
                continue

            # execution_delay: PlanningStep 前恢复延迟信号
            if (
                delay > 0
                and deferred_signal is not None
                and isinstance(step, PlanningStep)
            ):
                ctx.target_portfolio = deferred_signal
                ctx.is_rebalance_day = True

            result = step.execute(ctx)
            if not result.success:
                step_name = type(step).__name__
                errors = "; ".join(result.errors) if result.errors else "unknown"
                logger.warning(
                    "Step {} failed on {}: {}",
                    step_name,
                    date,
                    errors,
                )
                return False

            # execution_delay: StrategyStep 后将当日信号入队并清除
            if delay > 0 and isinstance(step, StrategyStep):
                if ctx.target_portfolio is not None:
                    self._signal_queue.append(ctx.target_portfolio)
                ctx.target_portfolio = None

        # 累积跨日结果
        self._fills.extend(ctx.step_fills)
        self._orders.extend(ctx.step_orders)

        # 审计日志: 批量记录 PreTrade 决策
        if self._audit_collector is not None and ctx.pre_trade_decisions:
            self._audit_collector.record_pre_trade_decisions(
                date,
                tuple(ctx.pre_trade_decisions),
            )

        return True

    def _is_rebalance_day(self, date: str) -> bool:
        """根据配置判断是否为调仓日 — 委托给 engine_steps.is_rebalance_day。"""
        return is_rebalance_day(
            date,
            self._config.rebalance_freq,
            self._trading_days,
            self._trading_day_index,
        )
