"""Shared artifact reader for unified derived runtime data."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, overload

import polars as pl

from ditto_features.errors import DerivedNotFoundError, DerivedVersionError
from ditto_features.models.derived import (
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_features.services.derived._pruning import prune_parquet_paths

__all__ = [
    "DerivedArtifactReader",
    "VersionResolutionStrategy",
]


class VersionResolutionStrategy(StrEnum):
    """Explicit strategy for version resolution."""

    PRIMARY_ONLINE_ONLY = "primary_online_only"
    FALLBACK_TO_ACTIVE = "fallback_to_active"
    EXPLICIT_VERSION = "explicit_version"


class _CatalogReader(Protocol):
    """Minimal catalog read interface consumed by the artifact reader."""

    def get_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None: ...
    def get_version(
        self, derived_id: str, version: int
    ) -> DerivedVersionRecord | None: ...
    def get_state(self, derived_id: str) -> DerivedStateRecord | None: ...
    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]: ...


class DerivedArtifactReader:
    """Resolve versions and read materialized artifact frames."""

    def __init__(
        self,
        *,
        catalog_service: _CatalogReader,
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

    # ------------------------------------------------------------------
    # read_frame overloads
    # ------------------------------------------------------------------

    @overload
    def read_frame(
        self,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        streaming: bool = False,
        max_rows: int | None = None,
        as_lazy: Literal[False] = False,
    ) -> pl.DataFrame: ...

    @overload
    def read_frame(
        self,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        streaming: bool = False,
        max_rows: int | None = None,
        as_lazy: Literal[True],
    ) -> pl.DataFrame | pl.LazyFrame: ...

    def read_frame(
        self,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        streaming: bool = False,
        max_rows: int | None = None,
        as_lazy: bool = False,
    ) -> pl.DataFrame | pl.LazyFrame:
        """
        Read one artifact slice from parquet partitions.

        Args:
            derived_id: The derived artifact identifier.
            version: The artifact version.
            instrument_ids: Optional filter for specific instruments.
            start: Optional start date filter (inclusive).
            end: Optional end date filter (inclusive).
            as_of: Optional point-in-time filter (inclusive).
            streaming: When True, collect with the streaming engine.
            max_rows: Optional row limit applied before collection.
            as_lazy: When True, return a ``pl.LazyFrame`` without collecting.

        Returns:
            A ``pl.DataFrame`` by default, or a ``pl.LazyFrame`` when
            ``as_lazy=True``.

        """
        frame = self._build_filtered_lazy_frame(
            derived_id=derived_id,
            version=version,
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            as_of=as_of,
        )

        if frame is None:
            return pl.DataFrame()

        if as_lazy:
            return frame

        if max_rows is not None:
            frame = frame.head(max_rows)

        time_key = self._time_key(derived_id, version)

        if streaming:
            collected = frame.collect(engine="streaming").sort(
                ["instrument_id", time_key]
            )
        else:
            collected = frame.collect().sort(["instrument_id", time_key])

        if (
            "availability_time" not in collected.columns
            and time_key in collected.columns
        ):
            collected = collected.with_columns(
                pl.col(time_key).alias("availability_time")
            )
        return collected

    def _build_filtered_lazy_frame(
        self,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
    ) -> pl.LazyFrame | None:
        """
        Build a filtered LazyFrame for the given artifact version.

        Returns ``None`` when no parquet files exist for the requested
        date range (convenient for the ``as_lazy=False`` early-return).
        """
        spec_record = self._require_catalog_entry(derived_id, version)
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec_record.materialization_profile.lower()
            / derived_id
            / f"v{version}"
        )
        parquet_paths = prune_parquet_paths(version_root, start=start, end=end)
        if not parquet_paths:
            return None

        time_key = _effective_time_key(spec_record)
        frame = _scan_with_schema_evolution(parquet_paths)
        if instrument_ids:
            frame = frame.filter(pl.col("instrument_id").is_in(instrument_ids))
        if start is not None:
            frame = frame.filter(pl.col(time_key) >= pl.lit(_coerce_date(start)))
        if end is not None:
            frame = frame.filter(pl.col(time_key) <= pl.lit(_coerce_date(end)))
        if as_of is not None:
            frame = frame.filter(pl.col(time_key) <= pl.lit(_coerce_date(as_of)))
        return frame

    def _time_key(self, derived_id: str, version: int) -> str:
        """Resolve the effective time key for a given derived artifact."""
        spec_record = self._require_catalog_entry(derived_id, version)
        return _effective_time_key(spec_record)

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


def _scan_with_schema_evolution(parquet_paths: list[Path]) -> pl.LazyFrame:
    """
    Scan parquet files with schema evolution support.

    When multiple files have diverging schemas (new columns or widened
    types), ``pl.concat(how='diagonal_relaxed')`` unions the column sets
    and coerces mismatched types to their common supertype.
    """
    if len(parquet_paths) == 1:
        return pl.scan_parquet(str(parquet_paths[0]))
    lfs = [pl.scan_parquet(str(p)) for p in parquet_paths]
    return pl.concat(lfs, how="diagonal_relaxed")
