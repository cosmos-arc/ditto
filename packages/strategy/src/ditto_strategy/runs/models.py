"""
策略运行记录模型.

StrategyRunRecord — 策略运行的生命周期记录。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.strategy import RunStatus


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


@dataclass(frozen=True)
class StrategyRunCheckpointRecord:
    """
    策略运行 checkpoint 记录.

    保存每个运行最新的可恢复边界。具体执行引擎负责产生 checkpoint，
    控制面只持久化运行 ID、完成边界和可恢复位置。
    """

    run_id: str
    strategy_id: str
    strategy_version: str = ""
    mode: str = "backtest"
    completed_trade_date: str = ""
    resume_from: str | None = None
    completed_days: int = 0
    total_days: int = 0
    nav: float = 0.0
    order_count: int = 0
    fill_count: int = 0
    account_state_json: str = ""
    account_state_hash: str = ""
    settlement_state_json: str = ""
    settlement_state_hash: str = ""
    runtime_state_json: str = ""
    runtime_state_hash: str = ""
    updated_at: str = ""

    @property
    def can_resume(self) -> bool:
        """Whether this checkpoint points to a remaining resume date."""
        return bool(self.resume_from)


__all__ = ["StrategyRunCheckpointRecord", "StrategyRunRecord"]
