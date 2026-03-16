"""Integration tests for legacy derived catalog migration and query."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_core.engine.materialization.models import DerivedVersionStatus
from ditto_datahub.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
    DerivedSeriesQuery,
    LegacyDerivedCatalogMigrationService,
)
from ditto_datahub.stores.runtime.derived_catalog import DerivedCatalogWriter
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient

pytestmark = pytest.mark.serial


def _target_catalog(sqlite_client: SQLiteClient) -> DerivedCatalogService:
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )


def _seed_legacy_catalog(data_root: Path) -> None:
    writer = DerivedCatalogWriter(data_root)
    writer.write_spec(
        DerivedSpecRecord(
            derived_id="factor.momentum_20d",
            version=3,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="spec-hash-v3",
            spec_json={
                "id": "factor.momentum_20d",
                "version": 3,
                "role": "factor",
                "materialization_profile": "SERIES",
                "expression": "ts_mean(close, 20)",
            },
            created_at="2026-03-14T10:00:00+08:00",
        )
    )
    writer.write_version(
        DerivedVersionRecord(
            derived_id="factor.momentum_20d",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-14T10:00:00+08:00",
            updated_at=None,
        )
    )
    writer.write_run(
        DerivedRunRecord(
            run_id="drv-001",
            derived_id="factor.momentum_20d",
            version=3,
            mode="full",
            trigger="manual",
            request_start="2026-03-10",
            request_end="2026-03-11",
            compute_start="2026-03-10",
            compute_end="2026-03-11",
            source_snapshot_id="market:20260311-001",
            status="SUCCESS",
            rows_written=2,
            partitions_written=("2026",),
            error_message=None,
            created_at="2026-03-14T10:01:00+08:00",
            started_at="2026-03-14T10:01:00+08:00",
            finished_at="2026-03-14T10:01:30+08:00",
        )
    )
    writer.write_state(
        DerivedStateRecord(
            derived_id="factor.momentum_20d",
            active_version=3,
            coverage_start="2026-03-10",
            coverage_end="2026-03-11",
            watermark="2026-03-11",
            latest_run_id="drv-001",
            latest_run_status="SUCCESS",
            total_rows=2,
            updated_at="2026-03-14T10:01:30+08:00",
        )
    )
    writer.write_partitions(
        (
            DerivedPartitionRecord(
                run_id="drv-001",
                derived_id="factor.momentum_20d",
                version=3,
                partition_key="2026",
                partition_path="derived/artifacts/series/factor.momentum_20d/v3/2026.parquet",
                row_count=2,
                checksum="checksum-2026",
                written_at="2026-03-14T10:01:20+08:00",
            ),
        )
    )


def _write_artifact(data_root: Path) -> None:
    artifact_root = (
        data_root / "derived" / "artifacts" / "series" / "factor.momentum_20d" / "v3"
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "value": [1.5, 2.5],
            "availability_time": [date(2026, 3, 10), date(2026, 3, 11)],
        }
    ).write_parquet(artifact_root / "2026.parquet")


@pytest.mark.integration
class TestLegacyDerivedCatalogMigrationQueryIntegration:
    """Integration tests for legacy migration into the artifact query path."""

    def test_migration_makes_legacy_catalog_queryable_via_artifact_reader(
        self,
        sqlite_pool_with_schema,
        tmp_path: Path,
    ) -> None:
        """Migrated legacy records should immediately support artifact-backed query."""
        sqlite_client = SQLiteClient(sqlite_pool_with_schema)
        target_catalog = _target_catalog(sqlite_client)
        _seed_legacy_catalog(tmp_path)
        _write_artifact(tmp_path)
        migration_service = LegacyDerivedCatalogMigrationService(
            data_root=tmp_path,
            target_catalog_service=target_catalog,
        )

        migration_result = migration_service.migrate()
        query_service = DerivedQueryService(
            catalog_service=target_catalog,
            artifact_reader=DerivedArtifactReader(
                catalog_service=target_catalog,
                artifact_root=tmp_path,
            ),
        )
        frame = query_service.find_series(
            DerivedSeriesQuery(
                derived_ids=("factor.momentum_20d",),
                instrument_ids=(1,),
                start="2026-03-10",
                end="2026-03-11",
            )
        )

        assert migration_result.skipped_reason is None
        assert migration_result.migrated_specs == 1
        assert migration_result.migrated_versions == 1
        assert migration_result.migrated_runs == 1
        assert migration_result.migrated_states == 1
        assert migration_result.migrated_partitions == 1
        assert frame["derived_id"].to_list() == [
            "factor.momentum_20d",
            "factor.momentum_20d",
        ]
        assert frame["version"].to_list() == [3, 3]
        assert frame["value"].to_list() == [1.5, 2.5]
