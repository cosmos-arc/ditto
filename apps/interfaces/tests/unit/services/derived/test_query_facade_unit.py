"""Unit tests for the unified derived query facade."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_app.query.derived import (
    DerivedQueryFacade,
    LatestDerivedRequest,
    RuntimeMode,
    SeriesDerivedRequest,
    SourceCompareRequest,
)
from ditto_datahub.services import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedSeriesQuery,
    DerivedSourceScope,
)
from ditto_datahub.services.hot_layer import (
    UnavailableHotLayerReader,
)
from pytest_mock import MockerFixture

_HOT_LAYER = UnavailableHotLayerReader()


class TestDerivedQueryFacade:
    """Tests for DerivedQueryFacade."""

    def test_get_latest_maps_to_serving_scope(self, mocker: MockerFixture) -> None:
        """Latest requests should map to serving scope without exposing runtime_mode."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.ONLINE
        expected_df = pl.DataFrame({"derived_id": ["factor.momentum_20d"]})
        service.find_latest.return_value = expected_df
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=_HOT_LAYER,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1, 2),
            as_of=date(2026, 3, 13),
            version=3,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        assert not hasattr(request, "runtime_mode")
        resolver.resolve.assert_called_once_with()
        service.find_latest.assert_called_once_with(
            DerivedLatestQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1, 2),
                as_of="2026-03-13",
                version=3,
                source_scope=DerivedSourceScope.SERVING,
            )
        )

    def test_get_series_maps_to_offline_scope(self, mocker: MockerFixture) -> None:
        """Series requests should default to offline scope without resolving mode."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        expected_df = pl.DataFrame({"derived_id": ["factor.momentum_20d"]})
        service.find_series.return_value = expected_df
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=_HOT_LAYER,
        )
        request = SeriesDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start=date(2026, 3, 1),
            end=date(2026, 3, 13),
            as_of=date(2026, 3, 13),
            version=4,
            limit=200,
        )

        result = facade.get_series(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        resolver.resolve.assert_not_called()
        service.find_series.assert_called_once_with(
            DerivedSeriesQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                start="2026-03-01",
                end="2026-03-13",
                as_of="2026-03-13",
                version=4,
                source_scope=DerivedSourceScope.OFFLINE,
                limit=200,
            )
        )

    def test_compare_sources_fixes_serving_offline_pair(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Compare requests map to serving/offline pair without resolving mode."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        expected_df = pl.DataFrame({"derived_id": ["factor.momentum_20d"]})
        service.compare_sources.return_value = expected_df
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=_HOT_LAYER,
        )
        request = SourceCompareRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start=date(2026, 3, 1),
            end=date(2026, 3, 13),
            version=5,
        )

        result = facade.compare_sources(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        resolver.resolve.assert_not_called()
        service.compare_sources.assert_called_once_with(
            DerivedCompareQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                start="2026-03-01",
                end="2026-03-13",
                version=5,
                compare_sources=(
                    DerivedSourceScope.SERVING,
                    DerivedSourceScope.OFFLINE,
                ),
            )
        )

    def test_compare_request_rejects_research_dataset_arguments(self) -> None:
        """Compare requests should not accept research dataset semantics."""
        with pytest.raises(TypeError):
            SourceCompareRequest(
                **{
                    "derived_ids": ("factor.momentum_20d",),
                    "instrument_ids": (1,),
                    "start": date(2026, 3, 1),
                    "end": date(2026, 3, 13),
                    "dataset_snapshot_id": "snapshot-001",
                }
            )


class TestDerivedQueryFacadeHotLayerIntegration:
    """Tests for hot layer integration in DerivedQueryFacade.get_latest()."""

    def test_online_mode_with_unavailable_hot_layer_falls_back_to_cold(
        self,
        mocker: MockerFixture,
    ) -> None:
        """ONLINE mode with unavailable hot layer should fall back to cold layer."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.ONLINE
        expected_df = pl.DataFrame(
            {"derived_id": ["factor.momentum_20d"], "value": [1.0]},
        )
        service.find_latest.return_value = expected_df
        hot_layer = UnavailableHotLayerReader()
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            as_of=None,
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        # Hot layer was checked but unavailable, so cold layer was used
        assert hot_layer.is_available() is False
        service.find_latest.assert_called_once()

    def test_offline_mode_skips_hot_layer(
        self,
        mocker: MockerFixture,
    ) -> None:
        """OFFLINE mode should skip hot layer entirely."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.OFFLINE
        expected_df = pl.DataFrame(
            {"derived_id": ["factor.momentum_20d"], "value": [2.0]},
        )
        service.find_latest.return_value = expected_df
        hot_layer = mocker.Mock()
        hot_layer.is_available.return_value = True
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            as_of=None,
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        # Hot layer should NOT be checked in OFFLINE mode
        hot_layer.is_available.assert_not_called()
        service.find_latest.assert_called_once()

    def test_degraded_mode_skips_hot_layer(
        self,
        mocker: MockerFixture,
    ) -> None:
        """DEGRADED mode should skip hot layer entirely."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.DEGRADED
        expected_df = pl.DataFrame(
            {"derived_id": ["factor.momentum_20d"], "value": [3.0]},
        )
        service.find_latest.return_value = expected_df
        hot_layer = mocker.Mock()
        hot_layer.is_available.return_value = True
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            as_of=None,
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        # Hot layer should NOT be checked in DEGRADED mode
        hot_layer.is_available.assert_not_called()
        service.find_latest.assert_called_once()

    def test_online_mode_with_available_hot_layer_returns_hot_data(
        self,
        mocker: MockerFixture,
    ) -> None:
        """ONLINE mode with available hot layer returning data should skip cold."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.ONLINE
        hot_df = pl.DataFrame(
            {"derived_id": ["factor.momentum_20d"], "value": [42.0]},
        )
        hot_layer = mocker.Mock()
        hot_layer.is_available.return_value = True
        hot_layer.read_latest.return_value = hot_df
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1, 2),
            as_of=date(2026, 3, 13),
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == hot_df.to_dicts()
        # Cold layer should NOT be called
        service.find_latest.assert_not_called()
        hot_layer.is_available.assert_called_once()
        hot_layer.read_latest.assert_called_once_with(
            derived_id="factor.momentum_20d",
            instrument_ids=(1, 2),
            as_of="2026-03-13",
        )

    def test_online_mode_with_hot_layer_exception_falls_back(
        self,
        mocker: MockerFixture,
    ) -> None:
        """ONLINE mode with hot layer exception should fall back to cold layer."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.ONLINE
        expected_df = pl.DataFrame(
            {"derived_id": ["factor.momentum_20d"], "value": [99.0]},
        )
        service.find_latest.return_value = expected_df
        hot_layer = mocker.Mock()
        hot_layer.is_available.return_value = True
        hot_layer.read_latest.side_effect = RuntimeError("QuestDB connection failed")
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            as_of=None,
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        # Cold layer should be used as fallback
        service.find_latest.assert_called_once()

    def test_online_mode_with_empty_hot_result_falls_back(
        self,
        mocker: MockerFixture,
    ) -> None:
        """ONLINE mode with empty hot layer result should fall back to cold layer."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.ONLINE
        expected_df = pl.DataFrame(
            {"derived_id": ["factor.momentum_20d"], "value": [7.0]},
        )
        service.find_latest.return_value = expected_df
        hot_layer = mocker.Mock()
        hot_layer.is_available.return_value = True
        hot_layer.read_latest.return_value = pl.DataFrame()
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            as_of=None,
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        # Cold layer should be used when hot returns empty
        service.find_latest.assert_called_once()

    def test_multiple_derived_ids_skips_hot_layer(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Multiple derived_ids should skip hot layer (singular protocol)."""
        service = mocker.Mock()
        resolver = mocker.Mock()
        resolver.resolve.return_value = RuntimeMode.ONLINE
        expected_df = pl.DataFrame(
            {"derived_id": ["factor.a", "factor.b"], "value": [1.0, 2.0]},
        )
        service.find_latest.return_value = expected_df
        hot_layer = mocker.Mock()
        hot_layer.is_available.return_value = True
        facade = DerivedQueryFacade(
            service=service,
            mode_resolver=resolver,
            hot_layer=hot_layer,
        )
        request = LatestDerivedRequest(
            derived_ids=("factor.a", "factor.b"),
            instrument_ids=(1,),
            as_of=None,
            version=None,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        # Hot layer should NOT be called for multi-id requests
        hot_layer.is_available.assert_not_called()
        service.find_latest.assert_called_once()
