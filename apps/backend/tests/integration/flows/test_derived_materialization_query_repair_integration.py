"""Integration tests for derived materialize -> query -> repair flow."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.queries.research import ResearchDatasetFacade
from ditto_apps.jobs.flows.materialization import (
    daily_materialization_flow,
    repair_from_invalidation_flow,
)
from ditto_apps.registry import ConfigProvider
from ditto_apps.registry.contexts.bundle import MaterializationBundle
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogWriter,
    DataSchemaFingerprint,
)
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.materialization import DerivedInvalidationEvent
from ditto_features.materialization.models import DerivedVersionStatus
from ditto_features.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_features.services import (
    DerivedCatalogService,
    DerivedQueryService,
    DerivedSeriesQuery,
)

pytestmark = pytest.mark.serial


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

        @provide
        def exchange_transformers(self) -> ExchangeTransformers:
            return ExchangeTransformers(
                tushare=MagicMock(),
                tdx=MagicMock(),
            )

    return SourcesProvider()


def _make_test_container():
    from ditto_apps.registry.container import _get_base_providers

    return make_container(
        ConfigProvider(),
        _sources_provider(),
        *_get_base_providers(),
    )


@contextmanager
def _materialization_bundle_context():
    from ditto_application.processes.materialization.orchestrator import (
        DerivedMaterializationOrchestrator,
    )

    container = _make_test_container()
    try:
        yield MaterializationBundle(
            materialization_service=container.get(DerivedMaterializationOrchestrator),
            invalidation_service=container.get(InvalidationCascadeOrchestrator),
            publication_facade=container.get(DerivedPublicationFacade),
            research_dataset_facade=container.get(ResearchDatasetFacade),
        )
    finally:
        container.close()


def _invoke_flow(flow_entrypoint: Any, **kwargs: Any) -> dict[str, Any]:
    runner: Any = getattr(flow_entrypoint, "fn", flow_entrypoint)
    return runner(**kwargs)


def _write_market_truth_layers(data_root: Path, *, close_values: list[float]) -> None:
    market_root = data_root / "market" / "stock"
    (market_root / "bars").mkdir(parents=True, exist_ok=True)
    (market_root / "adj").mkdir(parents=True, exist_ok=True)
    (market_root / "status").mkdir(parents=True, exist_ok=True)
    trade_dates = [date(2026, 3, 10), date(2026, 3, 11)]
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": trade_dates,
            "open": close_values,
            "high": close_values,
            "low": close_values,
            "close": close_values,
            "pre_close": close_values,
            "volume": [100.0, 110.0],
            "amount": [1_000.0, 1_100.0],
        }
    ).write_parquet(market_root / "bars" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": trade_dates,
            "adj_factor": [1.0, 1.0],
        }
    ).write_parquet(market_root / "adj" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": trade_dates,
            "is_suspended": [False, False],
            "suspend_timing": [None, None],
            "is_st": [False, False],
            "st_type": [None, None],
            "list_status": ["L", "L"],
            "source": ["test", "test"],
            "source_ticker": ["000001.SZ", "000001.SZ"],
        }
    ).write_parquet(market_root / "status" / "2026.parquet")


def _seed_market_catalog(
    catalog: DataCatalogWriter,
    *,
    source_snapshot_id: str,
) -> None:
    """Register the two physical truth partitions used by this integration test."""
    columns = (
        "instrument_id",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
    )
    for trade_date in ("2026-03-10", "2026-03-11"):
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    namespace="market",
                    dataset_id="stock_daily",
                    partition_keys=(f"trade_date={trade_date}",),
                ),
                storage_uri=f"market/stock_daily/{trade_date}",
                schema=DataSchemaFingerprint(
                    schema_hash="sha256:integration-stock-daily-v1",
                    row_count=1,
                    schema_version="market.stock_daily.v1",
                    columns=columns,
                ),
                source="tushare",
                freshness_at=datetime(2026, 3, 12, tzinfo=UTC),
                source_snapshot_id=source_snapshot_id,
            )
        )


def _seed_series_spec(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
    expression: str,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expression,
    )
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=derived_id,
            version=version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{derived_id}:v{version}",
            spec_json=asdict(spec),
            created_at="2026-03-14T12:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=derived_id,
            version=version,
            status=DerivedVersionStatus.PUBLISHED,
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-14T12:00:00+08:00",
            updated_at=None,
        )
    )


@pytest.mark.integration
class TestDerivedMaterializationQueryRepairIntegration:
    """Integration tests for the derived repair chain."""

    def test_materialize_query_and_repair_flow_share_one_artifact_chain(
        self,
        monkeypatch,
        mocker,
        tmp_path: Path,
    ) -> None:
        """Materialize -> query -> repair should update the queried artifact slice."""
        sqlite_path = tmp_path / "metadata" / "metadata.sqlite"
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        monkeypatch.setenv("SQLITE_PATH", sqlite_path.as_posix())
        _write_market_truth_layers(tmp_path, close_values=[10.0, 11.0])

        seed_container = _make_test_container()
        try:
            catalog_service = seed_container.get(DerivedCatalogService)
            _seed_market_catalog(
                seed_container.get(DataCatalogWriter),
                source_snapshot_id="market:20260311-001",
            )
            _seed_series_spec(
                catalog_service,
                derived_id="factor.alpha_repair",
                version=3,
                expression="market.close * 2",
            )
        finally:
            seed_container.close()

        mocker.patch(
            "ditto_apps.jobs.flows.materialization.create_materialization_bundle",
            side_effect=_materialization_bundle_context,
        )

        materialize_result = _invoke_flow(
            daily_materialization_flow,
            trade_date="2026-03-11",
            mode="full",
            derived_ids=["factor.alpha_repair"],
        )

        before_container = _make_test_container()
        try:
            invalidation_service = before_container.get(InvalidationCascadeOrchestrator)
            query_service = before_container.get(DerivedQueryService)
            before_frame = query_service.find_series(
                DerivedSeriesQuery(
                    derived_ids=("factor.alpha_repair",),
                    instrument_ids=(1,),
                    start="2026-03-11",
                    end="2026-03-11",
                )
            )
            _write_market_truth_layers(tmp_path, close_values=[10.0, 21.0])
            _seed_market_catalog(
                before_container.get(DataCatalogWriter),
                source_snapshot_id="market:20260311-002",
            )
            invalidation_service.propagate(
                DerivedInvalidationEvent(
                    source_domain="market",
                    source_dataset="stock_daily",
                    change_date="2026-03-11",
                    affected_start="2026-03-11",
                    affected_end="2026-03-11",
                    source_snapshot_id="market:20260311-002",
                    root_dependency_ref="market.stock_daily",
                )
            )
        finally:
            before_container.close()

        repair_result = _invoke_flow(repair_from_invalidation_flow, limit=10)

        verify_container = _make_test_container()
        try:
            catalog_service = verify_container.get(DerivedCatalogService)
            query_service = verify_container.get(DerivedQueryService)
            after_frame = query_service.find_series(
                DerivedSeriesQuery(
                    derived_ids=("factor.alpha_repair",),
                    instrument_ids=(1,),
                    start="2026-03-11",
                    end="2026-03-11",
                )
            )
            latest_run = catalog_service.get_latest_run("factor.alpha_repair", 3)
            stale_invalidations = catalog_service.list_stale_invalidations()
        finally:
            verify_container.close()

        assert materialize_result["summary"]["materialized_count"] == 1
        assert before_frame["value"].to_list() == [22.0]
        assert repair_result["summary"]["repaired_count"] == 1
        assert after_frame["value"].to_list() == [42.0]
        assert latest_run is not None
        assert latest_run.trigger == "cascade"
        assert stale_invalidations == ()
