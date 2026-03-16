"""Tests for legacy derived catalog migration."""

from __future__ import annotations

from pathlib import Path

from ditto_core.engine.materialization.models import DerivedVersionStatus
from ditto_datahub.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services import (
    DerivedCatalogService,
    LegacyDerivedCatalogMigrationService,
)
from ditto_datahub.stores.runtime.derived_catalog import DerivedCatalogWriter
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)


def _target_catalog(sqlite_client) -> DerivedCatalogService:
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
            request_start="2026-03-01",
            request_end="2026-03-14",
            compute_start="2026-03-01",
            compute_end="2026-03-14",
            source_snapshot_id="market:20260314-001",
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
            coverage_start="2026-03-01",
            coverage_end="2026-03-14",
            watermark="2026-03-14",
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


class TestLegacyDerivedCatalogMigrationService:
    """Tests for LegacyDerivedCatalogMigrationService."""

    def test_migrate_copies_legacy_json_catalog_into_sqlite_and_is_idempotent(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Migration should copy supported legacy records once and then no-op."""
        _seed_legacy_catalog(tmp_path)
        target_catalog = _target_catalog(sqlite_client)
        service = LegacyDerivedCatalogMigrationService(
            data_root=tmp_path,
            target_catalog_service=target_catalog,
        )

        first = service.migrate()

        assert first.skipped_reason is None
        assert first.migrated_specs == 1
        assert first.migrated_versions == 1
        assert first.migrated_runs == 1
        assert first.migrated_states == 1
        assert first.migrated_partitions == 1
        assert target_catalog.get_spec("factor.momentum_20d", 3) is not None
        assert target_catalog.get_version("factor.momentum_20d", 3) is not None
        assert target_catalog.get_run("factor.momentum_20d", 3, "drv-001") is not None
        assert target_catalog.get_state("factor.momentum_20d") is not None
        assert (
            len(target_catalog.list_partitions("factor.momentum_20d", 3, "drv-001"))
            == 1
        )

        second = service.migrate()

        assert second.skipped_reason == "target_not_empty"
        assert second.migrated_specs == 0
        assert second.migrated_versions == 0
        assert second.migrated_runs == 0
        assert second.migrated_states == 0
        assert second.migrated_partitions == 0

    def test_migrate_is_noop_when_legacy_source_is_missing(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Missing legacy source should not create any target records."""
        service = LegacyDerivedCatalogMigrationService(
            data_root=tmp_path,
            target_catalog_service=_target_catalog(sqlite_client),
        )

        result = service.migrate()

        assert result.skipped_reason == "source_missing"
        assert result.migrated_specs == 0
        assert result.migrated_versions == 0
        assert result.migrated_runs == 0
        assert result.migrated_states == 0
        assert result.migrated_partitions == 0
