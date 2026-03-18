"""Shared artifact reader for unified derived runtime data."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

import polars as pl

from ditto_datahub.errors import DerivedNotFoundError, DerivedVersionError
from ditto_datahub.models.derived import DerivedSpecRecord
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService

__all__ = [
    "DerivedArtifactReader",
    "VersionResolutionStrategy",
]


class VersionResolutionStrategy(StrEnum):
    """Explicit strategy for version resolution."""

    PRIMARY_ONLINE_ONLY = "primary_online_only"
    FALLBACK_TO_ACTIVE = "fallback_to_active"
    EXPLICIT_VERSION = "explicit_version"


class DerivedArtifactReader:
    """Resolve versions and read materialized artifact frames."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        artifact_root: Path,
    ) -> None:
        self._catalog_service = catalog_service
        self._artifact_root = Path(artifact_root)

    def resolve_offline_version(
        self,
        derived_id: str,
        requested_version: int | None = None,
    ) -> int:
        """Resolve an offline artifact version."""
        version = requested_version or self._resolve_active_version(derived_id)
        self._require_catalog_entry(derived_id, version)
        return version

    def resolve_serving_version(
        self,
        derived_id: str,
        *,
        strategy: VersionResolutionStrategy = (
            VersionResolutionStrategy.PRIMARY_ONLINE_ONLY
        ),
        explicit_version: int | None = None,
    ) -> int:
        """
        Resolve the currently serving artifact version.

        Args:
            derived_id: The derived artifact identifier.
            strategy: How to resolve the version.
                Defaults to PRIMARY_ONLINE_ONLY.
            explicit_version: Required when strategy is EXPLICIT_VERSION.

        Returns:
            The resolved version number.

        Raises:
            DerivedVersionError: When resolution fails under the requested strategy.
            DerivedNotFoundError: When the resolved version lacks catalog entries.

        """
        if strategy is VersionResolutionStrategy.EXPLICIT_VERSION:
            if explicit_version is None:
                raise DerivedVersionError(
                    derived_id=derived_id,
                    reason=(
                        "explicit_version is required for "
                        + "EXPLICIT_VERSION strategy"
                    ),
                )
            version = explicit_version
        elif strategy is VersionResolutionStrategy.FALLBACK_TO_ACTIVE:
            version = self._resolve_primary_online(derived_id)
            if version is None:
                version = self._resolve_active_version(derived_id)
        else:
            # PRIMARY_ONLINE_ONLY
            version = self._resolve_primary_online(derived_id)
            if version is None:
                raise DerivedVersionError(
                    derived_id=derived_id,
                    reason="no primary online version found",
                )
        self._require_catalog_entry(derived_id, version)
        return version

    def read_frame(
        self,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
    ) -> pl.DataFrame:
        """Read one artifact slice from parquet partitions."""
        spec_record = self._require_catalog_entry(derived_id, version)
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec_record.materialization_profile.lower()
            / derived_id
            / f"v{version}"
        )
        parquet_paths = sorted(version_root.glob("*.parquet"))
        if not parquet_paths:
            return pl.DataFrame()

        time_key = _effective_time_key(spec_record)
        frame = pl.scan_parquet([str(path) for path in parquet_paths])
        if instrument_ids:
            frame = frame.filter(pl.col("instrument_id").is_in(instrument_ids))
        if start is not None:
            frame = frame.filter(pl.col(time_key) >= pl.lit(_coerce_date(start)))
        if end is not None:
            frame = frame.filter(pl.col(time_key) <= pl.lit(_coerce_date(end)))
        if as_of is not None:
            frame = frame.filter(pl.col(time_key) <= pl.lit(_coerce_date(as_of)))

        collected = frame.collect().sort(["instrument_id", time_key])
        if (
            "availability_time" not in collected.columns
            and time_key in collected.columns
        ):
            collected = collected.with_columns(
                pl.col(time_key).alias("availability_time")
            )
        return collected

    def _resolve_active_version(self, derived_id: str) -> int:
        state = self._catalog_service.get_state(derived_id)
        if state is None or state.active_version is None:
            raise DerivedNotFoundError(derived_id=derived_id)
        return state.active_version

    def _resolve_primary_online(self, derived_id: str) -> int | None:
        """Return the primary online PUBLISHED version, or ``None``."""
        return next(
            (
                record.version
                for record in self._catalog_service.list_versions(derived_id)
                if record.is_primary
                and record.is_online
                and record.status == "published"
            ),
            None,
        )

    def _require_catalog_entry(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedSpecRecord:
        spec_record = self._catalog_service.get_spec(derived_id, version)
        if spec_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        version_record = self._catalog_service.get_version(derived_id, version)
        if version_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return spec_record


def _effective_time_key(spec_record: DerivedSpecRecord) -> str:
    payload = spec_record.spec_json
    time_keys = payload.get("time_keys")
    if isinstance(time_keys, list) and time_keys:
        first = time_keys[0]
        if isinstance(first, str):
            return first
    return "trade_date"


def _coerce_date(value: str) -> date:
    return date.fromisoformat(value[:10])
