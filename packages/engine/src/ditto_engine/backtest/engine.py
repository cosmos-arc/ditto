"""
EngineLoop -- 回测引擎主循环 + 配置/结果模型.

V1 每日循环 (通过 TradingStep chain 编排):
  1. DataFetchStep: 获取 Slice + 账户快照 + 清除锁定
  2. RiskScanStep: PostTrade 风控扫描 + 锁管理
  3. StrategyStep: 策略 Pipeline -> TargetPortfolio (仅调仓日)
  4. PlanningStep: ExecutionPlanner -> ExecutionPlan (仅调仓日)
  5. PreTradeStep: PreTrade 校验 + 订单提交 (仅调仓日)
  6. ExecutionStep: 订单成交处理
  7. AuditStep: 审计记录 (账户快照 + 成交 + 已平仓交易)
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_kernel.identity import InstrumentId
from loguru import logger

from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import Order
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.backtest.data_feed import DataFeed, Slice
from ditto_engine.backtest.manifest import (
    InputRef,
    RuleRefCollector,
    RunManifest,
    RunMode,
    hash_config,
    hash_spec,
    hash_universe,
)
from ditto_engine.backtest.statistics import ExecutionAuditCollector
from ditto_engine.backtest.steps import (
    AuditStep,
    DataFetchStep,
    ExecutionStep,
    PlanningStep,
    PreTradeStep,
    RiskScanStep,
    StepContext,
    StrategyStep,
    TradingStep,
)
from ditto_engine.backtest.steps._input_bundle import build_input_bundle
from ditto_engine.execution.brokerage import Brokerage
from ditto_engine.execution.planner import ExecutionPlanner
from ditto_engine.execution.reality import FeeModel
from ditto_engine.execution.rules import InstrumentRuleProvider
from ditto_engine.execution.targets import TargetPortfolioLike
from ditto_engine.execution.trade_builder import (
    FifoTradeBuilder,
    FlatToFlatTradeBuilder,
    TradeMatchingMethod,
)
from ditto_engine.risk.post_trade import PostTradeRiskGuard
from ditto_engine.risk.pre_trade import CompositePreTradeCheck

__all__ = [
    "EngineConfig",
    "EngineLoop",
    "EngineMode",
    "EngineOptions",
    "EngineResult",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EngineMode(StrEnum):
    """引擎运行模式。"""

    BACKTEST = "backtest"
    LIVE = "live"


# ---------------------------------------------------------------------------
# EngineConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineConfig:
    """
    引擎配置 -- frozen, 运行前确定.

    Attributes:
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始资金
        benchmark_id: 基准标的 ID (None = 无基准)
        mode: 运行模式
        trade_matching: 成交匹配算法
        strategy_id: 策略 ID
        strategy_version: 策略版本
        strategy_run_id: 策略运行 ID
        parameter_overrides: 参数覆盖列表
        rebalance_freq: 调仓频率 (daily / weekly / monthly)
        engine_version: 引擎版本号 (用于 manifest/diff 追踪)

    """

    start_date: str
    end_date: str
    initial_cash: float
    benchmark_id: InstrumentId | None = None
    mode: EngineMode = EngineMode.BACKTEST
    trade_matching: TradeMatchingMethod = TradeMatchingMethod.FIFO
    strategy_id: str = "default"
    strategy_version: str = ""
    strategy_run_id: str = ""
    parameter_overrides: tuple[str, ...] = ()
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"
    execution_delay: int = 0


# ---------------------------------------------------------------------------
# EngineResult
# ---------------------------------------------------------------------------


@dataclass
class EngineResult:
    """
    引擎运行结果 -- 可变, 运行过程中累积.

    Attributes:
        run_id: 运行唯一 ID
        period: (start_date, end_date)
        final_nav: 最终净值
        total_trades: 总成交笔数
        orders: 所有提交的订单
        fills: 所有成交事件
        account_view: 最终账户快照
        manifest: 运行清单 (None = 未启用 RuleRefCollector)
        skipped_dates: Step 失败被跳过的日期

    """

    run_id: str
    period: tuple[str, str]
    final_nav: float = 0.0
    total_trades: int = 0
    orders: list[Order] = field(default_factory=list)
    fills: list[FillEvent] = field(default_factory=list)
    account_view: AccountView | None = None
    manifest: RunManifest | None = None
    skipped_dates: tuple[str, ...] = ()
    cancelled: bool = False


# ---------------------------------------------------------------------------
# EngineOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineOptions:
    """
    引擎可选组件 -- 将可选依赖打包以减少构造参数数量。

    Attributes:
        clock: 统一时间抽象 (必需, 用于事件时间戳和步进推进)
        fee_model: 手续费模型 (用于 PreTrade 估算, None = 不使用独立费率)
        rule_provider: 三层规则提供者 (None = 不传规则给 Planner)
        post_trade_guard: PostTrade 风控扫描器 (None = 跳过 PostTrade)
        audit_collector: 审计收集器 (None = 不记录审计日志)
        event_bus: 事件总线 (None = 不发布域事件)
        input_bundle_builder: 自定义 input bundle 构建器
            (None = 使用默认构建器)
        random_seed: 随机种子（用于可复现性，默认 42）
        should_stop: 协作式取消回调 (None = 不支持取消)
        on_progress: 进度回调 (completed_days, total_days)

    """

    clock: Clock
    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_collector: ExecutionAuditCollector | None = None
    event_bus: EventBus | None = None
    input_bundle_builder: Callable[[StepContext], StrategyInputBundle] | None = None
    random_seed: int = 42
    should_stop: Callable[[], bool] | None = None
    on_progress: Callable[[int, int], None] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_slice(slice_: Slice | None) -> Slice:
    """断言 slice_ 非 None — 用于 lambda 中类型收窄."""
    if slice_ is None:
        msg = "slice_ required"
        raise ValueError(msg)
    return slice_


def _collect_dependency_versions() -> tuple[str, ...]:
    """收集当前运行环境的依赖版本（用于可复现性审计）."""
    packages = ("polars", "ditto-engine")
    versions: list[str] = []
    for pkg in sorted(packages):
        try:
            ver = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            ver = "unknown"
        versions.append(f"{pkg}=={ver}")
    return tuple(versions)


# ---------------------------------------------------------------------------
# EngineLoop
# ---------------------------------------------------------------------------


class EngineLoop:
    """
    回测引擎主循环 -- 通过 TradingStep chain 编排每日执行流程.

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
        """构建 TradingStep chain。"""
        return (
            DataFetchStep(
                data_feed=self._data_feed,
                clock=self._clock,
                brokerage=self._brokerage,
                strategy_context=self._strategy_context,
                input_instruments=self._input_instruments,
                bar_fingerprints=self._bar_fingerprints,
            ),
            RiskScanStep(
                post_trade_guard=self._post_trade_guard,
                audit_collector=self._audit_collector,
                event_bus=self._event_bus,
                strategy_context=self._strategy_context,
                clock=self._clock,
            ),
            StrategyStep(
                pipeline=self._pipeline,
                strategy_context=self._strategy_context,
                strategy_id=self._config.strategy_id,
                strategy_run_id=self._config.strategy_run_id,
                input_bundle_builder=self._input_bundle_builder
                if self._input_bundle_builder is not None
                else lambda ctx: self._build_input_bundle(
                    ctx.date,
                    _require_slice(ctx.slice_),
                ),
            ),
            PlanningStep(
                planner=self._planner,
                rule_provider=self._rule_provider,
                rule_ref_collector=self._rule_ref_collector,
                strategy_context=self._strategy_context,
            ),
            PreTradeStep(
                pre_trade_check=self._pre_trade_check,
                brokerage=self._brokerage,
                fee_model=self._fee_model,
                event_bus=self._event_bus,
                clock=self._clock,
            ),
            ExecutionStep(
                brokerage=self._brokerage,
                event_bus=self._event_bus,
                clock=self._clock,
            ),
            AuditStep(
                audit_collector=self._audit_collector,
                brokerage=self._brokerage,
                trade_builder=self._trade_builder,
                recorded_trade_ids=self._recorded_trade_ids,
            ),
        )

    # -- public ---------------------------------------------------------------

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

        account_view = self._brokerage.get_account()

        # flush 未平仓交易 -- 回测结束时记录剩余开仓交易
        if self._audit_collector is not None:
            for trade in self._trade_builder.flush():
                if trade.trade_id not in self._recorded_trade_ids:
                    self._audit_collector.record_closed_trade(trade)
                    self._recorded_trade_ids.add(trade.trade_id)

        manifest = self._build_manifest(run_id)
        return self._assemble_result(
            run_id,
            start,
            end,
            account_view,
            manifest,
            skipped,
            cancelled,
        )

    # -- internals ------------------------------------------------------------

    def _build_manifest(self, run_id: str) -> RunManifest:
        """构建 RunManifest — 记录运行配置、规则引用、输入依赖等治理字段."""
        input_refs = tuple(sorted(self._input_instruments))
        config_hash = hash_config(
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            initial_cash=self._config.initial_cash,
            strategy_id=self._config.strategy_id,
            rebalance_freq=self._config.rebalance_freq,
            engine_version=self._config.engine_version,
        )
        spec_hash = hash_spec(
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            rebalance_freq=self._config.rebalance_freq,
        )
        return RunManifest(
            run_id=run_id,
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            mode=RunMode.BACKTEST,
            input_refs=input_refs,
            input_ref_details=self._build_input_ref_details(),
            parameter_overrides=self._config.parameter_overrides,
            rule_refs=self._rule_ref_collector.rule_refs,
            config_hash=config_hash,
            engine_version=self._config.engine_version,
            spec_hash=spec_hash,
            universe_hash=hash_universe(self._input_instruments),
            dependency_versions=_collect_dependency_versions(),
            random_seed=self._random_seed,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    def _assemble_result(
        self,
        run_id: str,
        start: str,
        end: str,
        account_view: AccountView,
        manifest: RunManifest,
        skipped: list[str],
        cancelled: bool,
    ) -> EngineResult:
        """组装 EngineResult — 汇总账户、成交、订单等最终状态."""
        return EngineResult(
            run_id=run_id,
            period=(start, end),
            final_nav=account_view.nav,
            total_trades=len(self._fills),
            orders=list(self._orders),
            fills=list(self._fills),
            account_view=account_view,
            manifest=manifest,
            skipped_dates=tuple(skipped),
            cancelled=cancelled,
        )

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

    def _build_input_ref_details(self) -> tuple[InputRef, ...]:
        """
        从 _bar_fingerprints 构建 InputRef 列表.

        对每个 instrument 的 sorted (date, close) 元组列表计算 SHA-256 哈希,
        生成 InputRef(instrument_id, data_hash, date_range, source).
        """
        refs: list[InputRef] = []
        for iid in sorted(self._bar_fingerprints.keys()):
            entries = self._bar_fingerprints[iid]
            sorted_entries = sorted(entries, key=lambda t: t[0])
            payload = ",".join(f"{d}:{c}" for d, c in sorted_entries)
            data_hash = (
                "sha256:"
                + hashlib.sha256(
                    payload.encode("utf-8"),
                ).hexdigest()[:16]
            )
            dates = [d for d, _ in sorted_entries]
            date_range = (dates[0], dates[-1]) if dates else ("", "")
            refs.append(
                InputRef(
                    instrument_id=iid,
                    data_hash=data_hash,
                    date_range=date_range,
                    source="backtest:data_feed",
                ),
            )
        return tuple(refs)

    def _dequeue_delayed_signal(self) -> TargetPortfolioLike | None:
        """取出到期的延迟信号。队列中信号数 >= execution_delay 时才有信号到期。"""
        if (
            self._execution_delay > 0
            and len(self._signal_queue) >= self._execution_delay
        ):
            return self._signal_queue.popleft()
        return None

    def _step(self, date: str) -> bool:
        """执行单日步骤 -- 通过 Step chain 编排。返回 False 表示某 step 失败。"""
        is_rebalance = self._is_rebalance_day(date)
        ctx = StepContext(date=date, is_rebalance_day=is_rebalance)
        delay = self._execution_delay
        deferred_signal = self._dequeue_delayed_signal()

        # 执行 Step chain
        for step in self._steps:
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
        """
        根据配置判断是否为调仓日.

        daily: 每日
        weekly: 每自然周第一个交易日（基于 trading_days 判断 ISO week 跨越）
        monthly: 每月第一个交易日

        date 不在 trading_days 中时，fallback 为 daily（return True），
        避免抛出 ValueError。
        """
        freq = self._config.rebalance_freq
        if freq == "daily":
            return True

        idx = self._trading_day_index.get(date)
        if idx is None:
            return True

        # 首个交易日始终为调仓日（weekly / monthly 共享逻辑）
        if idx == 0:
            return True

        prev_date = self._trading_days[idx - 1]

        if freq == "weekly":
            curr = datetime.strptime(date, "%Y-%m-%d")
            prev = datetime.strptime(prev_date, "%Y-%m-%d")
            return curr.isocalendar()[1] != prev.isocalendar()[1]

        if freq == "monthly":
            return not prev_date.startswith(date[:7])

        return True
