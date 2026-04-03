"""策略命令 DTO — 单次写入操作的输入参数."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RunBacktestCommand:
    """回测运行命令."""

    strategy_id: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class RunStrategySliceCommand:
    """单日策略运行命令."""

    strategy_id: str
    trade_date: date
