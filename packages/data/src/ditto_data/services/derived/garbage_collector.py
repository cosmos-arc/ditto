"""Garbage collector for derived catalog version/run records and artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from ditto_platform.foundation import logger

from ditto_data.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_data.services.derived.gc_models import GcPlan, GcReport

__all__ = ["DerivedGarbageCollector"]

# Statuses eligible for GC when not protected by keep_last_n or primary_online.
_GC_ELIGIBLE_STATUSES: frozenset[str] = frozenset(
    {"deprecated", "archived", "draft"},
)


class _CatalogReader(Protocol):
    """Minimal reader interface needed by the garbage collector."""

    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]: ...

    def list_specs(
        self,
        derived_ids: tuple[str, ...] | None = None,
        durable_only: bool = False,
    ) -> tuple[DerivedSpecRecord, ...]: ...


class _CatalogWriter(Protocol):
    """Minimal writer interface needed by the garbage collector."""

    def delete_version_records(self, derived_id: str, version: int) -> int: ...


class DerivedGarbageCollector:
    """
    Garbage-collect old derived version records and disk artifacts.

    Protection rules (a version is **protected** if ANY applies):
    - ``is_online=True and is_primary=True`` (primary online version)
    - Among the most recent *keep_last_n* published/materialized versions

    Everything else with a GC-eligible status is a candidate for deletion.
    """

    def __init__(
        self,
        catalog_reader: _CatalogReader,
        catalog_writer: _CatalogWriter,
        artifact_root: Path,
    ) -> None:
        self._reader = catalog_reader
        self._writer = catalog_writer
        self._artifact_root = Path(artifact_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dry_run(
        self,
        derived_id: str,
        keep_last_n: int = 3,
    ) -> list[GcPlan]:
        """Compute deletion plan without executing anything."""
        candidates = self._collect_candidates(derived_id, keep_last_n)
        plans: list[GcPlan] = []
        for version_rec in candidates:
            plans.append(
                GcPlan(
                    derived_id=derived_id,
                    version=version_rec.version,
                )
            )
        return plans

    def gc_versions(
        self,
        derived_id: str,
        keep_last_n: int = 3,
    ) -> GcReport:
        """Execute GC for one derived id."""
        candidates = self._collect_candidates(derived_id, keep_last_n)
        errors: list[str] = []
        files_removed = 0
        records_removed = 0
        versions_deleted = 0

        for version_rec in candidates:
            # 1. Delete disk artifacts
            removed, file_errors = self._remove_version_artifacts(
                derived_id, version_rec.version
            )
            files_removed += removed
            errors.extend(file_errors)

            # 2. Delete SQLite records
            try:
                deleted = self._writer.delete_version_records(
                    derived_id, version_rec.version
                )
                records_removed += deleted
                versions_deleted += 1
            except Exception as exc:
                msg = (
                    f"Failed to delete SQLite records for "
                    f"{derived_id} v{version_rec.version}: {exc}"
                )
                logger.warning(msg)
                errors.append(msg)

        return GcReport(
            derived_id=derived_id,
            versions_deleted=versions_deleted,
            files_removed=files_removed,
            records_removed=records_removed,
            errors=tuple(errors),
        )

    def gc_all(self, keep_last_n: int = 3) -> list[GcReport]:
        """Execute GC for every derived id known to the catalog."""
        specs = self._reader.list_specs()
        derived_ids = list({s.derived_id for s in specs})
        reports: list[GcReport] = []
        for did in derived_ids:
            report = self.gc_versions(did, keep_last_n=keep_last_n)
            reports.append(report)
        return reports

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _collect_candidates(
        self,
        derived_id: str,
        keep_last_n: int,
    ) -> list[DerivedVersionRecord]:
        """Return version records eligible for GC, ordered ascending by version."""
        all_versions = self._reader.list_versions(derived_id)
        if not all_versions:
            return []

        protected_set = self._protected_versions(all_versions, keep_last_n)

        candidates: list[DerivedVersionRecord] = []
        for v in all_versions:
            if v.version in protected_set:
                continue
            if v.status not in _GC_ELIGIBLE_STATUSES:
                continue
            candidates.append(v)
        return candidates

    @staticmethod
    def _protected_versions(
        versions: tuple[DerivedVersionRecord, ...],
        keep_last_n: int,
    ) -> set[int]:
        """
        Compute the set of protected version numbers.

        A version is protected if:
        - It is the primary_online version, OR
        - It is among the last *keep_last_n* published/materialized versions.
        """
        protected: set[int] = set()

        # Rule 1: primary_online
        for v in versions:
            if v.is_online and v.is_primary:
                protected.add(v.version)

        # Rule 2: last N published/materialized versions (by version number desc)
        durable_statuses = {"published", "materialized"}
        durable = [v for v in versions if v.status in durable_statuses]
        durable.sort(key=lambda v: v.version, reverse=True)
        for v in durable[:keep_last_n]:
            protected.add(v.version)

        return protected

    def _remove_version_artifacts(
        self,
        derived_id: str,
        version: int,
    ) -> tuple[int, list[str]]:
        """
        Recursively delete the artifact version directory across all profiles.

        Returns ``(files_removed, errors)``.
        """
        files_removed = 0
        errors: list[str] = []
        # Layout: {root}/derived/artifacts/{profile}/{id}/v{version}/
        artifacts_base = self._artifact_root / "derived" / "artifacts"
        if not artifacts_base.is_dir():
            return 0, errors

        for profile_dir in artifacts_base.iterdir():
            if not profile_dir.is_dir():
                continue
            version_dir = profile_dir / derived_id / f"v{version}"
            if version_dir.is_dir():
                files_removed += self._count_files(version_dir)
                try:
                    shutil.rmtree(version_dir)
                except OSError as exc:
                    msg = f"Failed to remove {version_dir}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)

        return files_removed, errors

    @staticmethod
    def _count_files(directory: Path) -> int:
        """Count all regular files under *directory*."""
        count = 0
        for item in directory.rglob("*"):
            if item.is_file():
                count += 1
        return count
