"""
策略运行共享类型 — Process 模块.

包含所有策略相关的协议、DTO 定义。
BacktestService 与 StrategyRunService 共用此模块中的类型定义。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from ditto_strategy.runs.models import StrategyRunRecord

__all__ = [
    "BacktestTrigger",
    "RunLifecycleService",
    "StrategySliceTrigger",
    "mark_run_failed",
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
        *,
        parent_run_id: str = "",
        config_json: str = "",
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

    def mark_cancelled(self, run_id: str) -> bool:
        """标记运行为 cancelled。"""
        ...

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """获取运行记录。"""
        ...

    def is_cancelled(self, run_id: str) -> bool:
        """检查运行是否已被取消。"""
        ...

    def update_progress(
        self,
        run_id: str,
        *,
        progress_pct: float = 0.0,
        current_step: str = "",
        completed_days: int = 0,
        total_days: int = 0,
    ) -> bool:
        """更新运行进度。"""
        ...


# ===========================================================================
# mark_run_failed — 异常生命周期辅助函数
# ===========================================================================


def mark_run_failed(
    run_svc: RunLifecycleService | None,
    run_id: str,
    exc: BaseException,
) -> None:
    """
    标记运行失败 — 消除 ``mark_failed + raise`` 重复模式.

    当 run_svc 非空时调用 ``mark_failed``，否则静默跳过。
    调用方仍需 ``raise`` 重新抛出异常。

    Args:
        run_svc: 运行生命周期服务，为 None 时静默跳过。
        run_id: 运行 ID。
        exc: 捕获的异常实例。

    示例::

        try:
            return self._execute_backtest(run_id)
        except Exception as exc:
            mark_run_failed(run_svc, run_id, exc)
            raise

    """
    if run_svc is not None:
        run_svc.mark_failed(run_id, str(exc))


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
