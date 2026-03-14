"""Tests for the unified derived query contract service."""

from __future__ import annotations

import pytest
from ditto_datahub.models.derived import (
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services.derived import (
    COMPARE_RESULT_COLUMNS,
    LATEST_RESULT_COLUMNS,
    SERIES_RESULT_COLUMNS,
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedQueryService,
    DerivedSeriesQuery,
    DerivedSourceScope,
    empty_compare_result,
    empty_latest_result,
    empty_series_result,
)
from pytest_mock import MockerFixture


def _state_record(active_version: int | None = 3) -> DerivedStateRecord:
    return DerivedStateRecord(
        derived_id="factor.momentum_20d",
        active_version=active_version,
        coverage_start="2026-01-01",
        coverage_end="2026-03-13",
        watermark="2026-03-13",
        latest_run_id="run-001",
        latest_run_status="SUCCESS",
        total_rows=128,
        updated_at="2026-03-13T12:00:00+08:00",
    )


def _version_record(version: int = 3) -> DerivedVersionRecord:
    return DerivedVersionRecord(
        derived_id="factor.momentum_20d",
        version=version,
        status="MATERIALIZED",
        engine_version="expr-v0",
        is_online=True,
        is_primary=True,
        created_at="2026-03-13T12:00:00+08:00",
        updated_at=None,
    )


class TestDerivedQueryService:
    """Tests for DerivedQueryService."""

    def test_latest_query_rejects_empty_derived_ids(self) -> None:
        """Derived latest queries should reject empty ids."""
        with pytest.raises(ValueError, match="derived_ids must not be empty"):
            DerivedLatestQuery(derived_ids=(), instrument_ids=(1,))

    def test_series_query_rejects_non_positive_limit(self) -> None:
        """Derived series queries should validate positive limits."""
        with pytest.raises(ValueError, match="limit must be greater than 0"):
            DerivedSeriesQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                limit=0,
            )

    def test_latest_query_rejects_unsupported_source_scope(self) -> None:
        """Derived latest queries should reject unsupported source scopes."""
        with pytest.raises(ValueError, match="unsupported source_scope"):
            DerivedLatestQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                source_scope="archive",
            )

    def test_find_latest_resolves_active_version_before_backend_guard(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Latest queries should resolve active versions before failing closed."""
        catalog_service = mocker.Mock()
        catalog_service.get_state.return_value = _state_record(active_version=3)
        catalog_service.get_spec.return_value = object()
        catalog_service.get_version.return_value = _version_record(version=3)
        service = DerivedQueryService(catalog_service=catalog_service)
        query = DerivedLatestQuery(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1, 2),
        )

        with pytest.raises(NotImplementedError, match="Phase 3 backend not ready"):
            service.find_latest(query)

        catalog_service.get_state.assert_called_once_with("factor.momentum_20d")
        catalog_service.get_spec.assert_called_once_with("factor.momentum_20d", 3)
        catalog_service.get_version.assert_called_once_with("factor.momentum_20d", 3)

    def test_find_series_missing_spec_raises_key_error(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Explicit versions should fail fast when catalog metadata is missing."""
        catalog_service = mocker.Mock()
        catalog_service.get_spec.return_value = None
        service = DerivedQueryService(catalog_service=catalog_service)
        query = DerivedSeriesQuery(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            version=5,
        )

        with pytest.raises(KeyError, match="derived spec not found"):
            service.find_series(query)

        catalog_service.get_state.assert_not_called()
        catalog_service.get_spec.assert_called_once_with("factor.momentum_20d", 5)

    def test_compare_query_rejects_duplicate_sources(self) -> None:
        """Compare queries should require two distinct source scopes."""
        with pytest.raises(ValueError, match="two distinct scopes"):
            DerivedCompareQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                start="2026-03-01",
                end="2026-03-13",
                compare_sources=(
                    DerivedSourceScope.SERVING,
                    DerivedSourceScope.SERVING,
                ),
            )


def test_empty_result_helpers_expose_stable_columns() -> None:
    """Empty result helpers should preserve the Phase 2 schema contract."""
    assert empty_latest_result().columns == list(LATEST_RESULT_COLUMNS)
    assert empty_series_result().columns == list(SERIES_RESULT_COLUMNS)
    assert empty_compare_result().columns == list(COMPARE_RESULT_COLUMNS)


def test_services_exports_switch_to_derived_query_contract() -> None:
    """Top-level exports should no longer expose feature/factor query services."""
    import ditto_datahub
    from ditto_datahub import services

    assert "DerivedQueryService" in services.__all__
    assert "FeatureService" not in services.__all__
    assert "FactorService" not in services.__all__
    assert "DerivedQueryService" in ditto_datahub.__all__
