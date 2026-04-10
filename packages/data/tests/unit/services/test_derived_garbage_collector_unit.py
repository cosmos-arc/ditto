"""Tests for DerivedGarbageCollector — Phase 3 GC (version/run garbage collection)."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_data.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_data.services.derived.garbage_collector import DerivedGarbageCollector
from ditto_data.services.derived.gc_models import GcConfig, GcPlan, GcReport

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeReader:
    """In-process fake for DerivedCatalogReaderProtocol (partial)."""

    def __init__(self, versions: list[DerivedVersionRecord]) -> None:
        self._versions = list(versions)

    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]:
        return tuple(v for v in self._versions if v.derived_id == derived_id)

    def list_specs(
        self,
        derived_ids: tuple[str, ...] | None = None,
        durable_only: bool = False,
    ) -> tuple[DerivedSpecRecord, ...]:
        all_specs = tuple(
            DerivedSpecRecord(
                derived_id=v.derived_id,
                version=v.version,
                role="factor",
                materialization_profile="series",
                spec_hash=f"hash-v{v.version}",
                spec_json={},
                created_at=v.created_at,
            )
            for v in self._versions
        )
        if derived_ids is not None:
            allowed = set(derived_ids)
            return tuple(s for s in all_specs if s.derived_id in allowed)
        return all_specs

    def list_partitions(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> list[DerivedPartitionRecord]:
        return []

    def get_latest_run(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedRunRecord | None:
        return None


class _FakeWriter:
    """In-process fake for DerivedCatalogWriterProtocol (partial)."""

    def __init__(self) -> None:
        self.deleted: list[tuple[str, int]] = []
        self.delete_side_effect: Exception | None = None

    def delete_version_records(self, derived_id: str, version: int) -> int:
        if self.delete_side_effect is not None:
            raise self.delete_side_effect
        self.deleted.append((derived_id, version))
        return 1

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _make_version(
    derived_id: str,
    version: int,
    status: str = "published",
    is_online: bool = False,
    is_primary: bool = False,
) -> DerivedVersionRecord:
    return DerivedVersionRecord(
        derived_id=derived_id,
        version=version,
        status=status,
        engine_version="1.0",
        is_online=is_online,
        is_primary=is_primary,
        created_at=f"2026-03-{10 + version:02d}T00:00:00+08:00",
        updated_at=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGcSkipsPrimaryOnlineVersion:
    """primary_online versions must never be deleted."""

    def test_gc_skips_primary_online_version(self, tmp_path: Path) -> None:
        reader = _FakeReader(
            [
                _make_version("f.a", 1, "published", is_online=True, is_primary=True),
                _make_version("f.a", 2, "deprecated"),
                _make_version("f.a", 3, "deprecated"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        report = gc.gc_versions("f.a", keep_last_n=3)

        # v1 is primary_online -> protected.
        # v2, v3 are deprecated and GC-eligible (not in "last 3 durable"
        # because only v1 counts as durable/published).
        # With keep_last_n=3, v1 is the only durable version so it is kept.
        # v2, v3 are deprecated -> deleted.
        assert report.versions_deleted == 2
        deleted_versions = {v for _, v in writer.deleted}
        assert deleted_versions == {2, 3}

    def test_primary_online_not_in_dry_run(self, tmp_path: Path) -> None:
        reader = _FakeReader(
            [
                _make_version("f.a", 1, "published", is_online=True, is_primary=True),
                _make_version("f.a", 2, "archived"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        plans = gc.dry_run("f.a", keep_last_n=1)

        plan_versions = [p.version for p in plans]
        assert 1 not in plan_versions


class TestGcKeepsLastNVersions:
    """The most recent N published/materialized versions must be kept."""

    def test_gc_keeps_last_n_versions(self, tmp_path: Path) -> None:
        # v1=published, v2=published, v3=materialized, v4=published,
        # v5=published, v6=deprecated, v7=deprecated
        # Durable (published/materialized): v1, v2, v3, v4, v5
        # Last 3 by version number: v3, v4, v5 -> protected
        # v1, v2: published status, NOT in GC-eligible statuses -> not deleted
        # v6, v7: deprecated -> GC-eligible
        # Total GC-eligible: v6, v7 = 2
        reader = _FakeReader(
            [
                _make_version("f.a", 1, "published"),
                _make_version("f.a", 2, "published"),
                _make_version("f.a", 3, "materialized"),
                _make_version("f.a", 4, "published"),
                _make_version("f.a", 5, "published"),
                _make_version("f.a", 6, "deprecated"),
                _make_version("f.a", 7, "deprecated"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        report = gc.gc_versions("f.a", keep_last_n=3)

        assert report.versions_deleted == 2
        deleted_versions = {v for _, v in writer.deleted}
        assert deleted_versions == {6, 7}


class TestGcDeletesParquetAndSqliteRecords:
    """GC should clean up both disk artifacts and SQLite records."""

    def test_gc_deletes_both_disk_and_sql(self, tmp_path: Path) -> None:
        """Disk files and SQL records are removed when versions exceed keep_last_n."""
        # v1 and v2 should be GC'd (v3, v4, v5 kept as last 3 published)
        for v in (1, 2, 3, 4, 5):
            version_dir = (
                tmp_path / "derived" / "artifacts" / "series" / "f.a" / f"v{v}"
            )
            version_dir.mkdir(parents=True)
            (version_dir / "2024.parquet").touch()
            (version_dir / "2025.parquet").touch()
            runs_dir = version_dir / "_runs" / "run-001"
            runs_dir.mkdir(parents=True)
            (runs_dir / "metadata.json").touch()

        reader = _FakeReader(
            [
                _make_version("f.a", 1, "archived"),
                _make_version("f.a", 2, "archived"),
                _make_version("f.a", 3, "published"),
                _make_version("f.a", 4, "published"),
                _make_version("f.a", 5, "published"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        report = gc.gc_versions("f.a", keep_last_n=3)

        # v1, v2 deleted
        assert report.versions_deleted == 2
        assert report.files_removed >= 6  # 2 parquet + 1 run metadata per version
        assert report.records_removed == 2  # 1 per version from delete_version_records

        # Disk cleanup: v1 and v2 directories should be gone
        base = tmp_path / "derived" / "artifacts" / "series" / "f.a"
        assert not (base / "v1").exists()
        assert not (base / "v2").exists()
        # v3, v4, v5 should still exist
        assert (base / "v3").exists()
        assert (base / "v4").exists()
        assert (base / "v5").exists()


class TestDryRunDoesNotDelete:
    """dry_run should only compute the plan without executing."""

    def test_dry_run_does_not_delete(self, tmp_path: Path) -> None:
        reader = _FakeReader(
            [
                _make_version("f.a", 1, "archived"),
                _make_version("f.a", 2, "archived"),
                _make_version("f.a", 3, "published"),
                _make_version("f.a", 4, "published"),
                _make_version("f.a", 5, "published"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        plans = gc.dry_run("f.a", keep_last_n=3)

        assert len(plans) == 2
        plan_versions = sorted(p.version for p in plans)
        assert plan_versions == [1, 2]

        # Nothing should be deleted
        assert writer.deleted == []


class TestGcEmptyCatalogNoop:
    """GC on empty catalog should be a no-op."""

    def test_gc_empty_catalog_noop(self, tmp_path: Path) -> None:
        reader = _FakeReader([])
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        report = gc.gc_versions("f.nonexistent", keep_last_n=3)

        assert report.versions_deleted == 0
        assert report.files_removed == 0
        assert report.records_removed == 0
        assert report.errors == ()

    def test_gc_all_empty(self, tmp_path: Path) -> None:
        reader = _FakeReader([])
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        reports = gc.gc_all(keep_last_n=3)

        assert reports == []


class TestGcAll:
    """gc_all should iterate over all known derived_ids."""

    def test_gc_all_multiple_derived(self, tmp_path: Path) -> None:
        reader = _FakeReader(
            [
                _make_version("f.a", 1, "archived"),
                _make_version("f.a", 2, "published"),
                _make_version("f.a", 3, "published"),
                _make_version("f.b", 1, "deprecated"),
                _make_version("f.b", 2, "published"),
                _make_version("f.b", 3, "published"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        reports = gc.gc_all(keep_last_n=2)

        assert len(reports) == 2
        total_deleted = sum(r.versions_deleted for r in reports)
        assert total_deleted == 2  # v1 of f.a and v1 of f.b


class TestGcErrorHandling:
    """GC errors should be collected, not raised."""

    def test_sqlite_delete_error_collected(self, tmp_path: Path) -> None:
        reader = _FakeReader(
            [
                _make_version("f.a", 1, "archived"),
                _make_version("f.a", 2, "published"),
                _make_version("f.a", 3, "published"),
            ]
        )
        writer = _FakeWriter()
        writer.delete_side_effect = RuntimeError("DB locked")

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )
        report = gc.gc_versions("f.a", keep_last_n=2)

        # SQLite delete failed, so version is not counted as deleted
        assert report.versions_deleted == 0
        assert len(report.errors) == 1
        assert "DB locked" in report.errors[0]

    def test_file_deletion_error_collected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil

        version_dir = tmp_path / "derived" / "artifacts" / "series" / "f.a" / "v1"
        version_dir.mkdir(parents=True)
        parquet_file = version_dir / "2024.parquet"
        parquet_file.touch()

        reader = _FakeReader(
            [
                _make_version("f.a", 1, "archived"),
                _make_version("f.a", 2, "published"),
                _make_version("f.a", 3, "published"),
            ]
        )
        writer = _FakeWriter()

        gc = DerivedGarbageCollector(
            catalog_reader=reader,
            catalog_writer=writer,
            artifact_root=tmp_path,
        )

        def mock_rmtree(path: object, *args: object, **kwargs: object) -> None:
            raise OSError("Permission denied")

        monkeypatch.setattr(shutil, "rmtree", mock_rmtree)
        report = gc.gc_versions("f.a", keep_last_n=2)

        # SQLite delete should succeed even though file removal failed
        assert report.records_removed == 1
        assert len(report.errors) == 1
        assert "Permission denied" in report.errors[0]


class TestGcPlan:
    """GcPlan dataclass tests."""

    def test_gc_plan_fields(self) -> None:
        plan = GcPlan(
            derived_id="f.a",
            version=1,
            partition_paths=("/data/2024.parquet",),
            run_ids=("run-001",),
        )
        assert plan.derived_id == "f.a"
        assert plan.version == 1
        assert plan.partition_paths == ("/data/2024.parquet",)
        assert plan.run_ids == ("run-001",)


class TestGcConfig:
    """GcConfig dataclass tests."""

    def test_gc_config_defaults(self) -> None:
        config = GcConfig()
        assert config.keep_last_n == 3

    def test_gc_config_custom(self) -> None:
        config = GcConfig(keep_last_n=5)
        assert config.keep_last_n == 5


class TestGcReport:
    """GcReport dataclass tests."""

    def test_gc_report_fields(self) -> None:
        report = GcReport(
            derived_id="f.a",
            versions_deleted=2,
            files_removed=10,
            records_removed=2,
        )
        assert report.derived_id == "f.a"
        assert report.versions_deleted == 2
        assert report.files_removed == 10
        assert report.records_removed == 2
        assert report.errors == ()

    def test_gc_report_with_errors(self) -> None:
        report = GcReport(
            derived_id="f.a",
            versions_deleted=1,
            files_removed=5,
            records_removed=1,
            errors=("Permission denied: /data/v1/2024.parquet",),
        )
        assert len(report.errors) == 1
