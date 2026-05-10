"""Derived entity types — role, materialization profile, and unified spec."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ditto_kernel.market import (
    CALENDAR_TO_TIMEZONE,
    GRAIN_TO_TIME_KEYS,
    CalendarId,
    GrainId,
    TimeSpec,
)
from ditto_kernel.strategy import ExecutionPolicy

__all__ = [
    "DerivedRole",
    "DerivedSpec",
    "MaterializationProfile",
]


class DerivedRole(StrEnum):
    """Derived entity role."""

    FEATURE = "feature"
    FACTOR = "factor"
    SIGNAL = "signal"
    LABEL = "label"


class MaterializationProfile(StrEnum):
    """Derived materialization profile."""

    SERIES = "SERIES"
    STATE = "STATE"
    DERIVE = "DERIVE"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True)
class DerivedSpec:
    """Unified derived semantic contract."""

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
        """Return explicit time keys or the grain-derived default."""
        return self.time_keys or GRAIN_TO_TIME_KEYS[self.grain]

    @property
    def timezone(self) -> str:
        """Return timezone implied by the calendar."""
        return CALENDAR_TO_TIMEZONE[self.calendar]
