"""
Ditto 共享内核 — 跨层领域原语 + Protocol 抽象 + 薄实现.

提供跨层共享的纯类型定义（枚举、NewType、值对象）和系统级 Protocol 抽象。
零业务行为、零外部依赖、零 I/O。
"""

from ditto_kernel._version import __version__ as __version__
from ditto_kernel.clock import Clock, RealtimeClock, SimulatedClock
from ditto_kernel.events import DomainEvent, EventBus, SimpleEventBus
from ditto_kernel.exceptions import (
    AmbiguousTickerError,
    DataError,
    DittoError,
    IdentifierError,
    NoIdentifierProvidedError,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.instrument import AssetClass, Exchange, InstrumentIngestParams
from ditto_kernel.market import (
    CALENDAR_TO_TIMEZONE,
    GRAIN_TO_TIME_KEYS,
    CalendarId,
    GrainId,
    MacroDataProvider,
    MacroFrequency,
    TimeSpec,
)
from ditto_kernel.order import OrderSide
from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity
from ditto_kernel.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_kernel.strategy import (
    DecisionFrame,
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    ImpactModel,
    MaterializationProfile,
    RiskScope,
    RunStatus,
)

__all__ = [
    "CALENDAR_TO_TIMEZONE",
    "GRAIN_TO_TIME_KEYS",
    "AmbiguousTickerError",
    "AssetClass",
    "CalendarId",
    "Clock",
    "DQIssue",
    "DQLevel",
    "DQResult",
    "DQSeverity",
    "DataError",
    "DecisionFrame",
    "DerivedRole",
    "DerivedSpec",
    "DittoError",
    "DomainEvent",
    "EventBus",
    "Exchange",
    "ExecutionPolicy",
    "GrainId",
    "IdentifierError",
    "ImpactModel",
    "InstrumentId",
    "InstrumentIngestParams",
    "MacroDataProvider",
    "MacroFrequency",
    "MaterializationProfile",
    "NoIdentifierProvidedError",
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
    "__version__",
]
