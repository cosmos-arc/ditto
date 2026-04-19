"""Strategy subdomain — 策略规格、执行策略、衍生语义。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ditto_kernel.market import (
    CALENDAR_TO_TIMEZONE,
    GRAIN_TO_TIME_KEYS,
    CalendarId,
    GrainId,
    TimeSpec,
)

__all__ = [
    "DecisionFrame",
    "DerivedRole",
    "DerivedSpec",
    "ExecutionPolicy",
    "ImpactModel",
    "MaterializationProfile",
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


class DerivedRole(StrEnum):
    """Derived entity role。"""

    FEATURE = "feature"
    FACTOR = "factor"
    SIGNAL = "signal"
    LABEL = "label"


class MaterializationProfile(StrEnum):
    """Derived materialization profile。"""

    SERIES = "SERIES"
    STATE = "STATE"
    DERIVE = "DERIVE"
    OFFLINE = "OFFLINE"


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


@dataclass(frozen=True)
class DerivedSpec:
    """Unified derived semantic contract。"""

    id: str
    version: int
    role: DerivedRole
    materialization_profile: MaterializationProfile
    expression: str
    entity_keys: tuple[str, ...] = field(default_factory=lambda: ("instrument_id",))
    grain: GrainId = "1d"
    time_keys: tuple[str, ...] | None = None
    calendar: CalendarId = "cn_stock"
    description: str | None = None
    time_spec: TimeSpec | None = None
    operator_versions: dict[str, str] = field(default_factory=dict)
    universe_id: str | None = None
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)

    @property
    def effective_time_keys(self) -> tuple[str, ...]:
        """Return explicit time keys or the grain-derived default。"""
        return self.time_keys or GRAIN_TO_TIME_KEYS[self.grain]

    @property
    def timezone(self) -> str:
        """Return timezone implied by the calendar。"""
        return CALENDAR_TO_TIMEZONE[self.calendar]


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
