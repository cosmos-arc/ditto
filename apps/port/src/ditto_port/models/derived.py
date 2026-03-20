"""Port-side request and result models for unified derived queries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import polars as pl

type TemporalValue = date | datetime

__all__ = [
    "DerivedCompareResult",
    "DerivedLatestResult",
    "DerivedSeriesResult",
    "LatestDerivedRequest",
    "SeriesDerivedRequest",
    "SourceCompareRequest",
]


def _coerce_str_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    """Convert request string sequences to tuples."""
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not item for item in normalized):
        raise ValueError(f"{field_name} must not contain empty values")
    return normalized


def _coerce_int_tuple(values: Sequence[int], field_name: str) -> tuple[int, ...]:
    """Convert request int sequences to tuples."""
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_version(version: int | None) -> None:
    """Validate optional positive version."""
    if version is not None and version <= 0:
        raise ValueError("version must be greater than 0")


def _validate_limit(limit: int | None) -> None:
    """Validate optional positive limit."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than 0")


def _validate_range(
    start: TemporalValue | None,
    end: TemporalValue | None,
) -> None:
    """Validate an optional start/end range."""
    if start is not None and end is not None and start > end:
        raise ValueError("start must not be greater than end")


@dataclass(frozen=True)
class LatestDerivedRequest:
    """Latest query request for unified derived data."""

    derived_ids: tuple[str, ...]
    instrument_ids: tuple[int, ...]
    as_of: TemporalValue | None = None
    version: int | None = None

    def __post_init__(self) -> None:
        """Normalize request collections and validate version constraints."""
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
        _validate_version(self.version)


@dataclass(frozen=True)
class SeriesDerivedRequest:
    """Series query request for unified derived data."""

    derived_ids: tuple[str, ...]
    instrument_ids: tuple[int, ...] | None = None
    start: TemporalValue | None = None
    end: TemporalValue | None = None
    as_of: TemporalValue | None = None
    version: int | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        """Normalize request collections and validate range constraints."""
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
        _validate_range(self.start, self.end)
        _validate_version(self.version)
        _validate_limit(self.limit)


@dataclass(frozen=True)
class SourceCompareRequest:
    """Compare request for serving/offline slices."""

    derived_ids: tuple[str, ...]
    instrument_ids: tuple[int, ...]
    start: TemporalValue
    end: TemporalValue
    version: int | None = None

    def __post_init__(self) -> None:
        """Normalize request collections and validate compare boundaries."""
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
        _validate_range(self.start, self.end)
        _validate_version(self.version)


@dataclass(frozen=True)
class DerivedLatestResult:
    """Latest query result wrapper."""

    data: pl.DataFrame


@dataclass(frozen=True)
class DerivedSeriesResult:
    """Series query result wrapper."""

    data: pl.DataFrame


@dataclass(frozen=True)
class DerivedCompareResult:
    """Compare query result wrapper."""

    data: pl.DataFrame
