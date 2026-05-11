"""
Ditto 共享内核 — 跨层领域原语 + Protocol 抽象 + 薄实现.

提供跨层共享的纯类型定义（枚举、NewType、值对象）和系统级 Protocol 抽象。
零业务行为、零外部依赖、零 I/O。
"""

from ditto_kernel.clock import Clock, RealtimeClock, SimulatedClock
from ditto_kernel.events import DomainEvent, EventBus, EventName, SimpleEventBus
from ditto_kernel.exceptions import (
    AmbiguousTickerError,
    DittoError,
    IdentifierError,
    NoIdentifierProvidedError,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.instrument import AssetClass, Exchange, InstrumentIngestParams
from ditto_kernel.market import (
    MacroCategory,
    MacroFrequency,
    TimeSpec,
)
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.strategy import (
    ExecutionPolicy,
    ImpactModel,
    RiskScope,
)
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
from ditto_kernel.time_context import TimeContext
from ditto_kernel.tracing import traced
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)

__all__ = [
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
    "AmbiguousTickerError",
    "AssetClass",
    "Clock",
    "DittoError",
    "DomainEvent",
    "EventBus",
    "EventName",
    "Exchange",
    "ExecutionPolicy",
    "IdentifierError",
    "ImpactModel",
    "InstrumentId",
    "InstrumentIngestParams",
    "MacroCategory",
    "MacroFrequency",
    "NoIdentifierProvidedError",
    "OrderSide",
    "OrderType",
    "RealtimeClock",
    "RiskScope",
    "SimpleEventBus",
    "SimulatedClock",
    "Synchronizer",
    "TimeContext",
    "TimeSlice",
    "TimeSpec",
    "traced",
]
