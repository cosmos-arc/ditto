"""
TradingStep Protocol + StepResult + StepContext -- 回测引擎步骤核心类型.

- TradingStep Protocol: 每个步骤必须实现的接口
- StepResult: 步骤执行结果（成功/失败/审计数据）
- StepContext: 单日步骤链的共享可变状态
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ditto_execution.orders.book import OrderBookReadOnly
from ditto_execution.orders.model import Order
from ditto_execution.planner import ExecutionPlan
from ditto_execution.targets import TargetPortfolioLike
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_kernel.trading import InstrumentRules, MarketSnapshot
from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_backtest.audit.records import PreTradeDecisionRecord
from ditto_backtest.data_feed import Slice
from ditto_backtest.errors import SimulationError

__all__ = [
    "StepContext",
    "StepResult",
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
        time_context: 时间上下文（PIT 语义，由 Synchronizer 提供）
        is_rebalance_day: 是否为调仓日
        bars: 当日市场行情（由 Synchronizer 提供）
        source_snapshot_ids: 当日输入行情的上游快照 ID（由 Synchronizer 提供）
        slice_: 当日数据切片（benchmark_close 等，由 EngineLoop 设置）
        account_view: 账户快照（由 DataFetchStep 设置）
        order_book: 订单簿只读视图（由 DataFetchStep 设置）
        target_portfolio: 目标组合（由 StrategyStep 设置，仅调仓日）
        execution_plan: 执行计划（由 PlanningStep 设置，仅调仓日）
        rules: 三层规则（由 PlanningStep 设置，仅调仓日）
        step_orders: 当日已提交订单（由 PreTradeStep 追加）
        step_fills: 当日成交事件（由 ExecutionStep 追加）
        pre_trade_decisions: PreTrade 决策记录（由 PreTradeStep 追加）

    """

    # -- Day info (set by EngineLoop from Synchronizer output) --
    time_context: TimeContext
    is_rebalance_day: bool
    bars: dict[InstrumentId, MarketSnapshot]
    source_snapshot_ids: dict[InstrumentId, str] = field(default_factory=dict)

    # -- Step outputs (set by steps, read by subsequent steps) --
    slice_: Slice | None = None
    account_view: AccountView | None = None
    order_book: OrderBookReadOnly | None = None
    target_portfolio: TargetPortfolioLike | None = None
    execution_plan: ExecutionPlan | None = None
    rules: dict[InstrumentId, InstrumentRules] | None = None

    # -- Daily accumulators (appended by steps) --
    step_orders: list[Order] = field(default_factory=list)
    step_fills: list[FillEvent] = field(default_factory=list)
    pre_trade_decisions: list[PreTradeDecisionRecord] = field(default_factory=list)

    # -- 类型安全 getter（require_*）--
    # Steps 通过这些方法断言前置条件已满足，否则抛出 SimulationError。
    # 适用于步骤必须某字段非 None 才能继续的场景。
    # 对于"可选跳过"场景（如 execution_plan 为 None 则 skipped），
    # 仍应直接检查 `if ctx.xxx is None: skipped()`。

    def require_slice(self) -> Slice:
        """断言 slice_ 已设置，否则抛出 SimulationError。"""
        if self.slice_ is None:
            raise SimulationError("slice_ required before this step")
        return self.slice_

    def require_account_view(self) -> AccountView:
        """断言 account_view 已设置，否则抛出 SimulationError。"""
        if self.account_view is None:
            raise SimulationError("account_view required before this step")
        return self.account_view

    def require_execution_plan(self) -> ExecutionPlan:
        """断言 execution_plan 已设置，否则抛出 SimulationError。"""
        if self.execution_plan is None:
            raise SimulationError("execution_plan required before this step")
        return self.execution_plan

    def require_target_portfolio(self) -> TargetPortfolioLike:
        """断言 target_portfolio 已设置，否则抛出 SimulationError。"""
        if self.target_portfolio is None:
            raise SimulationError("target_portfolio required before this step")
        return self.target_portfolio


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
