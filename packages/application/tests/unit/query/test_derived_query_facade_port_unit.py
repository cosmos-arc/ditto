"""Unit tests for the unified derived query facade."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.derived import (
    DerivedQueryFacade,
    LatestDerivedRequest,
    SeriesDerivedRequest,
    SourceCompareRequest,
)
from ditto_features.services.derived import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedSeriesQuery,
    DerivedSourceScope,
)
from pytest_mock import MockerFixture


class TestDerivedQueryFacade:
    """Tests for DerivedQueryFacade."""

    def test_get_latest_maps_to_serving_scope(self, mocker: MockerFixture) -> None:
        """Latest requests should map to serving scope."""
        service = mocker.Mock()
        expected_df = pl.DataFrame({"derived_id": ["factor.momentum_20d"]})
        service.find_latest.return_value = expected_df
        facade = DerivedQueryFacade(service=service)
        request = LatestDerivedRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1, 2),
            as_of=date(2026, 3, 13),
            version=3,
        )

        result = facade.get_latest(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        assert result.data.height == 1
        service.find_latest.assert_called_once_with(
            DerivedLatestQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1, 2),
                as_of="2026-03-13",
                version=3,
                source_scope=DerivedSourceScope.SERVING,
            )
        )
        assert isinstance(result.data, pl.DataFrame)

    def test_get_series_maps_to_offline_scope(self, mocker: MockerFixture) -> None:
        """Series requests should default to offline scope."""
        service = mocker.Mock()
        expected_df = pl.DataFrame({"derived_id": ["factor.momentum_20d"]})
        service.find_series.return_value = expected_df
        facade = DerivedQueryFacade(service=service)
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
        assert result.data.height == 1
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
        assert isinstance(result.data, pl.DataFrame)

    def test_compare_sources_fixes_serving_offline_pair(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Compare requests map to serving/offline pair."""
        service = mocker.Mock()
        expected_df = pl.DataFrame({"derived_id": ["factor.momentum_20d"]})
        service.compare_sources.return_value = expected_df
        facade = DerivedQueryFacade(service=service)
        request = SourceCompareRequest(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start=date(2026, 3, 1),
            end=date(2026, 3, 13),
            version=5,
        )

        result = facade.compare_sources(request)

        assert result.data.to_dicts() == expected_df.to_dicts()
        assert result.data.height == 1
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
        assert isinstance(result.data, pl.DataFrame)

    def test_compare_request_rejects_research_dataset_arguments(self) -> None:
        """Compare requests should not accept research dataset semantics."""
        with pytest.raises(TypeError) as exc_info:
            SourceCompareRequest(
                **{
                    "derived_ids": ("factor.momentum_20d",),
                    "instrument_ids": (1,),
                    "start": date(2026, 3, 1),
                    "end": date(2026, 3, 13),
                    "dataset_snapshot_id": "snapshot-001",
                }
            )
        assert "dataset_snapshot_id" in str(exc_info.value)


class TestLatestDerivedRequestValidation:
    """Tests for LatestDerivedRequest validation."""

    def test_rejects_empty_derived_ids(self) -> None:
        """Empty derived_ids should raise ValueError."""
        with pytest.raises(
            AppQueryError, match="derived_ids must not be empty"
        ) as exc_info:
            LatestDerivedRequest(
                derived_ids=(),
                instrument_ids=(1,),
                as_of=date(2026, 3, 13),
            )
        assert "derived_ids" in str(exc_info.value)

    def test_rejects_zero_version(self) -> None:
        """Zero version should raise ValueError."""
        with pytest.raises(
            AppQueryError, match="version must be greater than 0"
        ) as exc_info:
            LatestDerivedRequest(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                as_of=date(2026, 3, 13),
                version=0,
            )
        assert "version" in str(exc_info.value)


class TestSeriesDerivedRequestValidation:
    """Tests for SeriesDerivedRequest validation."""

    def test_rejects_inverted_range(self) -> None:
        """start > end should raise ValueError."""
        with pytest.raises(
            AppQueryError, match="start must not be greater than end"
        ) as exc_info:
            SeriesDerivedRequest(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                start=date(2026, 3, 13),
                end=date(2026, 3, 1),
                as_of=date(2026, 3, 15),
            )
        assert "start" in str(exc_info.value)

    def test_rejects_zero_limit(self) -> None:
        """Zero limit should raise ValueError."""
        with pytest.raises(
            AppQueryError, match="limit must be greater than 0"
        ) as exc_info:
            SeriesDerivedRequest(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                start=date(2026, 3, 1),
                end=date(2026, 3, 13),
                as_of=date(2026, 3, 15),
                limit=0,
            )
        assert "limit" in str(exc_info.value)
