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

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import polars as pl
from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_kernel.identity import InstrumentId

from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.fills import FillEvent
from ditto_engine.accounting.order_book import Order
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.backtest.data_feed import DataFeed, Slice
from ditto_engine.backtest.manifest import (
    RuleRefCollector,
    RunManifest,
    RunMode,
    hash_config,
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
)
from ditto_engine.execution.brokerage import Brokerage
from ditto_engine.execution.planner import ExecutionPlanner
from ditto_engine.execution.reality import FeeModel
from ditto_engine.execution.rules import InstrumentRuleProvider
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

    """

    run_id: str
    period: tuple[str, str]
    final_nav: float = 0.0
    total_trades: int = 0
    orders: list[Order] = field(default_factory=list)
    fills: list[FillEvent] = field(default_factory=list)
    account_view: AccountView | None = None
    manifest: RunManifest | None = None


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

    """

    clock: Clock
    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_collector: ExecutionAuditCollector | None = None
    event_bus: EventBus | None = None


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

        # 跨日可变状态
        self._fills: list[FillEvent] = []
        self._orders: list[Order] = []

        self._strategy_context = StrategyContext()
        self._rule_ref_collector = RuleRefCollector()
        self._trading_days: tuple[str, ...] = ()
        self._input_instruments: set[InstrumentId] = set()

        # TradeBuilder -- 根据 config.trade_matching 创建成交匹配器
        if config.trade_matching == TradeMatchingMethod.FLAT_TO_FLAT:
            self._trade_builder = FlatToFlatTradeBuilder()
        else:
            self._trade_builder = FifoTradeBuilder()
        self._recorded_trade_ids: set[str] = set()

        # 构建 Step chain
        self._steps = self._build_steps()

    def _build_steps(self) -> tuple[object, ...]:
        """构建 TradingStep chain。"""
        return (
            DataFetchStep(
                data_feed=self._data_feed,
                clock=self._clock,
                brokerage=self._brokerage,
                strategy_context=self._strategy_context,
                input_instruments=self._input_instruments,
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
                input_bundle_builder=lambda ctx: self._build_input_bundle(
                    ctx.date,
                    ctx.slice_,  # type: ignore[arg-type]
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
                fee_model=self._fee_model,  # type: ignore[arg-type]
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
        self._trading_days = tuple(days)
        start = days[0] if days else self._config.start_date
        end = days[-1] if days else self._config.end_date

        for date in days:
            self._step(date)

        account_view = self._brokerage.get_account()

        # flush 未平仓交易 -- 回测结束时记录剩余开仓交易
        if self._audit_collector is not None:
            for trade in self._trade_builder.flush():
                if trade.trade_id not in self._recorded_trade_ids:
                    self._audit_collector.record_closed_trade(trade)
                    self._recorded_trade_ids.add(trade.trade_id)

        # 构建运行清单 -- 真实治理字段
        input_refs = tuple(sorted(self._input_instruments))
        config_hash = hash_config(
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            initial_cash=self._config.initial_cash,
            strategy_id=self._config.strategy_id,
            rebalance_freq=self._config.rebalance_freq,
            engine_version=self._config.engine_version,
        )
        manifest = RunManifest(
            run_id=run_id,
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            mode=RunMode.BACKTEST,
            input_refs=input_refs,
            parameter_overrides=self._config.parameter_overrides,
            rule_refs=self._rule_ref_collector.rule_refs,
            config_hash=config_hash,
            engine_version=self._config.engine_version,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        return EngineResult(
            run_id=run_id,
            period=(start, end),
            final_nav=account_view.nav,
            total_trades=len(self._fills),
            orders=list(self._orders),
            fills=list(self._fills),
            account_view=account_view,
            manifest=manifest,
        )

    # -- internals ------------------------------------------------------------

    def _build_input_bundle(self, date: str, slice_: Slice) -> StrategyInputBundle:
        """
        构建 StrategyInputBundle -- 子类可覆盖以注入自定义列.

        默认实现从 slice_.bars 提取 instrument_id / OHLCV / signal_value。
        """
        instrument_ids = list(slice_.bars.keys())

        instruments = pl.DataFrame({"instrument_id": instrument_ids})

        market_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []
        for iid, bar in slice_.bars.items():
            market_rows.append(
                {
                    "instrument_id": iid,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                },
            )
            signal_rows.append(
                {
                    "instrument_id": iid,
                    "signal_value": (
                        (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                    ),
                },
            )

        return StrategyInputBundle(
            trade_date=date,
            strategy_id=self._config.strategy_id,
            run_id=self._config.strategy_run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=pl.DataFrame(signal_rows),
            benchmark_close=slice_.benchmark_close,
        )

    def _step(self, date: str) -> None:
        """执行单日步骤 -- 通过 Step chain 编排。"""
        is_rebalance = self._is_rebalance_day(date)
        ctx = StepContext(date=date, is_rebalance_day=is_rebalance)

        # 执行 Step chain
        for step in self._steps:
            result = step.execute(ctx)  # type: ignore[union-attr]
            if not result.success:  # type: ignore[attr-defined]
                break

        # 累积跨日结果
        self._fills.extend(ctx.step_fills)
        self._orders.extend(ctx.step_orders)

        # 审计日志: 批量记录 PreTrade 决策
        if self._audit_collector is not None and ctx.pre_trade_decisions:
            self._audit_collector.record_pre_trade_decisions(
                date,
                tuple(ctx.pre_trade_decisions),  # type: ignore[arg-type]
            )

    def _is_rebalance_day(self, date: str) -> bool:
        """
        根据配置判断是否为调仓日.

        daily: 每日
        weekly: 每自然周第一个交易日（基于 trading_days 判断 ISO week 跨越）
        monthly: 每月第一个交易日
        """
        if self._config.rebalance_freq == "daily":
            return True

        if self._config.rebalance_freq == "weekly":
            idx = self._trading_days.index(date)
            if idx == 0:
                return True
            curr = datetime.strptime(date, "%Y-%m-%d")
            prev = datetime.strptime(self._trading_days[idx - 1], "%Y-%m-%d")
            return curr.isocalendar()[1] != prev.isocalendar()[1]

        if self._config.rebalance_freq == "monthly":
            month_prefix = date[:7]
            idx = self._trading_days.index(date)
            if idx == 0:
                return True
            return not self._trading_days[idx - 1].startswith(month_prefix)

        return True
