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
    MacroCategory,
    MacroDataProvider,
    MacroFrequency,
    TimeSpec,
)
from ditto_kernel.order import OrderSide, OrderType
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
from ditto_kernel.tracing import traced
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)

__all__ = [
    "CALENDAR_TO_TIMEZONE",
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
    "GRAIN_TO_TIME_KEYS",
    "AmbiguousTickerError",
    "AssetClass",
    "Clock",
    "DataError",
    "DecisionFrame",
    "DerivedRole",
    "DerivedSpec",
    "DittoError",
    "DomainEvent",
    "EventBus",
    "Exchange",
    "ExecutionPolicy",
    "IdentifierError",
    "ImpactModel",
    "InstrumentId",
    "InstrumentIngestParams",
    "MacroCategory",
    "MacroDataProvider",
    "MacroFrequency",
    "MaterializationProfile",
    "NoIdentifierProvidedError",
    "OrderSide",
    "OrderType",
    "RealtimeClock",
    "RiskScope",
    "RunStatus",
    "SimpleEventBus",
    "SimulatedClock",
    "TimeSpec",
    "__version__",
    "traced",
]
