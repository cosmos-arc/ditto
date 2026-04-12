"""
策略运行记录模型.

StrategyRunRecord — 策略运行的生命周期记录。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.enums import RunStatus


@dataclass(frozen=True)
class StrategyRunRecord:
    """
    策略运行记录.

    Attributes:
        run_id: 运行唯一标识.
        strategy_id: 策略 ID.
        strategy_version: 策略版本.
        mode: 运行模式 (backtest / research / recommendation / live).
        status: 运行状态.
        started_at: 开始时间 (RFC3339).
        completed_at: 完成时间 (RFC3339).
        error_message: 错误信息.
        parent_run_id: 父运行 ID（空字符串表示原始运行，非空表示重放）.

    """

    run_id: str
    strategy_id: str
    strategy_version: str = ""
    mode: str = "backtest"
    status: str = RunStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    error_message: str = ""
    parent_run_id: str = ""
    progress_pct: float = 0.0
    current_step: str = ""
    completed_days: int = 0
    total_days: int = 0
    config_json: str = ""


__all__ = ["StrategyRunRecord"]
