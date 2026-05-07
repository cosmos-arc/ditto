"""
Backtest Steps -- 回测引擎步骤化定义.

TradingStep Protocol + StepResult + StepContext + 所有 Step 实现。

拆分为子模块:
- types: StepResult, StepContext, TradingStep Protocol
- input_bundle: build_input_bundle 共享函数
- data_fetch: DataFetchStep
- risk_scan: RiskScanStep
- strategy: StrategyStep
- planning: PlanningStep
- pre_trade: PreTradeStep
- execution: ExecutionStep
- audit: AuditStep
"""

from ditto_backtest.steps.audit import AuditStep
from ditto_backtest.steps.data_fetch import DataFetchStep
from ditto_backtest.steps.execution import ExecutionStep
from ditto_backtest.steps.input_bundle import build_input_bundle
from ditto_backtest.steps.planning import PlanningStep
from ditto_backtest.steps.pre_trade import PreTradeStep
from ditto_backtest.steps.risk_scan import RiskScanStep
from ditto_backtest.steps.strategy import StrategyStep
from ditto_backtest.steps.types import StepContext, StepResult, TradingStep

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
    "build_input_bundle",
]
