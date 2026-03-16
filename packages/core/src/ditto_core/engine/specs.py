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


GRAIN_TO_TIME_KEYS: dict[GrainId, tuple[str, ...]] = {
    "1d": ("trade_date",),
    "1m": ("trade_date", "bar_time"),
}

CALENDAR_TO_TIMEZONE: dict[CalendarId, str] = {
    "cn_stock": "Asia/Shanghai",
}


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
    pit_required: bool | None = None
    normalization_preset: str | None = None
    operator_versions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Apply role-driven execution defaults."""
        if self.pit_required is None:
            object.__setattr__(self, "pit_required", self.role == DerivedRole.FACTOR)
        if self.normalization_preset is None:
            default_preset = "default" if self.role == DerivedRole.FACTOR else "none"
            object.__setattr__(self, "normalization_preset", default_preset)

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

        if self.normalization_preset not in {
            "default",
            "fundamental",
            "institutional",
            "none",
        }:
            raise ValueError(
                "normalization_preset must be one of "
                + "{'default', 'fundamental', 'institutional', 'none'}"
            )
