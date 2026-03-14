"""Port facade for unified derived query use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from ditto_datahub.services import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedQueryService,
    DerivedSeriesQuery,
    DerivedSourceScope,
)

from ditto_port.models.derived import (
    DerivedCompareResult,
    DerivedLatestResult,
    DerivedSeriesResult,
    LatestDerivedRequest,
    SeriesDerivedRequest,
    SourceCompareRequest,
)

type TemporalValue = date | datetime

__all__ = [
    "DerivedQueryFacade",
    "RuntimeMode",
    "RuntimeModeResolver",
    "StaticRuntimeModeResolver",
]


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


def _temporal_to_iso(value: TemporalValue | None) -> str | None:
    """Serialize date/datetime values for DataHub DTOs."""
    if value is None:
        return None
    return value.isoformat()


class DerivedQueryFacade:
    """Use-case facade for unified derived query entrypoints."""

    def __init__(
        self,
        service: DerivedQueryService,
        mode_resolver: RuntimeModeResolver,
    ) -> None:
        self._service = service
        self._mode_resolver = mode_resolver

    def get_latest(self, request: LatestDerivedRequest) -> DerivedLatestResult:
        """Map latest requests to the serving contract."""
        # Phase 2 only freezes the seam; Phase 3 will consume the resolved mode.
        _ = self._mode_resolver.resolve()
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
        _ = self._mode_resolver.resolve()
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
        _ = self._mode_resolver.resolve()
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
