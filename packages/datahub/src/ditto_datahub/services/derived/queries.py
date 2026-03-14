"""Query DTOs for unified derived queries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

__all__ = [
    "DerivedCompareQuery",
    "DerivedLatestQuery",
    "DerivedSeriesQuery",
    "DerivedSourceScope",
]

EXPECTED_COMPARE_SOURCE_COUNT = 2


class DerivedSourceScope(StrEnum):
    """Supported query source scopes."""

    SERVING = "serving"
    OFFLINE = "offline"


def _coerce_str_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    """Convert a string sequence to an immutable tuple with validation."""
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not item for item in normalized):
        raise ValueError(f"{field_name} must not contain empty values")
    return normalized


def _coerce_int_tuple(values: Sequence[int], field_name: str) -> tuple[int, ...]:
    """Convert an int sequence to an immutable tuple with validation."""
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_version(version: int | None) -> None:
    """Validate an optional positive version."""
    if version is not None and version <= 0:
        raise ValueError("version must be greater than 0")


def _validate_limit(limit: int | None) -> None:
    """Validate an optional positive limit."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than 0")


def _coerce_source_scope(value: DerivedSourceScope | str) -> DerivedSourceScope:
    """Normalize a single source scope value."""
    if isinstance(value, DerivedSourceScope):
        return value
    try:
        return DerivedSourceScope(value)
    except ValueError as exc:
        raise ValueError(f"unsupported source_scope: {value}") from exc


def _coerce_compare_sources(
    values: Sequence[DerivedSourceScope | str],
) -> tuple[DerivedSourceScope, DerivedSourceScope]:
    """Normalize compare sources to a strict pair."""
    normalized = tuple(_coerce_source_scope(value) for value in values)
    return cast(tuple[DerivedSourceScope, DerivedSourceScope], normalized)


@dataclass(frozen=True)
class DerivedLatestQuery:
    """Query latest values for one or more derived ids."""

    derived_ids: tuple[str, ...]
    instrument_ids: tuple[int, ...]
    as_of: str | None = None
    version: int | None = None
    source_scope: DerivedSourceScope = DerivedSourceScope.SERVING

    def __post_init__(self) -> None:
        """Normalize ids and validate the latest query contract."""
        object.__setattr__(
            self,
            "derived_ids",
            _coerce_str_tuple(self.derived_ids, "derived_ids"),
        )
        object.__setattr__(
            self,
            "instrument_ids",
            _coerce_int_tuple(self.instrument_ids, "instrument_ids"),
        )
        object.__setattr__(
            self,
            "source_scope",
            _coerce_source_scope(self.source_scope),
        )
        _validate_version(self.version)


@dataclass(frozen=True)
class DerivedSeriesQuery:
    """Query time series data for one or more derived ids."""

    derived_ids: tuple[str, ...]
    instrument_ids: tuple[int, ...] | None = None
    start: str | None = None
    end: str | None = None
    as_of: str | None = None
    version: int | None = None
    source_scope: DerivedSourceScope = DerivedSourceScope.OFFLINE
    limit: int | None = None

    def __post_init__(self) -> None:
        """Normalize ids and validate the series query contract."""
        object.__setattr__(
            self,
            "derived_ids",
            _coerce_str_tuple(self.derived_ids, "derived_ids"),
        )
        if self.instrument_ids is not None:
            object.__setattr__(
                self,
                "instrument_ids",
                _coerce_int_tuple(self.instrument_ids, "instrument_ids"),
            )
        object.__setattr__(
            self,
            "source_scope",
            _coerce_source_scope(self.source_scope),
        )
        _validate_version(self.version)
        _validate_limit(self.limit)


@dataclass(frozen=True)
class DerivedCompareQuery:
    """Compare values across serving and offline scopes."""

    derived_ids: tuple[str, ...]
    instrument_ids: tuple[int, ...]
    start: str
    end: str
    version: int | None = None
    compare_sources: tuple[DerivedSourceScope, DerivedSourceScope] = (
        DerivedSourceScope.SERVING,
        DerivedSourceScope.OFFLINE,
    )

    def __post_init__(self) -> None:
        """Normalize ids and validate the compare query contract."""
        object.__setattr__(
            self,
            "derived_ids",
            _coerce_str_tuple(self.derived_ids, "derived_ids"),
        )
        object.__setattr__(
            self,
            "instrument_ids",
            _coerce_int_tuple(self.instrument_ids, "instrument_ids"),
        )
        object.__setattr__(
            self,
            "compare_sources",
            _coerce_compare_sources(self.compare_sources),
        )
        _validate_version(self.version)
        if len(self.compare_sources) != EXPECTED_COMPARE_SOURCE_COUNT:
            raise ValueError("compare_sources must contain exactly two entries")
        if len(set(self.compare_sources)) != EXPECTED_COMPARE_SOURCE_COUNT:
            raise ValueError("compare_sources must contain two distinct scopes")
