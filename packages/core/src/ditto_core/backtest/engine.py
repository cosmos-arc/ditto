"""
EngineLoop — 回测引擎主循环 + 配置/结果模型.

V1 每日循环:
  1. 获取 Slice (DataFeed)
  2. 获取账户快照 (Brokerage)
  3. PostTrade 风控 (组合扫描 → RiskLock)
  4. 策略 Pipeline → TargetPortfolio
  5. ExecutionPlanner → ExecutionPlan (含 locked_instruments)
  6. PreTrade 校验 → 过滤/resize 订单
  7. 提交订单 (Brokerage)
  8. 处理成交 (Brokerage.process_pending)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import polars as pl

from ditto_core.accounting.account import AccountView
from ditto_core.accounting.buying_power import CashAccountBuyingPower
from ditto_core.accounting.order_book import Order
from ditto_core.backtest.data_feed import DataFeed, Slice
from ditto_core.backtest.manifest import RuleRefCollector, RunManifest, RunMode
from ditto_core.backtest.risk.post_trade import (
    PostTradeRiskGuard,
    RiskActionType,
)
from ditto_core.backtest.risk.pre_trade import (
    CompositePreTradeCheck,
    Decision,
    PreTradeContext,
)
from ditto_core.backtest.statistics import (
    ExecutionAuditCollector,
    PreTradeDecisionRecord,
    RiskScanRecord,
)
from ditto_core.execution.brokerage import Brokerage, ProcessInput
from ditto_core.execution.fills import FillEvent
from ditto_core.execution.planner import ExecutionPlanner
from ditto_core.execution.reality import FeeModel
from ditto_core.execution.rules import InstrumentRuleProvider, InstrumentRules
from ditto_core.execution.trade_builder import TradeMatchingMethod
from ditto_core.strategy.context import StrategyContext
from ditto_core.strategy.pipeline import StrategyInputBundle, StrategyPipeline

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
    引擎配置 — frozen, 运行前确定.

    Attributes:
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始资金
        benchmark_id: 基准标的 ID (None = 无基准)
        mode: 运行模式
        trade_matching: 成交匹配算法
        strategy_id: 策略 ID
        strategy_run_id: 策略运行 ID
        rebalance_freq: 调仓频率 (daily / weekly / monthly)
        engine_version: 引擎版本号 (用于 manifest/diff 追踪)

    """

    start_date: str
    end_date: str
    initial_cash: float
    benchmark_id: str | None = None
    mode: EngineMode = EngineMode.BACKTEST
    trade_matching: TradeMatchingMethod = TradeMatchingMethod.FIFO
    strategy_id: str = "default"
    strategy_run_id: str = ""
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# EngineResult
# ---------------------------------------------------------------------------


@dataclass
class EngineResult:
    """
    引擎运行结果 — 可变, 运行过程中累积.

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
    引擎可选组件 — 将可选依赖打包以减少构造参数数量。

    Attributes:
        fee_model: 手续费模型 (用于 PreTrade 估算, None = 不使用独立费率)
        rule_provider: 三层规则提供者 (None = 不传规则给 Planner)
        post_trade_guard: PostTrade 风控扫描器 (None = 跳过 PostTrade)
        audit_collector: 审计收集器 (None = 不记录审计日志)

    """

    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_collector: ExecutionAuditCollector | None = None


# ---------------------------------------------------------------------------
# EngineLoop
# ---------------------------------------------------------------------------


class EngineLoop:
    """
    回测引擎主循环 — 编排每日执行流程.

    Parameters
    ----------
        config: 引擎配置
        pipeline: 策略 Pipeline
        planner: 执行计划器
        brokerage: 经纪商 (构造时传入 rules_getter)
        pre_trade_check: 组合 PreTrade 校验
        data_feed: 市场数据源
        options: 可选组件 (费率模型、规则提供者、风控、审计)

    """

    def __init__(
        self,
        config: EngineConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: DataFeed,
        options: EngineOptions = EngineOptions(),
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._planner = planner
        self._brokerage = brokerage
        self._pre_trade_check = pre_trade_check
        self._data_feed = data_feed
        self._fee_model = options.fee_model
        self._rule_provider = options.rule_provider
        self._post_trade_guard = options.post_trade_guard
        self._audit_collector = options.audit_collector

        self._fills: list[FillEvent] = []
        self._orders: list[Order] = []
        self._strategy_context = StrategyContext()
        self._rule_ref_collector = RuleRefCollector()
        self._trading_days: tuple[str, ...] = ()

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

        # 构建运行清单 — RuleRefCollector 积累的 rule_refs
        manifest = RunManifest(
            run_id=run_id,
            strategy_id=self._config.strategy_id,
            strategy_version="",
            mode=RunMode.BACKTEST,
            rule_refs=self._rule_ref_collector.rule_refs,
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

    def _step(self, date: str) -> None:
        """执行单日步骤。"""
        slice_ = self._data_feed.get_slice(date)
        account_view = self._brokerage.get_account()

        # 每日清除到期锁定 — cooldown 未到期的锁定保留
        self._strategy_context.clear_locks(date)

        # PostTrade 风控扫描 — 在 Pipeline 前执行
        if self._post_trade_guard is not None:
            risk_actions = self._post_trade_guard.scan(account_view, slice_)
            # 审计日志：记录风控扫描结果
            if self._audit_collector is not None and risk_actions:
                self._audit_collector.record_risk_scan(
                    date,
                    tuple(
                        RiskScanRecord(
                            trade_date=date,
                            rule_id=action.rule_id,
                            instrument_id=action.instrument_id,
                            severity=action.severity,
                            action_taken=action.action_type,
                            detail=action.detail,
                            current_value=action.current_value,
                            threshold=action.threshold,
                        )
                        for action in risk_actions
                    ),
                )
            for action in risk_actions:
                if (
                    action.action_type
                    in (RiskActionType.REDUCE_POSITION, RiskActionType.LIQUIDATE)
                    and action.instrument_id != "*"
                ):
                    self._strategy_context.lock_instrument(
                        action.instrument_id,
                        action.detail,
                        cooldown_until=action.cooldown_until_date,
                    )

        if self._is_rebalance_day(date):
            input_bundle = self._build_input_bundle(date, slice_)
            target = self._pipeline.run(self._strategy_context, input_bundle)

            # 获取三层规则 — 传给 Planner 用于涨跌停/lot_size 检查
            rules = self._fetch_rules(date, slice_)

            # 收集规则引用 — RuleRefCollector first_observed (F3)
            self._rule_ref_collector.observe(date, rules)

            plan = self._planner.plan(
                target=target,
                account_view=account_view,
                trade_date=date,
                market_snapshots=slice_.bars,
                rules=rules,
                locked_instruments=self._strategy_context.get_locked_instruments(),
            )

            # PreTrade 校验循环 — 逐单检查, 滚动更新 context (F1)
            pre_trade_context = self._build_pre_trade_context(
                account_view,
                slice_,
                rules,
            )
            pre_trade_decisions = self._run_pre_trade_checks(
                date,
                plan.orders,
                pre_trade_context,
            )

            # 审计日志：批量记录 PreTrade 决策
            if self._audit_collector is not None and pre_trade_decisions:
                self._audit_collector.record_pre_trade_decisions(
                    date,
                    tuple(pre_trade_decisions),
                )

        # 处理成交
        process_input = self._build_process_input(date, slice_)
        step_fills = self._brokerage.process_pending(process_input)
        self._fills.extend(step_fills)

    def _run_pre_trade_checks(
        self,
        date: str,
        orders: tuple[Order, ...],
        pre_trade_context: PreTradeContext,
    ) -> list[PreTradeDecisionRecord]:
        """
        执行 PreTrade 校验循环，返回审计决策记录.

        逐单检查, 滚动更新 context (F1)。
        """
        _decision_map = {
            Decision.ACCEPT: "accepted",
            Decision.REJECT: "rejected",
            Decision.RESIZE: "resized",
        }
        decisions: list[PreTradeDecisionRecord] = []

        for order in orders:
            result = self._pre_trade_check.check_order(order, pre_trade_context)

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
                    trade_date=date,
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    direction=order.direction.value,
                    original_quantity=order.quantity,
                    final_quantity=final_qty,
                    decision=_decision_map.get(result.decision, result.decision),
                    reason=result.reason,
                    check_sequence=result.triggered_checks,
                ),
            )

            if result.decision == Decision.REJECT:
                continue

            final_order = (
                order.with_quantity(result.resized_quantity)
                if result.resized_quantity is not None
                else order
            )
            self._brokerage.place_order(final_order)
            self._orders.append(final_order)
            # F1: 更新滚动上下文
            pre_trade_context = pre_trade_context.with_order_accepted(
                final_order,
            )

        return decisions

    def _fetch_rules(
        self,
        date: str,
        slice_: Slice,
    ) -> dict[str, InstrumentRules] | None:
        """通过 RuleProvider 获取三层规则，无 provider 返回 None。"""
        if self._rule_provider is None:
            return None
        instrument_ids = list(slice_.bars.keys())
        return self._rule_provider.get_rules(date, instrument_ids)

    def _is_rebalance_day(self, date: str) -> bool:
        """
        根据配置判断是否为调仓日.

        daily: 每日
        weekly: 每周一 (weekday == 0)
        monthly: 每月第一个交易日
        """
        if self._config.rebalance_freq == "daily":
            return True

        if self._config.rebalance_freq == "weekly":
            parsed = datetime.strptime(date, "%Y-%m-%d")
            return parsed.weekday() == 0

        if self._config.rebalance_freq == "monthly":
            month_prefix = date[:7]
            idx = self._trading_days.index(date)
            if idx == 0:
                return True
            return not self._trading_days[idx - 1].startswith(month_prefix)

        return True

    def _build_pre_trade_context(
        self,
        account_view: AccountView,
        slice_: Slice,
        rules: dict[str, InstrumentRules] | None,
    ) -> PreTradeContext:
        """构建 PreTrade 校验上下文 (V3)。"""
        if self._fee_model is None:
            raise RuntimeError("fee_model is required for PreTrade")
        return PreTradeContext(
            account_view=account_view,
            rules=rules or {},
            market_snapshots=slice_.bars,
            fee_model=self._fee_model,
            buying_power_model=CashAccountBuyingPower(),
            pending_tickets=account_view.order_book.get_pending(),
        )

    def _build_input_bundle(
        self,
        date: str,
        slice_: Slice,
    ) -> StrategyInputBundle:
        """
        从 Slice 构建 StrategyInputBundle.

        V1: 从 bars 构建 market_data + signal_values (momentum signal).
        """
        instrument_ids = list(slice_.bars.keys())
        instruments = pl.DataFrame(
            {"instrument_id": instrument_ids},
        )

        # Build market_data and signal_values in a single pass
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
            trade_date=date,
            strategy_id=self._config.strategy_id,
            run_id=self._config.strategy_run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=pl.DataFrame(signal_rows),
            benchmark_close=slice_.benchmark_close,
        )

    def _build_process_input(self, date: str, slice_: Slice) -> ProcessInput:
        """将 Slice 转换为 ProcessInput (Brokerage.process_pending 输入)。"""
        return ProcessInput(
            step_time=slice_.step_time,
            trade_date=date,
            bars=slice_.bars,
        )
