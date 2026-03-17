"""Tests for invalidation cascade and repair."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import polars as pl
from ditto_core.engine.compile_cache import SQLiteCompileCache
from ditto_core.engine.materialization import (
    DerivedInvalidationEvent,
    DerivedMaterializationRequest,
)
from ditto_core.engine.materialization.models import (
    DerivedRunMode,
    DerivedRunTrigger,
    DerivedVersionStatus,
)
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_datahub.models.derived import (
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_port.services.derived import (
    DerivedInvalidationOrchestrator,
    InMemoryDerivedInputProvider,
)


def _service_bundle(sqlite_client, tmp_path: Path):
    from ditto_datahub.stores.runtime.derived_artifact_writer import (
        DerivedArtifactWriter,
    )
    from ditto_port.services.derived.materialization_orchestrator import (
        DerivedMaterializationOrchestrator,
    )

    catalog_service = DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )
    materialization_service = DerivedMaterializationOrchestrator(
        catalog_service=catalog_service,
        compile_cache_service=SQLiteCompileCache(sqlite_client),
        artifact_writer=DerivedArtifactWriter(tmp_path),
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
                        "factor.alpha_upstream": [0.5, 1.0],
                    }
                ),
            }
        ),
    )
    invalidation_service = DerivedInvalidationOrchestrator(
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
            status=DerivedVersionStatus.PUBLISHED,
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-13T10:00:00+08:00",
            updated_at=None,
        )
    )


class TestDerivedInvalidationOrchestrator:
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
        materialization_service = invalidation_service._materialization_service
        materialization_service.materialize(
            DerivedMaterializationRequest(
                derived_id=downstream.id,
                version=downstream.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
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
