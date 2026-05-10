"""Strategy subdomain — 策略规格、执行策略、衍生语义。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

__all__ = [
    "DecisionFrame",
    "ExecutionPolicy",
    "ImpactModel",
    "RiskScope",
    "RunStatus",
]


class ImpactModel(StrEnum):
    """冲击成本模型枚举。"""

    NONE = "none"
    VOLUME_SHARE = "volume_share"


class RiskScope(StrEnum):
    """风控扫描范围。"""

    INSTRUMENT = "instrument"
    PORTFOLIO = "portfolio"


class RunStatus(StrEnum):
    """策略运行状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExecutionPolicy:
    """执行策略配置。"""

    pit_required: bool = True
    normalization_preset: str = "default"
    adj_type: str = "none"

    @property
    def is_pit_mode(self) -> bool:
        """是否启用 PIT 模式。"""
        return self.pit_required


class DecisionFrame(Protocol):
    """
    Pipeline 各阶段流转的决策数据契约。

    定义 DecisionFrame 的最小接口，不依赖任何外部库。
    Engine 层的 polars DataFrame 实现满足此 Protocol。
    """

    @property
    def instruments(self) -> Sequence[str]:
        """标的 ID 序列。"""
        ...

    @property
    def signals(self) -> Sequence[str]:
        """信号值序列。"""
        ...

    @property
    def scores(self) -> Sequence[float]:
        """评分序列。"""
        ...
