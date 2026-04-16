"""
引擎配置 — EngineMode + EngineConfig.

从 engine.py 提取，消除 engine.py ↔ result.py 循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_kernel.identity import InstrumentId

from ditto_engine.execution.trade_builder import TradeMatchingMethod

__all__ = [
    "EngineConfig",
    "EngineMode",
]


class EngineMode(StrEnum):
    """引擎运行模式。"""

    BACKTEST = "backtest"
    LIVE = "live"


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
