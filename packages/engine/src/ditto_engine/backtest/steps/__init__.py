"""
Backtest Steps -- 回测引擎步骤化定义.

TradingStep Protocol + StepResult + StepContext + 所有 Step 实现。

拆分为子模块:
- types: StepResult, StepContext, TradingStep Protocol
- data_fetch: DataFetchStep
- risk_scan: RiskScanStep
- strategy: StrategyStep
- planning: PlanningStep
- pre_trade: PreTradeStep
- execution: ExecutionStep
- audit: AuditStep
"""

from ditto_engine.backtest.steps.audit import AuditStep
from ditto_engine.backtest.steps.data_fetch import DataFetchStep
from ditto_engine.backtest.steps.execution import ExecutionStep
from ditto_engine.backtest.steps.planning import PlanningStep
from ditto_engine.backtest.steps.pre_trade import PreTradeStep
from ditto_engine.backtest.steps.risk_scan import RiskScanStep
from ditto_engine.backtest.steps.strategy import StrategyStep
from ditto_engine.backtest.steps.types import StepContext, StepResult, TradingStep

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
