"""Tests for DerivedQueryFacade — 封装 DerivedQueryService 查询委托."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
from ditto_application.queries.derived import (
    DerivedCompareResult,
    DerivedLatestResult,
    DerivedQueryFacade,
    DerivedSeriesResult,
    LatestDerivedRequest,
    SeriesDerivedRequest,
    SourceCompareRequest,
)
from ditto_features.services.derived import DerivedSourceScope


class TestDerivedQueryFacadeGetLatest:
    """DerivedQueryFacade.get_latest — 委托到 DerivedQueryService.find_latest."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["find_latest"])
        service.find_latest.return_value = pl.DataFrame({"value": [42.0]})

        facade = DerivedQueryFacade(service=service)
        request = LatestDerivedRequest(
            derived_ids=("test_derived",),
            instrument_ids=(1, 2),
        )
        result = facade.get_latest(request)

        assert isinstance(result, DerivedLatestResult)
        assert len(result.data) == 1
        service.find_latest.assert_called_once()


class TestDerivedQueryFacadeGetSeries:
    """DerivedQueryFacade.get_series — 纯委托到 DerivedQueryService.find_series."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["find_series"])
        service.find_series.return_value = pl.DataFrame({"value": [1.0, 2.0]})

        facade = DerivedQueryFacade(service=service)
        request = SeriesDerivedRequest(
            derived_ids=("alpha",),
            instrument_ids=(10,),
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
        )
        result = facade.get_series(request)

        assert isinstance(result, DerivedSeriesResult)
        assert len(result.data) == 2
        service.find_series.assert_called_once()
        call_args = service.find_series.call_args[0][0]
        assert call_args.derived_ids == ("alpha",)
        assert call_args.instrument_ids == (10,)
        assert call_args.start == "2024-01-01"
        assert call_args.end == "2024-01-31"
        assert call_args.source_scope == DerivedSourceScope.OFFLINE


class TestDerivedQueryFacadeCompareSources:
    """DerivedQueryFacade.compare_sources — 委托到 DerivedQueryService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["compare_sources"])
        service.compare_sources.return_value = pl.DataFrame({"diff": [0.1]})

        facade = DerivedQueryFacade(service=service)
        request = SourceCompareRequest(
            derived_ids=("beta",),
            instrument_ids=(5,),
            start=date(2024, 3, 1),
            end=date(2024, 3, 31),
        )
        result = facade.compare_sources(request)

        assert isinstance(result, DerivedCompareResult)
        assert len(result.data) == 1
        service.compare_sources.assert_called_once()
        call_args = service.compare_sources.call_args[0][0]
        assert call_args.derived_ids == ("beta",)
        assert call_args.instrument_ids == (5,)
        assert call_args.start == "2024-03-01"
        assert call_args.end == "2024-03-31"
        assert call_args.compare_sources == (
            DerivedSourceScope.SERVING,
            DerivedSourceScope.OFFLINE,
        )
