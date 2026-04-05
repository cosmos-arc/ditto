"""Tests for DerivedQueryFacade — 封装 DerivedQueryService + 热层路由."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
from ditto_app.query.derived import (
    DerivedCompareResult,
    DerivedLatestResult,
    DerivedQueryFacade,
    DerivedSeriesResult,
    LatestDerivedRequest,
    RuntimeMode,
    SeriesDerivedRequest,
    SourceCompareRequest,
    StaticRuntimeModeResolver,
)
from ditto_data.services import DerivedSourceScope


class TestDerivedQueryFacadeGetLatestColdLayer:
    """DerivedQueryFacade.get_latest — OFFLINE 模式直接走 cold layer."""

    def test_delegates_to_service_without_hot_layer(self) -> None:
        service = MagicMock(spec=["find_latest"])
        service.find_latest.return_value = pl.DataFrame({"value": [42.0]})
        mode_resolver = StaticRuntimeModeResolver(mode=RuntimeMode.OFFLINE)
        hot_layer = MagicMock(spec=["is_available", "read_latest"])

        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=mode_resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("test_derived",),
            instrument_ids=(1, 2),
        )
        result = facade.get_latest(request)

        assert isinstance(result, DerivedLatestResult)
        assert len(result.data) == 1
        service.find_latest.assert_called_once()
        hot_layer.is_available.assert_not_called()


class TestDerivedQueryFacadeGetLatestHotLayerHit:
    """DerivedQueryFacade.get_latest — ONLINE + hot layer 命中."""

    def test_returns_hot_layer_data(self) -> None:
        hot_df = pl.DataFrame({"value": [99.0]})
        service = MagicMock(spec=["find_latest"])
        mode_resolver = StaticRuntimeModeResolver(mode=RuntimeMode.ONLINE)
        hot_layer = MagicMock(spec=["is_available", "read_latest"])
        hot_layer.is_available.return_value = True
        hot_layer.read_latest.return_value = hot_df

        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=mode_resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("test_derived",),
            instrument_ids=(1,),
            as_of=date(2024, 6, 1),
        )
        result = facade.get_latest(request)

        assert isinstance(result, DerivedLatestResult)
        assert result.data["value"][0] == 99.0
        hot_layer.read_latest.assert_called_once_with(
            derived_id="test_derived",
            instrument_ids=(1,),
            as_of="2024-06-01",
        )
        service.find_latest.assert_not_called()


class TestDerivedQueryFacadeGetLatestHotLayerFallback:
    """DerivedQueryFacade.get_latest — ONLINE + hot layer 异常降级到 cold layer."""

    def test_falls_back_to_cold_layer_on_hot_layer_error(self) -> None:
        service = MagicMock(spec=["find_latest"])
        service.find_latest.return_value = pl.DataFrame({"value": [55.0]})
        mode_resolver = StaticRuntimeModeResolver(mode=RuntimeMode.ONLINE)
        hot_layer = MagicMock(spec=["is_available", "read_latest"])
        hot_layer.is_available.return_value = True
        hot_layer.read_latest.side_effect = RuntimeError("QuestDB unreachable")

        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=mode_resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("test_derived",),
            instrument_ids=(1,),
        )
        result = facade.get_latest(request)

        assert isinstance(result, DerivedLatestResult)
        assert result.data["value"][0] == 55.0
        service.find_latest.assert_called_once()


class TestDerivedQueryFacadeGetSeries:
    """DerivedQueryFacade.get_series — 纯委托到 DerivedQueryService.find_series."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["find_series"])
        service.find_series.return_value = pl.DataFrame({"value": [1.0, 2.0]})
        mode_resolver = StaticRuntimeModeResolver(mode=RuntimeMode.OFFLINE)
        hot_layer = MagicMock(spec=["is_available", "read_latest"])

        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=mode_resolver,
            hot_layer=hot_layer,
        )
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
        mode_resolver = StaticRuntimeModeResolver(mode=RuntimeMode.OFFLINE)
        hot_layer = MagicMock(spec=["is_available", "read_latest"])

        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=mode_resolver,
            hot_layer=hot_layer,
        )
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
