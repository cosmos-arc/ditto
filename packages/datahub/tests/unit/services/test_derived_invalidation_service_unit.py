"""Tests for invalidation cascade and repair."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import polars as pl
from ditto_core.engine.materialization import DerivedInvalidationEvent
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_datahub.models.derived import (
    DerivedDependencyRecord,
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_port.services.derived import (
    DerivedInvalidationService,
    DerivedMaterializationService,
    InMemoryDerivedInputProvider,
    SQLiteCompileCacheService,
)


def _service_bundle(sqlite_client, tmp_path: Path):
    catalog_service = DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )
    materialization_service = DerivedMaterializationService(
        catalog_service=catalog_service,
        compile_cache_service=SQLiteCompileCacheService(sqlite_client),
        input_provider=InMemoryDerivedInputProvider(
            {
                "factor.alpha_upstream": pl.DataFrame(
                    {
                        "instrument_id": [1, 1],
                        "trade_date": ["2026-03-10", "2026-03-11"],
                        "close": [10.0, 11.0],
                    }
                ),
                "factor.alpha_downstream": pl.DataFrame(
                    {
                        "instrument_id": [1, 1],
                        "trade_date": ["2026-03-10", "2026-03-11"],
                        "close": [10.0, 11.0],
                    }
                ),
            }
        ),
        artifact_root=tmp_path,
    )
    invalidation_service = DerivedInvalidationService(
        catalog_service=catalog_service,
        materialization_service=materialization_service,
    )
    return catalog_service, invalidation_service


def _seed_spec(catalog_service: DerivedCatalogService, spec: DerivedSpec) -> None:
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=spec.id,
            version=spec.version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{spec.id}",
            spec_json=asdict(spec),
            created_at="2026-03-13T10:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=spec.id,
            version=spec.version,
            status="active",
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-13T10:00:00+08:00",
            updated_at=None,
        )
    )


class TestDerivedInvalidationService:
    """Tests for invalidation cascade."""

    def test_enqueue_expands_to_durable_downstream_and_repair_marks_processed(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Pending invalidations should cascade through durable downstream specs."""
        catalog_service, invalidation_service = _service_bundle(sqlite_client, tmp_path)
        upstream = DerivedSpec(
            id="factor.alpha_upstream",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        downstream = DerivedSpec(
            id="factor.alpha_downstream",
            version=4,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.OFFLINE,
            expression="@factor.alpha_upstream",
        )
        _seed_spec(catalog_service, upstream)
        _seed_spec(catalog_service, downstream)
        catalog_service.save_dependencies(
            (
                DerivedDependencyRecord(
                    derived_id=downstream.id,
                    version=downstream.version,
                    dependency_kind="derived",
                    dependency_ref=upstream.id,
                    created_at="2026-03-13T11:00:00+08:00",
                ),
            )
        )

        invalidation_id = invalidation_service.enqueue(
            DerivedInvalidationEvent(
                source_domain="market",
                source_dataset="stock_daily",
                change_date="2026-03-11",
                affected_start="2026-03-10",
                affected_end="2026-03-11",
                source_snapshot_id="market:20260311-001",
                root_dependency_ref=upstream.id,
            )
        )

        pending = catalog_service.list_pending_invalidations()
        assert invalidation_id == pending[0].invalidation_id
        assert pending[0].derived_id == downstream.id

        results = invalidation_service.repair_pending(limit=10)

        assert len(results) == 1
        processed = catalog_service.list_pending_invalidations()
        assert processed == ()
