"""Tests for the Phase 3 derived materialization service."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

import orjson
import polars as pl
from ditto_core.engine.materialization import DerivedMaterializationRequest
from ditto_core.engine.materialization.models import DerivedRunMode, DerivedRunTrigger
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_datahub.models.derived import (
    DerivedCheckpointRecord,
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_port.services.derived import (
    DerivedMaterializationService,
    InMemoryDerivedInputProvider,
    SQLiteCompileCacheService,
)


def _spec(profile: MaterializationProfile) -> DerivedSpec:
    role = (
        DerivedRole.FACTOR
        if profile != MaterializationProfile.DERIVE
        else DerivedRole.FEATURE
    )
    return DerivedSpec(
        id=f"{profile.name.lower()}.alpha_simple",
        version=3,
        role=role,
        materialization_profile=profile,
        expression="ts_delta(close, 1)",
    )


def _input_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 10),
                date(2026, 3, 11),
            ],
            "close": [10.0, 11.0, 20.0, 18.0],
        }
    )


def _catalog_service(sqlite_client, artifact_root: Path) -> DerivedCatalogService:
    del artifact_root
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )


def _seed_spec(
    catalog_service: DerivedCatalogService,
    spec: DerivedSpec,
) -> None:
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=spec.id,
            version=spec.version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{spec.id}:v{spec.version}",
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


class TestDerivedMaterializationService:
    """Tests for unified derived materialization."""

    def test_series_materialization_writes_artifact_and_runtime_metadata(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable profiles should write artifacts, checkpoint, and state."""
        spec = _spec(MaterializationProfile.SERIES)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        assert result.rows_written == 4
        assert result.partitions_written == ("2026",)
        state = catalog_service.get_state(spec.id)
        assert state is not None
        assert state.latest_run_status == "SUCCESS"
        partitions = catalog_service.list_partitions(spec.id, 3, result.run_id)
        assert len(partitions) == 1
        artifact_path = tmp_path / partitions[0].partition_path
        assert artifact_path.exists()
        metadata_path = (
            artifact_path.parent / "_runs" / result.run_id / "artifact_metadata.json"
        )
        assert metadata_path.exists()
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["compile_identity"]["cache_key"]

    def test_derive_materialization_is_ephemeral_only(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """DERIVE profile should keep runtime records without durable artifact/state."""
        spec = _spec(MaterializationProfile.DERIVE)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )

        assert result.partitions_written == ()
        assert catalog_service.get_state(spec.id) is None
        checkpoints = catalog_service.list_checkpoints(spec.id, 3)
        assert checkpoints == ()
        ephemeral_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / spec.id
            / "v3"
            / "_ephemeral"
        )
        assert ephemeral_root.exists()

    def test_checkpoint_rows_are_persisted(self, sqlite_client, tmp_path: Path) -> None:
        """Checkpoint rows should be visible after a durable run."""
        spec = _spec(MaterializationProfile.OFFLINE)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.SCHEDULED,
                source_snapshot_id="market:20260311-001",
            )
        )

        checkpoints = catalog_service.list_checkpoints(spec.id, 3)
        assert checkpoints == (
            DerivedCheckpointRecord(
                derived_id=spec.id,
                version=3,
                partition_key="2026",
                status="done",
                rows_written=4,
                checksum=checkpoints[0].checksum,
                error_message=None,
                started_at=checkpoints[0].started_at,
                completed_at=checkpoints[0].completed_at,
            ),
        )
        assert result.profile == MaterializationProfile.OFFLINE
