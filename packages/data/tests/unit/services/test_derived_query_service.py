"""Tests for the unified derived query contract service."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_features.materialization.models import DerivedVersionStatus
from ditto_features.models.derived import (
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_features.services.derived import (
    COMPARE_RESULT_COLUMNS,
    LATEST_RESULT_COLUMNS,
    SERIES_RESULT_COLUMNS,
    DerivedArtifactReader,
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedQueryService,
    DerivedSeriesQuery,
    DerivedSourceScope,
    empty_compare_result,
    empty_latest_result,
    empty_series_result,
)
from ditto_features.services.derived_catalog_service import DerivedCatalogService
from ditto_features.storage.sqlite.derived import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_kernel.exceptions import DerivedNotFoundError
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile


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
        status=DerivedVersionStatus.MATERIALIZED,
        engine_version="expr-v0",
        is_online=True,
        is_primary=True,
        created_at="2026-03-13T12:00:00+08:00",
        updated_at=None,
    )


def _catalog_service(sqlite_client) -> DerivedCatalogService:
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )


def _seed_spec(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
    is_online: bool,
    is_primary: bool,
    profile: MaterializationProfile = MaterializationProfile.SERIES,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=profile,
        expression="market.close",
    )
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=derived_id,
            version=version,
            role=spec.role.value,
            materialization_profile=profile.value,
            spec_hash=f"hash:{derived_id}:v{version}",
            spec_json=asdict(spec),
            created_at="2026-03-13T12:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=derived_id,
            version=version,
            status=DerivedVersionStatus.PUBLISHED
            if is_primary
            else DerivedVersionStatus.MATERIALIZED,
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-13T12:00:00+08:00",
            updated_at=None,
        )
    )


def _write_artifact(
    artifact_root: Path,
    *,
    derived_id: str,
    version: int,
    rows: list[dict[str, object]],
) -> None:
    version_root = (
        artifact_root / "derived" / "artifacts" / "series" / derived_id / f"v{version}"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(version_root / "2026.parquet")


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

    def test_find_latest_reads_primary_online_artifact_slice(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Serving latest queries should prefer the primary online version artifact."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.momentum_20d"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=2,
            is_online=True,
            is_primary=True,
        )
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=3,
            is_online=False,
            is_primary=False,
        )
        catalog_service.save_state(_state_record(active_version=3))
        _write_artifact(
            tmp_path,
            derived_id=derived_id,
            version=2,
            rows=[
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 10),
                    "value": 1.0,
                    "availability_time": date(2026, 3, 10),
                },
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 11),
                    "value": 2.0,
                    "availability_time": date(2026, 3, 11),
                },
            ],
        )
        _write_artifact(
            tmp_path,
            derived_id=derived_id,
            version=3,
            rows=[
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 11),
                    "value": 99.0,
                    "availability_time": date(2026, 3, 11),
                },
            ],
        )
        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
        )
        query = DerivedLatestQuery(
            derived_ids=(derived_id,),
            instrument_ids=(1,),
            as_of="2026-03-11",
        )

        result = service.find_latest(query)

        assert result.to_dicts() == [
            {
                "derived_id": derived_id,
                "instrument_id": 1,
                "value": 2.0,
                "trade_date": date(2026, 3, 11),
                "bar_time": None,
                "asof_ts": None,
                "version": 2,
            }
        ]

    def test_find_series_missing_spec_raises_not_found(
        self,
        sqlite_client,
    ) -> None:
        """Explicit versions should fail fast when catalog metadata is missing."""
        catalog_service = _catalog_service(sqlite_client)
        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=Path("/tmp/does-not-exist"),
            ),
        )
        query = DerivedSeriesQuery(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            version=5,
        )

        with pytest.raises(DerivedNotFoundError, match="Derived not found"):
            service.find_series(query)

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

    def test_find_series_reads_requested_offline_version_artifact(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Offline series queries should honor an explicit version override."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.momentum_20d"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=2,
            is_online=False,
            is_primary=False,
        )
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=3,
            is_online=True,
            is_primary=True,
        )
        catalog_service.save_state(_state_record(active_version=3))
        _write_artifact(
            tmp_path,
            derived_id=derived_id,
            version=2,
            rows=[
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 10),
                    "value": 1.5,
                    "availability_time": date(2026, 3, 10),
                },
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 11),
                    "value": 2.5,
                    "availability_time": date(2026, 3, 11),
                },
            ],
        )
        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
        )

        result = service.find_series(
            DerivedSeriesQuery(
                derived_ids=(derived_id,),
                instrument_ids=(1,),
                start="2026-03-10",
                end="2026-03-11",
                version=2,
            )
        )

        assert result.to_dicts() == [
            {
                "derived_id": derived_id,
                "instrument_id": 1,
                "trade_date": date(2026, 3, 10),
                "bar_time": None,
                "value": 1.5,
                "asof_ts": None,
                "version": 2,
            },
            {
                "derived_id": derived_id,
                "instrument_id": 1,
                "trade_date": date(2026, 3, 11),
                "bar_time": None,
                "value": 2.5,
                "asof_ts": None,
                "version": 2,
            },
        ]

    def test_compare_sources_reads_serving_and_offline_artifacts(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Compare queries should join serving baseline and offline candidate."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.momentum_20d"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=2,
            is_online=True,
            is_primary=True,
        )
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=3,
            is_online=False,
            is_primary=False,
        )
        catalog_service.save_state(_state_record(active_version=3))
        _write_artifact(
            tmp_path,
            derived_id=derived_id,
            version=2,
            rows=[
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 10),
                    "value": 1.0,
                    "availability_time": date(2026, 3, 10),
                },
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 11),
                    "value": 1.5,
                    "availability_time": date(2026, 3, 11),
                },
            ],
        )
        _write_artifact(
            tmp_path,
            derived_id=derived_id,
            version=3,
            rows=[
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 10),
                    "value": 1.2,
                    "availability_time": date(2026, 3, 10),
                },
                {
                    "instrument_id": 1,
                    "trade_date": date(2026, 3, 11),
                    "value": 1.4,
                    "availability_time": date(2026, 3, 11),
                },
            ],
        )
        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
        )

        result = service.compare_sources(
            DerivedCompareQuery(
                derived_ids=(derived_id,),
                instrument_ids=(1,),
                start="2026-03-10",
                end="2026-03-11",
                version=3,
            )
        )

        assert result.to_dicts() == [
            {
                "derived_id": derived_id,
                "instrument_id": 1,
                "trade_date": date(2026, 3, 10),
                "serving_value": 1.0,
                "offline_value": 1.2,
                "diff": -0.2,
            },
            {
                "derived_id": derived_id,
                "instrument_id": 1,
                "trade_date": date(2026, 3, 11),
                "serving_value": 1.5,
                "offline_value": 1.4,
                "diff": 0.1,
            },
        ]


class TestQueryForEvaluation:
    """Tests for DerivedQueryService.query_for_evaluation."""

    def test_query_for_evaluation_returns_clean_columns(self) -> None:
        """query_for_evaluation() should return only clean columns."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "value": [1.0, 2.0],
                "availability_time": [date(2026, 3, 10), date(2026, 3, 11)],
                "extra_internal_col": ["a", "b"],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        result = service.query_for_evaluation(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start="2026-03-10",
            end="2026-03-11",
        )

        assert result.columns == ["derived_id", "instrument_id", "trade_date", "value"]
        assert result.height == 2
        assert result.to_dicts() == [
            {
                "derived_id": "factor.momentum_20d",
                "instrument_id": 1,
                "trade_date": date(2026, 3, 10),
                "value": 1.0,
            },
            {
                "derived_id": "factor.momentum_20d",
                "instrument_id": 1,
                "trade_date": date(2026, 3, 11),
                "value": 2.0,
            },
        ]

    def test_query_for_evaluation_multiple_derived_ids(self) -> None:
        """query_for_evaluation() should concat results from multiple derived_ids."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1

        call_count = 0

        def mock_read_frame(**kwargs: object) -> pl.DataFrame:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return pl.DataFrame(
                    {
                        "instrument_id": [1],
                        "trade_date": [date(2026, 3, 10)],
                        "value": [10.0],
                        "availability_time": [date(2026, 3, 10)],
                    }
                )
            return pl.DataFrame(
                {
                    "instrument_id": [2],
                    "trade_date": [date(2026, 3, 10)],
                    "value": [20.0],
                    "availability_time": [date(2026, 3, 10)],
                }
            )

        artifact_reader.read_frame.side_effect = mock_read_frame

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        result = service.query_for_evaluation(
            derived_ids=("factor.momentum_20d", "factor.volatility_10d"),
        )

        assert result.height == 2
        assert set(result["derived_id"].to_list()) == {
            "factor.momentum_20d",
            "factor.volatility_10d",
        }

    def test_query_for_evaluation_applies_date_filters(self) -> None:
        """query_for_evaluation() should pass start/end filters to read_frame."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 2
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 15)],
                "value": [3.0],
                "availability_time": [date(2026, 3, 15)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        service.query_for_evaluation(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start="2026-03-15",
            end="2026-03-15",
            as_of="2026-03-15",
            version=2,
        )

        artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.momentum_20d",
            version=2,
            instrument_ids=(1,),
            start="2026-03-15",
            end="2026-03-15",
            as_of="2026-03-15",
            streaming=False,
        )

    def test_query_for_evaluation_returns_empty_on_no_data(self) -> None:
        """query_for_evaluation() should return empty frame when no data."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        artifact_reader.read_frame.return_value = pl.DataFrame()

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        result = service.query_for_evaluation(
            derived_ids=("factor.nonexistent",),
        )

        assert result.is_empty()
        assert result.columns == ["derived_id", "instrument_id", "trade_date", "value"]

    def test_query_for_evaluation_sorts_by_derived_id_instrument_trade_date(
        self,
    ) -> None:
        """query_for_evaluation() should sort by (derived_id, instrument, date)."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        # Return unsorted data
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [2, 1],
                "trade_date": [date(2026, 3, 11), date(2026, 3, 10)],
                "value": [20.0, 10.0],
                "availability_time": [date(2026, 3, 11), date(2026, 3, 10)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        result = service.query_for_evaluation(
            derived_ids=("factor.momentum_20d",),
        )

        assert result.to_dicts() == [
            {
                "derived_id": "factor.momentum_20d",
                "instrument_id": 1,
                "trade_date": date(2026, 3, 10),
                "value": 10.0,
            },
            {
                "derived_id": "factor.momentum_20d",
                "instrument_id": 2,
                "trade_date": date(2026, 3, 11),
                "value": 20.0,
            },
        ]


def test_empty_result_helpers_expose_stable_columns() -> None:
    """Empty result helpers should preserve the Phase 2 schema contract."""
    assert empty_latest_result().columns == list(LATEST_RESULT_COLUMNS)
    assert empty_series_result().columns == list(SERIES_RESULT_COLUMNS)
    assert empty_compare_result().columns == list(COMPARE_RESULT_COLUMNS)


class TestStreamingMemoryManagement:
    """Tests for streaming and lazy query support on DerivedQueryService."""

    def test_find_series_passes_streaming_to_read_frame(self) -> None:
        """find_series(streaming=True) should pass streaming=True to read_frame."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "value": [1.0],
                "availability_time": [date(2026, 3, 10)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )
        query = DerivedSeriesQuery(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start="2026-03-10",
            end="2026-03-11",
        )

        service.find_series(query, streaming=True)

        artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.momentum_20d",
            version=1,
            instrument_ids=(1,),
            start="2026-03-10",
            end="2026-03-11",
            as_of=None,
            streaming=True,
        )

    def test_find_latest_passes_streaming_to_read_frame(self) -> None:
        """find_latest(streaming=True) should pass streaming=True to read_frame."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_serving_version.return_value = 2
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 11)],
                "value": 2.0,
                "availability_time": [date(2026, 3, 11)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )
        query = DerivedLatestQuery(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
        )

        service.find_latest(query, streaming=True)

        artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.momentum_20d",
            version=2,
            instrument_ids=(1,),
            as_of=None,
            streaming=True,
        )

    def test_query_for_evaluation_passes_streaming_to_read_frame(self) -> None:
        """query_for_evaluation(streaming=True) should pass streaming=True."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "value": [1.0],
                "availability_time": [date(2026, 3, 10)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        service.query_for_evaluation(
            derived_ids=("factor.momentum_20d",),
            streaming=True,
        )

        artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.momentum_20d",
            version=1,
            instrument_ids=None,
            start=None,
            end=None,
            as_of=None,
            streaming=True,
        )

    def test_query_for_evaluation_defaults_to_non_streaming(self) -> None:
        """query_for_evaluation() should default to streaming=False."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "value": [1.0],
                "availability_time": [date(2026, 3, 10)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        service.query_for_evaluation(
            derived_ids=("factor.momentum_20d",),
        )

        artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.momentum_20d",
            version=1,
            instrument_ids=None,
            start=None,
            end=None,
            as_of=None,
            streaming=False,
        )

    def test_compare_sources_passes_streaming_to_read_frame(self) -> None:
        """compare_sources(streaming=True) should pass streaming=True to all reads."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_serving_version.return_value = 2
        artifact_reader.resolve_offline_version.return_value = 3
        artifact_reader.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "value": [1.0],
                "availability_time": [date(2026, 3, 10)],
            }
        )

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )
        query = DerivedCompareQuery(
            derived_ids=("factor.momentum_20d",),
            instrument_ids=(1,),
            start="2026-03-10",
            end="2026-03-11",
            version=3,
        )

        service.compare_sources(query, streaming=True)

        assert artifact_reader.read_frame.call_count == 2
        for call_args in artifact_reader.read_frame.call_args_list:
            assert call_args.kwargs.get("streaming") is True

    def test_query_as_lazy_returns_lazy_frame(self) -> None:
        """query_as_lazy() should return a pl.LazyFrame for custom processing."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        lazy_frame = pl.LazyFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "value": [1.0],
                "availability_time": [date(2026, 3, 10)],
            }
        )

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1
        artifact_reader.read_frame.return_value = lazy_frame

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        result = service.query_as_lazy(
            derived_ids=("factor.momentum_20d",),
            start="2026-03-10",
            end="2026-03-11",
        )

        assert isinstance(result, pl.LazyFrame)
        artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.momentum_20d",
            version=1,
            instrument_ids=None,
            start="2026-03-10",
            end="2026-03-11",
            as_of=None,
            as_lazy=True,
        )

    def test_query_as_lazy_multiple_derived_ids_returns_lazy_frame(
        self,
    ) -> None:
        """query_as_lazy() with multiple ids should return a LazyFrame concat."""
        catalog_service = MagicMock(spec=DerivedCatalogService)
        catalog_service.list_specs.return_value = ()
        catalog_service.get_version.return_value = None

        artifact_reader = MagicMock(spec=DerivedArtifactReader)
        artifact_reader.resolve_offline_version.return_value = 1

        def mock_read_frame(**kwargs: object) -> pl.LazyFrame | pl.DataFrame:
            derived_id = kwargs["derived_id"]
            if derived_id == "factor.momentum_20d":
                return pl.LazyFrame(
                    {
                        "instrument_id": [1],
                        "trade_date": [date(2026, 3, 10)],
                        "value": [10.0],
                        "availability_time": [date(2026, 3, 10)],
                    }
                )
            return pl.LazyFrame(
                {
                    "instrument_id": [2],
                    "trade_date": [date(2026, 3, 10)],
                    "value": [20.0],
                    "availability_time": [date(2026, 3, 10)],
                }
            )

        artifact_reader.read_frame.side_effect = mock_read_frame

        service = DerivedQueryService(
            catalog_service=catalog_service,
            artifact_reader=artifact_reader,
        )

        result = service.query_as_lazy(
            derived_ids=("factor.momentum_20d", "factor.volatility_10d"),
        )

        assert isinstance(result, pl.LazyFrame)
        collected = result.collect()
        assert collected.height == 2


def test_services_exports_no_cross_package_re_exports() -> None:
    """data.services should not re-export features/analysis services."""
    from ditto_data import services

    assert "DerivedQueryService" not in services.__all__
    assert "DerivedCatalogService" not in services.__all__
    assert "DerivedShadowSlotService" not in services.__all__
    assert "DerivedArtifactReader" not in services.__all__
