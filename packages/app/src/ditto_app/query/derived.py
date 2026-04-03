"""App facade for unified derived query use cases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

import polars as pl
from ditto_data.services import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedQueryService,
    DerivedSeriesQuery,
    DerivedSourceScope,
)
from ditto_data.services.hot_layer import HotLayerReader
from loguru import logger

type TemporalValue = date | datetime

# ---------------------------------------------------------------------------
# Request / Response models (formerly ditto_interfaces.models.derived)
# ---------------------------------------------------------------------------

__all__ = [
    "DerivedCompareResult",
    "DerivedLatestResult",
    "DerivedQueryFacade",
    "DerivedSeriesResult",
    "LatestDerivedRequest",
    "RuntimeMode",
    "RuntimeModeResolver",
    "SeriesDerivedRequest",
    "SourceCompareRequest",
    "StaticRuntimeModeResolver",
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


# ---------------------------------------------------------------------------
# Runtime mode
# ---------------------------------------------------------------------------


class RuntimeMode(StrEnum):
    """Runtime modes reserved for Phase 3 routing decisions."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


class RuntimeModeResolver(Protocol):
    """Resolve the current runtime mode without exposing it publicly."""

    def resolve(self) -> RuntimeMode:
        """Return the current runtime mode."""
        ...


@dataclass(frozen=True)
class StaticRuntimeModeResolver:
    """Static runtime mode resolver used by the DI container."""

    mode: RuntimeMode = RuntimeMode.OFFLINE

    def resolve(self) -> RuntimeMode:
        """Return the configured runtime mode."""
        return self.mode


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


def _temporal_to_iso(value: TemporalValue | None) -> str | None:
    """Serialize date/datetime values for Data DTOs."""
    if value is None:
        return None
    return value.isoformat()


class DerivedQueryFacade:
    """Use-case facade for unified derived query entrypoints."""

    def __init__(
        self,
        service: DerivedQueryService,
        mode_resolver: RuntimeModeResolver,
        hot_layer: HotLayerReader,
    ) -> None:
        self._service = service
        self._mode_resolver = mode_resolver
        self._hot_layer = hot_layer

    def get_latest(self, request: LatestDerivedRequest) -> DerivedLatestResult:
        """
        Map latest requests to the serving contract.

        In ONLINE mode with a single derived_id, attempts to serve from
        the hot layer (QuestDB) first. Falls back to the cold layer on
        unavailability, empty results, or any exception.
        """
        mode = self._mode_resolver.resolve()

        # Try hot layer when in ONLINE mode with a single derived_id
        if (
            mode == RuntimeMode.ONLINE
            and len(request.derived_ids) == 1
            and self._hot_layer.is_available()
        ):
            try:
                data = self._hot_layer.read_latest(
                    derived_id=request.derived_ids[0],
                    instrument_ids=request.instrument_ids,
                    as_of=_temporal_to_iso(request.as_of),
                )
                if not data.is_empty():
                    return DerivedLatestResult(data=data)
            except Exception:
                logger.warning(
                    "Hot layer read failed, falling back to cold layer",
                    derived_id=request.derived_ids[0],
                    exc_info=True,
                )

        # Cold layer (existing code)
        query = DerivedLatestQuery(
            derived_ids=request.derived_ids,
            instrument_ids=request.instrument_ids,
            as_of=_temporal_to_iso(request.as_of),
            version=request.version,
            source_scope=DerivedSourceScope.SERVING,
        )
        return DerivedLatestResult(data=self._service.find_latest(query))

    def get_series(self, request: SeriesDerivedRequest) -> DerivedSeriesResult:
        """Map series requests to the offline contract."""
        query = DerivedSeriesQuery(
            derived_ids=request.derived_ids,
            instrument_ids=request.instrument_ids,
            start=_temporal_to_iso(request.start),
            end=_temporal_to_iso(request.end),
            as_of=_temporal_to_iso(request.as_of),
            version=request.version,
            source_scope=DerivedSourceScope.OFFLINE,
            limit=request.limit,
        )
        return DerivedSeriesResult(data=self._service.find_series(query))

    def compare_sources(
        self,
        request: SourceCompareRequest,
    ) -> DerivedCompareResult:
        """Compare serving and offline slices without research semantics."""
        query = DerivedCompareQuery(
            derived_ids=request.derived_ids,
            instrument_ids=request.instrument_ids,
            start=_temporal_to_iso(request.start) or "",
            end=_temporal_to_iso(request.end) or "",
            version=request.version,
            compare_sources=(
                DerivedSourceScope.SERVING,
                DerivedSourceScope.OFFLINE,
            ),
        )
        return DerivedCompareResult(data=self._service.compare_sources(query))
