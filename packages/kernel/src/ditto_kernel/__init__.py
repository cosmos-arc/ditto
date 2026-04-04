"""
Ditto 共享内核 — 跨层领域原语 + Protocol 抽象 + 薄实现.

提供跨层共享的纯类型定义（枚举、NewType、值对象）和系统级 Protocol 抽象。
零业务行为、零外部依赖、零 I/O。

准入标准（详见 packages/kernel/CLAUDE.md）：
- 值对象：枚举 / NewType / 值对象（5 条准入标准）
- Protocol / 薄实现：接口契约 + 系统级基础设施（5 条准入标准）
"""

__version__ = "0.2.0"

from ditto_kernel.clock import Clock, RealtimeClock, SimulatedClock
from ditto_kernel.enums import AssetClass, Exchange, OrderSide, RiskScope, RunStatus
from ditto_kernel.events import DomainEvent, EventBus, SimpleEventBus
from ditto_kernel.identity import InstrumentId
from ditto_kernel.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_kernel.specs import (
    CALENDAR_TO_TIMEZONE,
    GRAIN_TO_TIME_KEYS,
    CalendarId,
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    GrainId,
    MaterializationProfile,
    TimeSpec,
)

__all__ = [
    "CALENDAR_TO_TIMEZONE",
    "GRAIN_TO_TIME_KEYS",
    "AssetClass",
    "CalendarId",
    "Clock",
    "DerivedRole",
    "DerivedSpec",
    "DomainEvent",
    "EventBus",
    "Exchange",
    "ExecutionPolicy",
    "GrainId",
    "InstrumentId",
    "MaterializationProfile",
    "OrderSide",
    "RealtimeClock",
    "ResearchDatasetSnapshotRecord",
    "ResearchDatasetSpecRecord",
    "ResearchSpineSnapshotRecord",
    "ResearchSpineSpecRecord",
    "RiskScope",
    "RunStatus",
    "SimpleEventBus",
    "SimulatedClock",
    "TimeSpec",
]
