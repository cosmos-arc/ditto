"""
Engine 辅助模型 — EngineOptions / assemble_engine_result / is_rebalance_day.

将非循环逻辑从 EngineLoop 拆出，降低 engine.py 复杂度。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ditto_execution.brokerage import Brokerage
from ditto_execution.planner import ExecutionPlanner
from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import FeeModel, InstrumentRuleProvider
from ditto_portfolio.accounting import AccountView, FillEvent, Order
from ditto_risk.post_trade import PostTradeRiskGuard
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from loguru import logger

from ditto_backtest.config import EngineConfig
from ditto_backtest.data_feed import DataFeed, Slice
from ditto_backtest.errors import SimulationError
from ditto_backtest.manifest import RuleRefCollector, RunManifest
from ditto_backtest.result import EngineResult
from ditto_backtest.statistics import ExecutionAuditCollector
from ditto_backtest.steps import (
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

__all__ = [
    "EngineOptions",
    "StepDeps",
    "assemble_engine_result",
    "build_steps",
    "is_rebalance_day",
    "require_slice",
]


@dataclass(frozen=True)
class EngineOptions:
    """
    引擎可选组件 — 将可选依赖打包以减少构造参数数量。

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


@dataclass
class StepDeps:
    """Step chain 构建所需的依赖容器 — 从 EngineLoop 实例状态提取。"""

    config: EngineConfig
    pipeline: StrategyPipeline
    planner: ExecutionPlanner
    brokerage: Brokerage
    pre_trade_check: CompositePreTradeCheck
    data_feed: DataFeed
    clock: Clock
    fee_model: FeeModel | None
    rule_provider: InstrumentRuleProvider | None
    post_trade_guard: PostTradeRiskGuard | None
    audit_collector: ExecutionAuditCollector | None
    event_bus: EventBus | None
    input_bundle_builder: Callable[[StepContext], StrategyInputBundle] | None
    strategy_context: StrategyContext
    input_instruments: set[InstrumentId]
    bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]]
    rule_ref_collector: RuleRefCollector
    trade_builder: Any  # FifoTradeBuilder | FlatToFlatTradeBuilder
    recorded_trade_ids: set[str]
    build_input_bundle_fn: Callable[[str, Slice], StrategyInputBundle]


def require_slice(slice_: Slice | None) -> Slice:
    """断言 slice_ 非 None — 用于 lambda 中类型收窄."""
    if slice_ is None:
        msg = "slice_ required"
        raise SimulationError(msg, step="engine")
    return slice_


def assemble_engine_result(  # noqa: PLR0913
    *,
    run_id: str,
    start: str,
    end: str,
    account_view: AccountView,
    manifest: RunManifest,
    fills: list[FillEvent],
    orders: list[Order],
    skipped: list[str],
    cancelled: bool,
) -> EngineResult:
    """组装 EngineResult — 汇总账户、成交、订单等最终状态."""
    return EngineResult(
        run_id=run_id,
        period=(start, end),
        final_nav=account_view.nav,
        total_trades=len(fills),
        orders=list(orders),
        fills=list(fills),
        account_view=account_view,
        manifest=manifest,
        skipped_dates=tuple(skipped),
        cancelled=cancelled,
    )


def is_rebalance_day(
    date: str,
    freq: str,
    trading_days: tuple[str, ...],
    trading_day_index: dict[str, int],
) -> bool:
    """
    根据配置判断是否为调仓日（纯函数）.

    daily: 每日
    weekly: 每自然周第一个交易日（基于 trading_days 判断 ISO week 跨越）
    monthly: 每月第一个交易日

    date 不在 trading_days 中时，fallback 为 daily（return True），
    避免抛出 ValueError。
    """
    if freq == "daily":
        return True

    idx = trading_day_index.get(date)
    if idx is None:
        logger.warning(
            (
                "is_rebalance_day: date={!r} 不在"
                " trading_days index 中, fallback 为 daily"
            ),
            date,
        )
        return True

    # 首个交易日始终为调仓日（weekly / monthly 共享逻辑）
    if idx == 0:
        return True

    prev_date = trading_days[idx - 1]

    if freq == "weekly":
        curr = datetime.strptime(date, "%Y-%m-%d")
        prev = datetime.strptime(prev_date, "%Y-%m-%d")
        return curr.isocalendar()[1] != prev.isocalendar()[1]

    if freq == "monthly":
        return not prev_date.startswith(date[:7])

    return True


def build_steps(deps: StepDeps) -> tuple[TradingStep, ...]:
    """构建 TradingStep chain。"""

    def _default_bundle_builder(ctx: StepContext) -> StrategyInputBundle:
        return deps.build_input_bundle_fn(
            ctx.date,
            require_slice(ctx.slice_),
        )

    input_bundle_builder = deps.input_bundle_builder
    if input_bundle_builder is None:
        input_bundle_builder = _default_bundle_builder

    return (
        DataFetchStep(
            data_feed=deps.data_feed,
            clock=deps.clock,
            brokerage=deps.brokerage,
            strategy_context=deps.strategy_context,
            input_instruments=deps.input_instruments,
            bar_fingerprints=deps.bar_fingerprints,
        ),
        RiskScanStep(
            post_trade_guard=deps.post_trade_guard,
            audit_collector=deps.audit_collector,
            event_bus=deps.event_bus,
            strategy_context=deps.strategy_context,
            clock=deps.clock,
        ),
        StrategyStep(
            pipeline=deps.pipeline,
            strategy_context=deps.strategy_context,
            strategy_id=deps.config.strategy_id,
            strategy_run_id=deps.config.strategy_run_id,
            input_bundle_builder=input_bundle_builder,
        ),
        PlanningStep(
            planner=deps.planner,
            rule_provider=deps.rule_provider,
            rule_ref_collector=deps.rule_ref_collector,
            strategy_context=deps.strategy_context,
        ),
        PreTradeStep(
            pre_trade_check=deps.pre_trade_check,
            brokerage=deps.brokerage,
            fee_model=deps.fee_model,
            event_bus=deps.event_bus,
            clock=deps.clock,
        ),
        ExecutionStep(
            brokerage=deps.brokerage,
            event_bus=deps.event_bus,
            clock=deps.clock,
        ),
        AuditStep(
            audit_collector=deps.audit_collector,
            brokerage=deps.brokerage,
            trade_builder=deps.trade_builder,
            recorded_trade_ids=deps.recorded_trade_ids,
        ),
    )
