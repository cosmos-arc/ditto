"""
TradingStep Protocol + StepResult + StepContext -- 回测引擎步骤核心类型.

- TradingStep Protocol: 每个步骤必须实现的接口
- StepResult: 步骤执行结果（成功/失败/审计数据）
- StepContext: 单日步骤链的共享可变状态
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ditto_execution.planner import ExecutionPlan
from ditto_execution.targets import TargetPortfolioLike
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRules
from ditto_portfolio.accounting import AccountView, FillEvent, Order

from ditto_backtest.audit.records import PreTradeDecisionRecord
from ditto_backtest.data_feed import Slice

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
