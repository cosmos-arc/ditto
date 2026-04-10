"""
策略运行共享类型 — Process 模块.

包含所有策略相关的协议、DTO 定义。
BacktestService 与 StrategyRunService 共用此模块中的类型定义。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

__all__ = [
    "BacktestTrigger",
    "RunLifecycleService",
    "StrategySliceTrigger",
]


# ===========================================================================
# RunLifecycleService — 策略运行生命周期协议
# ===========================================================================


@runtime_checkable
class RunLifecycleService(Protocol):
    """策略运行生命周期协议。"""

    def create_run(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = "",
        mode: str = "backtest",
    ) -> None:
        """创建运行记录。"""
        ...

    def mark_running(self, run_id: str) -> bool:
        """标记运行为 running。"""
        ...

    def mark_completed(self, run_id: str) -> bool:
        """标记运行为 completed。"""
        ...

    def mark_failed(self, run_id: str, error_message: str = "") -> bool:
        """标记运行为 failed。"""
        ...


# ===========================================================================
# Trigger DTO — Process Manager 输入
# ===========================================================================


@dataclass(frozen=True)
class BacktestTrigger:
    """回测触发器 — Process Manager 输入."""

    strategy_id: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class StrategySliceTrigger:
    """策略切片触发器 — Process Manager 输入."""

    strategy_id: str
    trade_date: date
