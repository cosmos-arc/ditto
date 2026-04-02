"""Tests for DerivedArtifactReader version resolution strategy."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from ditto_data.errors import DerivedVersionError
from ditto_datahub.models.derived import (
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services.derived import (
    DerivedArtifactReader,
    VersionResolutionStrategy,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_engine.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile


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
    status: str | None = None,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=profile,
        expression="market.close",
    )
    if status is None:
        status = "published" if is_primary else "materialized"
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
            status=status,
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-13T12:00:00+08:00",
            updated_at=None,
        )
    )


def _save_state(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    active_version: int,
) -> None:
    catalog_service.save_state(
        DerivedStateRecord(
            derived_id=derived_id,
            active_version=active_version,
            coverage_start="2026-01-01",
            coverage_end="2026-03-13",
            watermark="2026-03-13",
            latest_run_id="run-001",
            latest_run_status="SUCCESS",
            total_rows=128,
            updated_at="2026-03-13T12:00:00+08:00",
        )
    )


class TestVersionResolutionStrategy:
    """Tests for the explicit version resolution strategy on resolve_serving_version."""

    def test_primary_online_only_succeeds_when_primary_online_exists(
        self,
        sqlite_client,
    ) -> None:
        """PRIMARY_ONLINE_ONLY should return primary online version."""
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
        _save_state(catalog_service, derived_id=derived_id, active_version=3)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        version = reader.resolve_serving_version(
            derived_id,
            strategy=VersionResolutionStrategy.PRIMARY_ONLINE_ONLY,
        )

        assert version == 2

    def test_primary_online_only_raises_when_no_primary_online(
        self,
        sqlite_client,
    ) -> None:
        """PRIMARY_ONLINE_ONLY should raise when no primary online version exists."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.momentum_20d"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=3,
            is_online=False,
            is_primary=False,
        )
        _save_state(catalog_service, derived_id=derived_id, active_version=3)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        with pytest.raises(DerivedVersionError, match="no primary online version"):
            reader.resolve_serving_version(
                derived_id,
                strategy=VersionResolutionStrategy.PRIMARY_ONLINE_ONLY,
            )

    def test_fallback_to_active_returns_primary_online(
        self,
        sqlite_client,
    ) -> None:
        """FALLBACK_TO_ACTIVE should prefer primary online when available."""
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
        _save_state(catalog_service, derived_id=derived_id, active_version=3)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        version = reader.resolve_serving_version(
            derived_id,
            strategy=VersionResolutionStrategy.FALLBACK_TO_ACTIVE,
        )

        assert version == 2

    def test_fallback_to_active_returns_active_when_no_primary_online(
        self,
        sqlite_client,
    ) -> None:
        """FALLBACK_TO_ACTIVE should return active version as fallback."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.momentum_20d"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=3,
            is_online=False,
            is_primary=False,
        )
        _save_state(catalog_service, derived_id=derived_id, active_version=3)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        version = reader.resolve_serving_version(
            derived_id,
            strategy=VersionResolutionStrategy.FALLBACK_TO_ACTIVE,
        )

        assert version == 3

    def test_explicit_version_returns_requested_version(
        self,
        sqlite_client,
    ) -> None:
        """EXPLICIT_VERSION should return the explicitly specified version."""
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
        _save_state(catalog_service, derived_id=derived_id, active_version=3)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        version = reader.resolve_serving_version(
            derived_id,
            strategy=VersionResolutionStrategy.EXPLICIT_VERSION,
            explicit_version=3,
        )

        assert version == 3

    def test_explicit_version_raises_when_version_none(
        self,
        sqlite_client,
    ) -> None:
        """EXPLICIT_VERSION should raise when explicit_version is None."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.momentum_20d"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=2,
            is_online=True,
            is_primary=True,
        )
        _save_state(catalog_service, derived_id=derived_id, active_version=2)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        with pytest.raises(DerivedVersionError, match="explicit_version is required"):
            reader.resolve_serving_version(
                derived_id,
                strategy=VersionResolutionStrategy.EXPLICIT_VERSION,
            )


class TestPublishedVersionBinding:
    """Tests ensuring version resolution only selects PUBLISHED versions."""

    def test_primary_online_materialized_is_skipped_for_primary_online_only(
        self,
        sqlite_client,
    ) -> None:
        """PRIMARY_ONLINE_ONLY should skip a primary+online version with
        MATERIALIZED status (not PUBLISHED)."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.alpha"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=2,
            is_online=True,
            is_primary=True,
            status="materialized",
        )
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        with pytest.raises(DerivedVersionError, match="no primary online version"):
            reader.resolve_serving_version(
                derived_id,
                strategy=VersionResolutionStrategy.PRIMARY_ONLINE_ONLY,
            )

    def test_fallback_to_active_falls_through_when_primary_not_published(
        self,
        sqlite_client,
    ) -> None:
        """FALLBACK_TO_ACTIVE should fall through to active_version when
        the primary+online version is not PUBLISHED."""
        catalog_service = _catalog_service(sqlite_client)
        derived_id = "factor.alpha"
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=2,
            is_online=True,
            is_primary=True,
            status="materialized",
        )
        _seed_spec(
            catalog_service,
            derived_id=derived_id,
            version=3,
            is_online=True,
            is_primary=True,
            status="published",
        )
        _save_state(catalog_service, derived_id=derived_id, active_version=2)
        reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=Path("/tmp/test-artifacts"),
        )

        version = reader.resolve_serving_version(
            derived_id,
            strategy=VersionResolutionStrategy.FALLBACK_TO_ACTIVE,
        )

        assert version == 3
