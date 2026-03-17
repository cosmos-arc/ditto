"""Unified derived semantic spec models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

type CalendarId = Literal["cn_stock"]
type GrainId = Literal["1d", "1m"]

__all__ = [
    "CALENDAR_TO_TIMEZONE",
    "GRAIN_TO_TIME_KEYS",
    "CalendarId",
    "DerivedRole",
    "DerivedSpec",
    "ExecutionPolicy",
    "GrainId",
    "MaterializationProfile",
    "TimeSpec",
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


GRAIN_TO_TIME_KEYS: dict[GrainId, tuple[str, ...]] = {
    "1d": ("trade_date",),
    "1m": ("trade_date", "bar_time"),
}

CALENDAR_TO_TIMEZONE: dict[CalendarId, str] = {
    "cn_stock": "Asia/Shanghai",
}


@dataclass(frozen=True)
class TimeSpec:
    """时间语义规范"""

    event_time_key: str
    availability_time_key: str | None = None


@dataclass(frozen=True)
class ExecutionPolicy:
    """执行策略配置"""

    pit_required: bool = True
    normalization_preset: str = "default"


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

    @property
    def effective_time_keys(self) -> tuple[str, ...]:
        """Return explicit time keys or the grain-derived default."""
        return self.time_keys or GRAIN_TO_TIME_KEYS[self.grain]

    @property
    def timezone(self) -> str:
        """Return timezone implied by the calendar."""
        return CALENDAR_TO_TIMEZONE[self.calendar]

    def validate_spec(self) -> None:
        """Validate current v1 boundaries."""
        if len(self.entity_keys) != 1:
            raise NotImplementedError(
                f"复合键已预留、暂未实现: entity_keys={self.entity_keys}"
            )

        if self.grain == "1m":
            raise NotImplementedError("grain='1m' 已预留、暂未实现")
